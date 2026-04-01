#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import epics


ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = ROOT / "tests" / "integration_3_2_3_3" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_3_2_3_3_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_3_2_3_3_RESULT.md"


PV = {
    "start": "RFQ:LLRF:Con01:AutoC_Start",
    "reset": "RFQ:LLRF:Con01:AutoC_Reset",
    "status": "RFQ:LLRF:Con01:AutoC_Status",
    "rf_on": "RFQ:LLRF:Con01:Opr_RFOn",
    "power": "RFQ:LLRF:Con01_RFIn03:Power",
    "pulse_drive": "RFQ:LLRF:Con01:AmpPulseDrive_Set",
    "cw_drive": "RFQ:LLRF:Con01:AmpCWDrive_Set",
    "pulse_cw": "RFQ:LLRF:Con01:pulsecw",
    "pulse_time": "RFQ:LLRF:Con01:RFPulseOnTime_Set",
    "power_targets": "RFQ:LLRF:Con01:AutoC_PowerTargets",
    "target": "RFQ:LLRF:Con01:AutoC_CurrentTargetPower",
    "init_drive": "RFQ:LLRF:Con01:AutoC_InitDrive",
    "pulse_start": "RFQ:LLRF:Con01:AutoC_PulseStart",
    "pulse_end": "RFQ:LLRF:Con01:AutoC_PulseEnd",
    "pulse_step": "RFQ:LLRF:Con01:AutoC_PulseStep",
    "pulse_wait": "RFQ:LLRF:Con01:AutoC_PulseWaitTime",
    "power_wait": "RFQ:LLRF:Con01:AutoC_PowerWaitTime",
}


STATUS_ALIASES = {
    "IDLE": "IDLE",
    "INIT": "INITIALIZING",
    "INITIALIZING": "INITIALIZING",
    "ADJU": "ADJUSTING_POWER",
    "ADJUSTING_POWER": "ADJUSTING_POWER",
    "WAIT": "WAITING_VACUUM",
    "WAITING_VACUUM": "WAITING_VACUUM",
    "EXPA": "EXPANDING_PULSE",
    "EXPANDING_PULSE": "EXPANDING_PULSE",
    "PAUS": "PAUSED",
    "PAUSED": "PAUSED",
    "COMP": "COMPLETED",
    "COMPLETED": "COMPLETED",
    "ERRO": "ERROR",
    "ERROR": "ERROR",
    "STOP": "STOPPED",
    "STOPPED": "STOPPED",
}


def caget(pv, timeout=1.0, as_string=False):
    return epics.caget(pv, timeout=timeout, as_string=as_string)


def caput(pv, value, timeout=2.0):
    ok = epics.caput(pv, value, wait=True, timeout=timeout)
    return bool(ok)


def _decode_status_value(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip().rstrip("\x00")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="ignore").strip().rstrip("\x00")
    if hasattr(raw, "tolist"):
        arr = raw.tolist()
        if isinstance(arr, list) and arr and isinstance(arr[0], (int, float)):
            chars = []
            for item in arr:
                val = int(item)
                if val == 0:
                    break
                if 32 <= val <= 126:
                    chars.append(chr(val))
            if chars:
                return "".join(chars)
    return str(raw).strip().rstrip("\x00")


def normalize_status(raw):
    decoded = _decode_status_value(raw)
    if not decoded:
        return None
    key = decoded.upper().strip()
    return STATUS_ALIASES.get(key, key)


def get_status(timeout=1.0):
    raw = caget(PV["status"], timeout=timeout, as_string=True)
    status = normalize_status(raw)
    if status:
        return status
    return normalize_status(caget(PV["status"], timeout=timeout))


def append_status(history):
    status = get_status()
    if status and (not history or history[-1] != status):
        history.append(status)
    return status


def wait_for_pv(pv, predicate, timeout=30.0, interval=0.2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = caget(pv)
        if predicate(last):
            return True, last
        time.sleep(interval)
    return False, last


def wait_for_status(predicate, history, timeout=30.0, interval=0.2, ctl_proc=None):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        if ctl_proc is not None and ctl_proc.poll() is not None:
            append_status(history)
            return False, "CONTROLLER_EXITED"
        last = append_status(history)
        if predicate(last):
            return True, last
        time.sleep(interval)
    return False, last


def wait_for_condition(predicate, history, timeout=30.0, interval=0.2, ctl_proc=None):
    end = time.time() + timeout
    while time.time() < end:
        if ctl_proc is not None and ctl_proc.poll() is not None:
            append_status(history)
            return False
        append_status(history)
        if predicate():
            return True
        time.sleep(interval)
    return False


def terminate_process(proc):
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def as_float(value):
    if value is None:
        return None
    return float(value)


def read_snapshot(drive_pv):
    return {
        "status": get_status(),
        "start": caget(PV["start"]),
        "rf_on": caget(PV["rf_on"]),
        "power": as_float(caget(PV["power"])),
        "drive": as_float(caget(drive_pv)),
        "pulse_time_s": as_float(caget(PV["pulse_time"])),
        "target_power": as_float(caget(PV["target"])),
    }


def reset_to_idle(history):
    caput(PV["start"], 0)
    current = append_status(history)
    if current == "IDLE":
        return True, current

    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", history, timeout=20)
    caput(PV["reset"], 0)
    return ok, status


def tc_int_03(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)

    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 120.0)
    caput(PV["pulse_step"], 2.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)

    caput(PV["start"], 1)
    ok_adjusting, _ = wait_for_status(lambda s: s == "ADJUSTING_POWER", history, timeout=60, ctl_proc=ctl_proc)

    ok_drive_changed, _ = wait_for_pv(
        PV["pulse_drive"],
        lambda v: v is not None and float(v) > 100.1,
        timeout=25.0,
        interval=0.2,
    )

    caput(PV["start"], 0)
    ok_paused, _ = wait_for_status(lambda s: s == "PAUSED", history, timeout=20, ctl_proc=ctl_proc)

    time.sleep(1.0)
    pause_begin = read_snapshot(PV["pulse_drive"])
    time.sleep(5.0)
    pause_end = read_snapshot(PV["pulse_drive"])

    caput(PV["start"], 1)
    ok_resume, _ = wait_for_status(lambda s: s == "ADJUSTING_POWER", history, timeout=30, ctl_proc=ctl_proc)

    paused_index = history.index("PAUSED") if "PAUSED" in history else -1
    after_pause_path = history[paused_index + 1:] if paused_index >= 0 else []

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_adjusting": ok_adjusting,
        "drive_changed_before_pause": ok_drive_changed,
        "entered_paused": ok_paused,
        "rf_on_kept_1_during_pause": int(pause_begin["rf_on"]) == 1 and int(pause_end["rf_on"]) == 1 if pause_begin["rf_on"] is not None and pause_end["rf_on"] is not None else False,
        "drive_not_changed_during_pause": abs(pause_end["drive"] - pause_begin["drive"]) <= 1e-6 if pause_begin["drive"] is not None and pause_end["drive"] is not None else False,
        "resumed_to_adjusting": ok_resume,
        "resumed_without_reinit": "INITIALIZING" not in after_pause_path and "IDLE" not in after_pause_path,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-03",
        "name": "调功率过程中暂停与恢复",
        "output": {
            "status_timeline": history,
            "pause_begin": pause_begin,
            "pause_end": pause_end,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def tc_int_04(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)

    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 120.0)
    caput(PV["pulse_step"], 2.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)

    caput(PV["start"], 1)
    ok_expanding, _ = wait_for_status(lambda s: s == "EXPANDING_PULSE", history, timeout=80, ctl_proc=ctl_proc)

    def expanding_with_progress():
        status = get_status()
        pulse = caget(PV["pulse_time"])
        return status == "EXPANDING_PULSE" and pulse is not None and float(pulse) >= 0.102

    ok_progress_ready = wait_for_condition(expanding_with_progress, history, timeout=120, interval=0.2, ctl_proc=ctl_proc)
    pulse_before_pause = as_float(caget(PV["pulse_time"]))

    caput(PV["start"], 0)
    ok_paused, _ = wait_for_status(lambda s: s == "PAUSED", history, timeout=20, ctl_proc=ctl_proc)

    time.sleep(1.0)
    pulse_pause_begin = as_float(caget(PV["pulse_time"]))
    time.sleep(5.0)
    pulse_pause_end = as_float(caget(PV["pulse_time"]))

    caput(PV["start"], 1)
    ok_resume_signal, _ = wait_for_status(
        lambda s: s in ("EXPANDING_PULSE", "ADJUSTING_POWER"),
        history,
        timeout=30,
        ctl_proc=ctl_proc,
    )

    ok_pulse_increase = wait_for_condition(
        lambda: caget(PV["pulse_time"]) is not None and float(caget(PV["pulse_time"])) > (pulse_pause_end + 0.001),
        history,
        timeout=90,
        interval=0.2,
        ctl_proc=ctl_proc,
    )
    pulse_after_resume = as_float(caget(PV["pulse_time"]))

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_expanding": ok_expanding,
        "expanding_progress_observed": ok_progress_ready,
        "entered_paused": ok_paused,
        "pulse_frozen_during_pause": abs(pulse_pause_end - pulse_pause_begin) <= 0.001 if pulse_pause_begin is not None and pulse_pause_end is not None else False,
        "resume_signal_processed": ok_resume_signal,
        "pulse_continues_after_resume": ok_pulse_increase,
        "pulse_not_reset_on_resume": pulse_after_resume >= pulse_before_pause if pulse_after_resume is not None and pulse_before_pause is not None else False,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-04",
        "name": "展脉宽过程中暂停与恢复",
        "output": {
            "status_timeline": history,
            "pulse_before_pause_s": pulse_before_pause,
            "pulse_pause_begin_s": pulse_pause_begin,
            "pulse_pause_end_s": pulse_pause_end,
            "pulse_after_resume_s": pulse_after_resume,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def tc_int_05(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)

    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 100.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)

    caput(PV["start"], 1)

    def at_second_target():
        status = get_status()
        target = caget(PV["target"])
        return status == "ADJUSTING_POWER" and target is not None and abs(float(target) - 20.0) <= 0.1

    ok_second_target = wait_for_condition(at_second_target, history, timeout=140, interval=0.2, ctl_proc=ctl_proc)

    caput(PV["start"], 0)
    ok_paused, _ = wait_for_status(lambda s: s == "PAUSED", history, timeout=20, ctl_proc=ctl_proc)

    pre_reset_target = as_float(caget(PV["target"]))
    pre_reset_pulse = as_float(caget(PV["pulse_time"]))
    caput(PV["reset"], 1)
    ok_back_idle, _ = wait_for_status(lambda s: s == "IDLE", history, timeout=20, ctl_proc=ctl_proc)
    caput(PV["reset"], 0)
    time.sleep(0.5)

    target_after_reset = as_float(caget(PV["target"]))
    pulse_after_reset = as_float(caget(PV["pulse_time"]))
    start_after_reset = caget(PV["start"])

    caput(PV["start"], 1)
    ok_restart, _ = wait_for_status(
        lambda s: s in ("INITIALIZING", "ADJUSTING_POWER"),
        history,
        timeout=40,
        ctl_proc=ctl_proc,
    )

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "reached_second_target_before_pause": ok_second_target,
        "entered_paused": ok_paused,
        "reset_returns_to_idle": ok_back_idle,
        "target_restored_to_first": abs(target_after_reset - 10.0) <= 0.1 if target_after_reset is not None else False,
        "pulse_restored_to_start": abs(pulse_after_reset - 0.1) <= 0.001 if pulse_after_reset is not None else False,
        "start_cleared_after_reset": int(start_after_reset) == 0 if start_after_reset is not None else False,
        "restart_after_reset": ok_restart,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-05",
        "name": "用户暂停后手动复位",
        "output": {
            "status_timeline": history,
            "pre_reset_target": pre_reset_target,
            "pre_reset_pulse_s": pre_reset_pulse,
            "target_after_reset": target_after_reset,
            "pulse_after_reset_s": pulse_after_reset,
            "start_after_reset": start_after_reset,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 3.2/3.3 集成测试结果（TC-INT-03/04/05）")
    lines.append("")
    lines.append("## 执行信息")
    lines.append("")
    lines.append(f"- 时间: `{report['timestamp']}`")
    lines.append(f"- Python: `{report['python']}`")
    lines.append(f"- 结果目录: `{RESULT_DIR.as_posix()}`")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 总用例: `{len(report['cases'])}`")
    lines.append(f"- 通过: `{sum(1 for c in report['cases'] if c['conclusion'] == '通过')}`")
    lines.append(f"- 不通过: `{sum(1 for c in report['cases'] if c['conclusion'] != '通过')}`")
    lines.append("")

    for case in report["cases"]:
        lines.append(f"## {case['id']} {case['name']}")
        lines.append("")
        lines.append("### 测试输出")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(case["output"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        lines.append("### 检查项")
        lines.append("")
        lines.append("| 检查项 | 结果 |")
        lines.append("|---|---|")
        for key, value in case["checks"].items():
            lines.append(f"| `{key}` | `{'PASS' if value else 'FAIL'}` |")
        lines.append("")
        lines.append("### 结论")
        lines.append("")
        lines.append(f"- `{case['conclusion']}`")
        lines.append("")

    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def pick_ca_ports():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        server_port = sock.getsockname()[1]
    repeater_port = server_port + 1 if server_port < 65535 else server_port - 1
    return str(server_port), str(repeater_port)


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    sim_log_fp = SIM_LOG.open("w", encoding="utf-8")
    ctl_log_fp = CTL_LOG.open("w", encoding="utf-8")

    server_port, repeater_port = pick_ca_ports()
    os.environ["EPICS_CA_ADDR_LIST"] = "127.0.0.1"
    os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
    os.environ["EPICS_CA_SERVER_PORT"] = server_port
    os.environ["EPICS_CA_REPEATER_PORT"] = repeater_port

    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{current_pythonpath}" if current_pythonpath else str(ROOT)

    sim_proc = None
    ctl_proc = None
    try:
        sim_log_fp.write(f"[INFO] 使用隔离 CA 端口: server={server_port}, repeater={repeater_port}\n")
        sim_log_fp.flush()

        sim_proc = subprocess.Popen(
            [sys.executable, "tests/sim_ioc.py"],
            cwd=str(ROOT),
            env=env,
            stdout=sim_log_fp,
            stderr=subprocess.STDOUT,
        )

        ok_ioc, _ = wait_for_status(lambda s: s is not None, history=[], timeout=30)
        if not ok_ioc:
            raise RuntimeError("sim_ioc 未就绪，无法读取 AutoC_Status")

        caput(PV["start"], 0)
        caput(PV["reset"], 1)
        time.sleep(0.3)
        caput(PV["reset"], 0)

        ctl_proc = subprocess.Popen(
            [sys.executable, "tests/integration_3_1/cases/controller_runner.py"],
            cwd=str(ROOT),
            env=env,
            stdout=ctl_log_fp,
            stderr=subprocess.STDOUT,
        )
        time.sleep(1.0)
        if ctl_proc.poll() is not None:
            ctl_log_fp.flush()
            raise RuntimeError("controller 进程异常退出，请检查 controller.log")

        case1 = tc_int_03(ctl_proc)
        case2 = tc_int_04(ctl_proc)
        case3 = tc_int_05(ctl_proc)

        report = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "cases": [case1, case2, case3],
        }
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_markdown(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        terminate_process(ctl_proc)
        terminate_process(sim_proc)
        sim_log_fp.close()
        ctl_log_fp.close()


if __name__ == "__main__":
    main()

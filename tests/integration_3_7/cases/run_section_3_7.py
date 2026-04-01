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
RESULT_DIR = ROOT / "tests" / "integration_3_7" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_3_7_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_3_7_RESULT.md"


PV = {
    "start": "RFQ:LLRF:Con01:AutoC_Start",
    "reset": "RFQ:LLRF:Con01:AutoC_Reset",
    "status": "RFQ:LLRF:Con01:AutoC_Status",
    "pulse_cw": "RFQ:LLRF:Con01:pulsecw",
    "power_targets": "RFQ:LLRF:Con01:AutoC_PowerTargets",
    "target": "RFQ:LLRF:Con01:AutoC_CurrentTargetPower",
    "init_drive": "RFQ:LLRF:Con01:AutoC_InitDrive",
    "pulse_start": "RFQ:LLRF:Con01:AutoC_PulseStart",
    "pulse_end": "RFQ:LLRF:Con01:AutoC_PulseEnd",
    "pulse_step": "RFQ:LLRF:Con01:AutoC_PulseStep",
    "pulse_wait": "RFQ:LLRF:Con01:AutoC_PulseWaitTime",
    "power_wait": "RFQ:LLRF:Con01:AutoC_PowerWaitTime",
    "pulse_time": "RFQ:LLRF:Con01:RFPulseOnTime_Set",
    "vac2": "RFQ:Vac2",
    "vac3": "RFQ:Vac3",
    "vac6": "RFQ:Vac6",
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


def as_float(value):
    if value is None:
        return None
    return float(value)


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


def pick_ca_ports():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        server_port = sock.getsockname()[1]
    repeater_port = server_port + 1 if server_port < 65535 else server_port - 1
    return str(server_port), str(repeater_port)


def reset_to_idle(history):
    caput(PV["start"], 0)
    current = append_status(history)
    if current == "IDLE":
        return True, current
    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", history, timeout=20)
    caput(PV["reset"], 0)
    return ok, status


def normalize_vacuum():
    caput(PV["vac2"], 1e-6)
    caput(PV["vac3"], 1e-6)
    caput(PV["vac6"], 1e-6)


def configure_base(pulse_start, pulse_end):
    caput(PV["pulse_cw"], 1)
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], pulse_start)
    caput(PV["pulse_end"], pulse_end)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)


def read_log_since(log_path, offset):
    with log_path.open("r", encoding="utf-8") as fp:
        fp.seek(offset)
        return fp.read()


def tc_int_13(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)
    normalize_vacuum()
    configure_base(pulse_start=100.0, pulse_end=110.0)
    caput(PV["power_targets"], [10.0, 10.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)

    ok_target3 = wait_for_condition(
        lambda: caget(PV["target"]) is not None and float(caget(PV["target"])) >= 29.9,
        history,
        timeout=220,
        interval=0.2,
        ctl_proc=ctl_proc,
    )
    target_now = as_float(caget(PV["target"]))

    log_text = read_log_since(CTL_LOG, log_offset)
    idx_switch2 = log_text.find("切换到第2/3个功率目标")
    idx_switch3 = log_text.find("切换到第3/3个功率目标")
    second_segment = ""
    if idx_switch2 >= 0 and idx_switch3 > idx_switch2:
        second_segment = log_text[idx_switch2:idx_switch3]

    drive_adjust_count = second_segment.count("Drive:")
    has_power_ok_log = "功率达标" in second_segment
    has_direct_expand_log = "功率达标，准备展脉宽" in second_segment

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "switched_to_second_target_log": idx_switch2 >= 0,
        "switched_to_third_target_log": idx_switch3 > idx_switch2 >= 0,
        "target_progressed_to_30_by_pv": ok_target3 and target_now is not None and target_now >= 29.9,
        "no_drive_adjust_while_second_target_already_satisfied": drive_adjust_count == 0,
        "second_target_directly_returns_to_expanding": has_power_ok_log and has_direct_expand_log,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-13",
        "name": "第2段目标功率已满足时跳过调功率",
        "output": {
            "status_timeline": history,
            "target_now": target_now,
            "drive_adjust_count_in_second_segment": drive_adjust_count,
            "has_power_ok_log": has_power_ok_log,
            "has_direct_expand_log": has_direct_expand_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def tc_int_14(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)
    normalize_vacuum()
    configure_base(pulse_start=110.0, pulse_end=110.0)
    caput(PV["power_targets"], [10.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)

    pulse_samples = []
    end = time.time() + 150
    ok_second_target = False
    while time.time() < end:
        if ctl_proc.poll() is not None:
            append_status(history)
            break
        append_status(history)
        pulse_val = as_float(caget(PV["pulse_time"]))
        if pulse_val is not None:
            pulse_samples.append(pulse_val)
        target_val = caget(PV["target"])
        if target_val is not None and abs(float(target_val) - 20.0) <= 0.1:
            ok_second_target = True
            break
        time.sleep(0.2)

    pulse_final = as_float(caget(PV["pulse_time"]))
    pulse_min = min(pulse_samples) if pulse_samples else None
    pulse_max = max(pulse_samples) if pulse_samples else None
    log_text = read_log_since(CTL_LOG, log_offset)
    has_reached_log = "脉宽已达目标" in log_text
    has_expand_write_log = "展脉宽:" in log_text

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "switched_to_second_target": ok_second_target,
        "pulse_kept_at_pulse_end": pulse_final is not None and abs(pulse_final - 0.110) <= 0.001,
        "expand_immediately_marked_complete": has_reached_log,
        "no_pulse_expand_write": not has_expand_write_log,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-14",
        "name": "脉宽已在 pulse_end 时跳过展宽",
        "output": {
            "status_timeline": history,
            "pulse_final_s": pulse_final,
            "pulse_min_s": pulse_min,
            "pulse_max_s": pulse_max,
            "has_reached_log": has_reached_log,
            "has_expand_write_log": has_expand_write_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 3.7 集成测试结果（TC-INT-13/14）")
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


def start_controller(env, ctl_log_fp):
    proc = subprocess.Popen(
        [sys.executable, "tests/integration_3_7/cases/controller_runner.py"],
        cwd=str(ROOT),
        env=env,
        stdout=ctl_log_fp,
        stderr=subprocess.STDOUT,
    )
    time.sleep(1.0)
    return proc


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    SIM_LOG.write_text("", encoding="utf-8")
    CTL_LOG.write_text("", encoding="utf-8")

    server_port, repeater_port = pick_ca_ports()
    os.environ["EPICS_CA_ADDR_LIST"] = "127.0.0.1"
    os.environ["EPICS_CA_AUTO_ADDR_LIST"] = "NO"
    os.environ["EPICS_CA_SERVER_PORT"] = server_port
    os.environ["EPICS_CA_REPEATER_PORT"] = repeater_port

    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{current_pythonpath}" if current_pythonpath else str(ROOT)

    with SIM_LOG.open("a", encoding="utf-8") as sim_log_fp, CTL_LOG.open("a", encoding="utf-8") as ctl_log_fp:
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
            normalize_vacuum()

            ctl_proc = start_controller(env, ctl_log_fp)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出")

            case_13 = tc_int_13(ctl_proc)
            case_14 = tc_int_14(ctl_proc)

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "cases": [case_13, case_14],
            }
            JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            write_markdown(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            terminate_process(ctl_proc)
            terminate_process(sim_proc)


if __name__ == "__main__":
    main()

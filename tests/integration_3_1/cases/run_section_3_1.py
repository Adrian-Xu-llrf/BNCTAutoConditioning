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
RESULT_DIR = ROOT / "tests" / "integration_3_1" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_3_1_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_3_1_RESULT.md"


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


def wait_for_pv(pv, predicate, timeout=30.0, interval=0.2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = caget(pv)
        if predicate(last):
            return True, last
        time.sleep(interval)
    return False, last


def wait_for_status(predicate, timeout=30.0, interval=0.2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = get_status()
        if predicate(last):
            return True, last
        time.sleep(interval)
    return False, last


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


def reset_to_idle():
    caput(PV["start"], 0)
    current = get_status()
    if current == "IDLE":
        return True, current

    # 保持 reset=1 直到观察到 IDLE，避免被 1s 轮询窗口漏采
    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", timeout=20)
    caput(PV["reset"], 0)
    return ok, status


def monitor_until_completed(timeout=180.0, ctl_proc=None):
    end = time.time() + timeout
    statuses = []
    targets = []
    snapshots = []

    last_status = None
    while time.time() < end:
        if ctl_proc is not None and ctl_proc.poll() is not None:
            statuses.append("CONTROLLER_EXITED")
            return False, statuses, targets, snapshots

        status = get_status()
        target = caget(PV["target"])
        power = caget(PV["power"])
        rf_on = caget(PV["rf_on"])
        start = caget(PV["start"])
        pulse_time = caget(PV["pulse_time"])
        cw_drive = caget(PV["cw_drive"])
        pulse_drive = caget(PV["pulse_drive"])

        snapshots.append(
            {
                "status": status,
                "target": None if target is None else float(target),
                "power": None if power is None else float(power),
                "rf_on": rf_on,
                "start": start,
                "pulse_time_s": None if pulse_time is None else float(pulse_time),
                "cw_drive": None if cw_drive is None else float(cw_drive),
                "pulse_drive": None if pulse_drive is None else float(pulse_drive),
            }
        )

        if status != last_status:
            statuses.append(status)
            last_status = status
        if target is not None:
            t = round(float(target), 1)
            if t not in targets:
                targets.append(t)

        if status == "COMPLETED":
            return True, statuses, targets, snapshots
        time.sleep(0.5)

    return False, statuses, targets, snapshots


def tc_int_01(ctl_proc=None):
    ok_idle, idle_status = reset_to_idle()

    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 20.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)

    caput(PV["start"], 1)
    ok_completed, statuses, targets, snapshots = monitor_until_completed(timeout=220.0, ctl_proc=ctl_proc)

    # COMPLETED 由状态机先写状态，再在后续循环将 start 置 0
    time.sleep(1.5)
    start_end = caget(PV["start"])
    rf_on_end = caget(PV["rf_on"])
    pulse_time_end = caget(PV["pulse_time"])

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "completed": ok_completed,
        "status_initializing_seen": "INITIALIZING" in statuses,
        "status_adjusting_seen": "ADJUSTING_POWER" in statuses,
        "status_expanding_seen": "EXPANDING_PULSE" in statuses,
        "status_completed_seen": "COMPLETED" in statuses,
        "target_10_seen": 10.0 in targets,
        "target_20_seen": 20.0 in targets,
        "target_30_seen": 30.0 in targets,
        "start_auto_reset_to_0": int(start_end) == 0 if start_end is not None else False,
        "rf_on_kept_1_after_complete": int(rf_on_end) == 1 if rf_on_end is not None else False,
        "pulse_reached_end_110ms": abs(float(pulse_time_end) - 0.11) <= 0.02 if pulse_time_end is not None else False,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-01",
        "name": "完整三段功率老练（Happy Path）",
        "output": {
            "statuses": statuses,
            "targets_seen": targets,
            "final_start": start_end,
            "final_rf_on": rf_on_end,
            "final_pulse_time_s": pulse_time_end,
            "sample_count": len(snapshots),
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def tc_int_02(ctl_proc=None):
    ok_idle, idle_status = reset_to_idle()

    caput(PV["pulse_cw"], 0)
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    sentinel_expected = 0.123
    caput(PV["pulse_time"], sentinel_expected)
    wait_for_pv(
        PV["pulse_time"],
        lambda v: v is not None and abs(float(v) - sentinel_expected) <= 0.001,
        timeout=5.0,
        interval=0.2,
    )
    sentinel = caget(PV["pulse_time"])

    caput(PV["start"], 1)
    ok_completed, statuses, targets, snapshots = monitor_until_completed(timeout=120.0, ctl_proc=ctl_proc)

    pulse_time_end = caget(PV["pulse_time"])
    cw_drive_end = caget(PV["cw_drive"])
    pulse_drive_end = caget(PV["pulse_drive"])
    power_end = caget(PV["power"])

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "completed": ok_completed,
        "status_completed_seen": "COMPLETED" in statuses,
        "cw_target_seen_10": 10.0 in targets,
        "pulse_time_unchanged": abs(float(pulse_time_end) - sentinel_expected) <= 0.001 if pulse_time_end is not None else False,
        "cw_drive_used": float(cw_drive_end) > 0.0 if cw_drive_end is not None else False,
        "pulse_drive_not_used": abs(float(pulse_drive_end)) <= 1e-6 if pulse_drive_end is not None else False,
        "power_positive": float(power_end) > 0.0 if power_end is not None else False,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-02",
        "name": "CW 模式完整流程",
        "output": {
            "statuses": statuses,
            "targets_seen": targets,
            "pulse_time_expected_s": sentinel_expected,
            "pulse_time_sentinel_s": sentinel,
            "final_pulse_time_s": pulse_time_end,
            "final_cw_drive": cw_drive_end,
            "final_pulse_drive": pulse_drive_end,
            "final_power": power_end,
            "sample_count": len(snapshots),
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 3.1 集成测试结果（TC-INT-01/02）")
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
    # 选择可用 UDP 端口作为 CA server port；repeater port 使用相邻端口
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
        sim_log_fp.write(
            f"[INFO] 使用隔离 CA 端口: server={server_port}, repeater={repeater_port}\n"
        )
        sim_log_fp.flush()

        sim_proc = subprocess.Popen(
            [sys.executable, "tests/sim_ioc.py"],
            cwd=str(ROOT),
            env=env,
            stdout=sim_log_fp,
            stderr=subprocess.STDOUT,
        )
        ok_ioc, status = wait_for_status(lambda s: s is not None, timeout=30)
        if not ok_ioc:
            raise RuntimeError("sim_ioc 未就绪，无法读取 AutoC_Status")

        # 清理残留状态，避免 controller 启动时误判 start=1 直接进入 STOPPED
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

        # controller 进程必须保持存活；否则多半是 import/path 失败
        time.sleep(1.0)
        if ctl_proc.poll() is not None:
            ctl_log_fp.flush()
            raise RuntimeError("controller 进程异常退出，请检查 controller.log")

        case1 = tc_int_01(ctl_proc=ctl_proc)
        case2 = tc_int_02(ctl_proc=ctl_proc)

        report = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "cases": [case1, case2],
        }
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_markdown(report)

        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        terminate_process(ctl_proc)
        if sim_proc is not None:
            terminate_process(sim_proc)
        sim_log_fp.close()
        ctl_log_fp.close()


if __name__ == "__main__":
    main()

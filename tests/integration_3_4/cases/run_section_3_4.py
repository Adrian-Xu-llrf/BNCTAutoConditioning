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
import yaml


ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = ROOT / "tests" / "integration_3_4" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_3_4_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_3_4_RESULT.md"
TMP_CFG = RESULT_DIR / "config_max_faults_3.yaml"


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
    "pulse_drop": "RFQ:LLRF:Con01:AutoC_PulseDrop",
    "arc_status": "RFQ:LLRF:Con01:ArcStatus_Rd",
    "interlock_status": "RFQ:LLRF:Con01:InterlockStatus_Rd",
    "trigger_arc": "RFQ:SIM:TriggerArc",
    "trigger_interlock": "RFQ:SIM:TriggerInterlock",
    "vac_reset": "RFQ:Reset",
    "reset_interlock": "RFQ:LLRF:Con01:ResetInterlock",
    "reset_pw1": "RFQ:LLRF:Mon01:ResetPWFaultStat",
    "reset_pw2": "RFQ:LLRF:Mon02:ResetPWFaultStat",
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


def wait_for_pv(pv, predicate, timeout=30.0, interval=0.2):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = caget(pv)
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


def create_temp_config(max_faults):
    src = ROOT / "config.yaml"
    with src.open("r", encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp)
    cfg["loop"]["max_faults"] = int(max_faults)
    with TMP_CFG.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(cfg, fp, allow_unicode=True, sort_keys=False)
    return str(TMP_CFG)


def reset_to_idle(history):
    caput(PV["start"], 0)
    current = append_status(history)
    if current == "IDLE":
        return True, current
    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", history, timeout=20)
    caput(PV["reset"], 0)
    return ok, status


def configure_fault_recovery_case():
    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 8.0)
    caput(PV["pulse_drop"], 20.0)


def wait_for_fault_injection_window(history, ctl_proc):
    def ready():
        st = get_status()
        tgt = caget(PV["target"])
        pulse = caget(PV["pulse_time"])
        return (
            st == "ADJUSTING_POWER"
            and tgt is not None
            and abs(float(tgt) - 20.0) <= 0.1
            and pulse is not None
            and float(pulse) >= 0.109
        )

    return wait_for_condition(ready, history, timeout=180, interval=0.2, ctl_proc=ctl_proc)


def _log_contains_sequence(log_path, start_offset, keywords):
    with log_path.open("r", encoding="utf-8") as fp:
        fp.seek(start_offset)
        text = fp.read()
    pos = -1
    for kw in keywords:
        idx = text.find(kw, pos + 1)
        if idx < 0:
            return False
        pos = idx
    return True


def run_single_fault_recovery_case(case_id, name, trigger_pv, fault_status_pv, fault_tag, ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)
    configure_fault_recovery_case()

    caput(PV["start"], 1)
    ok_window = wait_for_fault_injection_window(history, ctl_proc)

    pulse_before = as_float(caget(PV["pulse_time"]))
    power_before = as_float(caget(PV["power"]))

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(trigger_pv, 1)
    ok_fault0, fault0 = wait_for_pv(fault_status_pv, lambda v: v is not None and int(v) == 0, timeout=5)
    ok_rf_off, rf_off = wait_for_pv(PV["rf_on"], lambda v: v is not None and int(v) == 0, timeout=5)

    ok_fault1, fault1 = wait_for_pv(fault_status_pv, lambda v: v is not None and int(v) == 1, timeout=45)
    ok_rf_on, rf_on = wait_for_pv(PV["rf_on"], lambda v: v is not None and int(v) == 1, timeout=45)

    ok_recover_state, recover_state = wait_for_status(
        lambda s: s in ("INITIALIZING", "ADJUSTING_POWER", "EXPANDING_PULSE"),
        history,
        timeout=45,
        ctl_proc=ctl_proc,
    )
    ok_power_recovered, _ = wait_for_pv(
        PV["power"],
        lambda v: v is not None and float(v) > 1.0,
        timeout=45,
        interval=0.2,
    )
    power_after = as_float(caget(PV["power"]))
    pulse_after = as_float(caget(PV["pulse_time"]))
    pulse_drop_observed = (
        pulse_before is not None and pulse_after is not None and pulse_after < pulse_before - 1e-6
    )
    log_sequence_ok = _log_contains_sequence(
        CTL_LOG,
        log_offset,
        [
            f"[{fault_tag}] VacReset",
            f"[{fault_tag}] reset_interlock",
            f"[{fault_tag}] ResetPWFaultStat1",
            f"[{fault_tag}] ResetPWFaultStat2",
        ],
    )

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "fault_window_ready": ok_window,
        "fault_status_to_0": ok_fault0 and int(fault0) == 0 if fault0 is not None else False,
        "rf_off_after_fault": ok_rf_off and int(rf_off) == 0 if rf_off is not None else False,
        "recovery_sequence_order": log_sequence_ok,
        "fault_status_back_to_1": ok_fault1 and int(fault1) == 1 if fault1 is not None else False,
        "rf_on_after_recovery": ok_rf_on and int(rf_on) == 1 if rf_on is not None else False,
        "recovery_state_seen": ok_recover_state,
        "power_recovered_positive": ok_power_recovered and power_after is not None and power_after > 1.0,
        "pulse_dropped_after_fault": pulse_drop_observed,
    }
    passed = all(checks.values())

    return {
        "id": case_id,
        "name": name,
        "output": {
            "status_timeline": history,
            "recovery_sequence_from_log": log_sequence_ok,
            "pulse_before_s": pulse_before,
            "pulse_after_s": pulse_after,
            "power_before": power_before,
            "power_after": power_after,
            "recovery_state": recover_state,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def tc_int_06(ctl_proc):
    return run_single_fault_recovery_case(
        "TC-INT-06",
        "单次 Arc 故障自动恢复",
        PV["trigger_arc"],
        PV["arc_status"],
        "Arc",
        ctl_proc,
    )


def tc_int_07(ctl_proc):
    return run_single_fault_recovery_case(
        "TC-INT-07",
        "单次 VacInterlock 故障自动恢复",
        PV["trigger_interlock"],
        PV["interlock_status"],
        "VacInterlock",
        ctl_proc,
    )


def tc_int_08_and_09(ctl_proc):
    history = []
    reset_to_idle(history)

    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 120.0)
    caput(PV["pulse_step"], 5.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)

    caput(PV["start"], 1)
    ok_running, _ = wait_for_status(
        lambda s: s in ("ADJUSTING_POWER", "EXPANDING_PULSE"),
        history,
        timeout=80,
        ctl_proc=ctl_proc,
    )

    recovery_flags = []
    for i in range(3):
        caput(PV["trigger_arc"], 1)
        ok_arc0, _ = wait_for_pv(PV["arc_status"], lambda v: v is not None and int(v) == 0, timeout=5)
        if i < 2:
            ok_recovered = wait_for_condition(
                lambda: (
                    caget(PV["arc_status"]) is not None
                    and int(caget(PV["arc_status"])) == 1
                    and caget(PV["rf_on"]) is not None
                    and int(caget(PV["rf_on"])) == 1
                    and get_status() in ("ADJUSTING_POWER", "EXPANDING_PULSE", "INITIALIZING")
                ),
                history,
                timeout=60,
                interval=0.2,
                ctl_proc=ctl_proc,
            )
            recovery_flags.append(bool(ok_arc0 and ok_recovered))
        else:
            recovery_flags.append(bool(ok_arc0))
        time.sleep(1.0)

    ok_error, _ = wait_for_status(lambda s: s == "ERROR", history, timeout=45, ctl_proc=ctl_proc)
    ok_rf_off, _ = wait_for_pv(PV["rf_on"], lambda v: v is not None and int(v) == 0, timeout=10, interval=0.2)
    rf_on_error = caget(PV["rf_on"])
    pulse_drive_error = as_float(caget(PV["pulse_drive"]))
    cw_drive_error = as_float(caget(PV["cw_drive"]))
    time.sleep(5.0)
    status_after_5s = get_status()

    checks_08 = {
        "running_before_faults": ok_running,
        "first_two_faults_recovered": len(recovery_flags) >= 2 and recovery_flags[0] and recovery_flags[1],
        "third_fault_triggers_error": ok_error,
        "rf_off_in_error": ok_rf_off and int(rf_on_error) == 0 if rf_on_error is not None else False,
        "drive_zero_in_error": (
            (pulse_drive_error is None or abs(pulse_drive_error) <= 1e-6)
            and (cw_drive_error is None or abs(cw_drive_error) <= 1e-6)
        ),
        "stays_error_without_manual_reset": status_after_5s == "ERROR",
    }
    passed_08 = all(checks_08.values())

    caput(PV["reset"], 1)
    ok_back_idle, _ = wait_for_status(lambda s: s == "IDLE", history, timeout=20, ctl_proc=ctl_proc)
    caput(PV["reset"], 0)
    time.sleep(0.5)

    pulse_after_reset = as_float(caget(PV["pulse_time"]))
    start_after_reset = caget(PV["start"])
    target_after_reset = as_float(caget(PV["target"]))

    caput(PV["start"], 1)
    ok_restart, restart_state = wait_for_status(
        lambda s: s in ("INITIALIZING", "ADJUSTING_POWER"),
        history,
        timeout=40,
        ctl_proc=ctl_proc,
    )

    checks_09 = {
        "reset_back_to_idle": ok_back_idle,
        "pulse_restored_to_original_start": abs(pulse_after_reset - 0.1) <= 0.001 if pulse_after_reset is not None else False,
        "target_reinitialized": target_after_reset is not None and target_after_reset > 0.0,
        "restart_possible_after_error": ok_restart,
    }
    passed_09 = all(checks_09.values())

    case_08 = {
        "id": "TC-INT-08",
        "name": "故障次数超限进入 ERROR",
        "output": {
            "status_timeline": history,
            "recovery_flags_first_three_faults": recovery_flags,
            "rf_on_error": rf_on_error,
            "pulse_drive_error": pulse_drive_error,
            "cw_drive_error": cw_drive_error,
            "status_after_5s": status_after_5s,
        },
        "checks": checks_08,
        "conclusion": "通过" if passed_08 else "不通过",
    }

    case_09 = {
        "id": "TC-INT-09",
        "name": "ERROR 状态后手动复位",
        "output": {
            "status_timeline": history,
            "pulse_after_reset_s": pulse_after_reset,
            "start_after_reset": start_after_reset,
            "target_after_reset": target_after_reset,
            "restart_state": restart_state,
        },
        "checks": checks_09,
        "conclusion": "通过" if passed_09 else "不通过",
    }
    return case_08, case_09


def write_markdown(report):
    lines = []
    lines.append("# 3.4 集成测试结果（TC-INT-06/07/08/09）")
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


def start_controller(env, config_file, ctl_log_fp):
    env2 = env.copy()
    env2["RFQ_CONFIG_FILE"] = config_file
    proc = subprocess.Popen(
        [sys.executable, "tests/integration_3_4/cases/controller_runner.py"],
        cwd=str(ROOT),
        env=env2,
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

            ctl_proc = start_controller(env, "config.yaml", ctl_log_fp)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（默认配置）")

            case_06 = tc_int_06(ctl_proc)
            case_07 = tc_int_07(ctl_proc)

            terminate_process(ctl_proc)
            ctl_proc = None
            time.sleep(0.8)
            caput(PV["start"], 0)
            caput(PV["reset"], 0)

            maxfault_cfg = create_temp_config(max_faults=3)
            ctl_proc = start_controller(env, maxfault_cfg, ctl_log_fp)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（max_faults=3 配置）")

            case_08, case_09 = tc_int_08_and_09(ctl_proc)

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "cases": [case_06, case_07, case_08, case_09],
            }
            JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            write_markdown(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            terminate_process(ctl_proc)
            terminate_process(sim_proc)
            if TMP_CFG.exists():
                TMP_CFG.unlink()


if __name__ == "__main__":
    main()

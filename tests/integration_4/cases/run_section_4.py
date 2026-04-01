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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rfq.utils.pv_manager import PVManager


RESULT_DIR = ROOT / "tests" / "integration_4" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_4_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_4_RESULT.md"


PV = {
    "start": "RFQ:LLRF:Con01:AutoC_Start",
    "reset": "RFQ:LLRF:Con01:AutoC_Reset",
    "status": "RFQ:LLRF:Con01:AutoC_Status",
    "rf_on": "RFQ:LLRF:Con01:Opr_RFOn",
    "power": "RFQ:LLRF:Con01_RFIn03:Power",
    "pulse_cw": "RFQ:LLRF:Con01:pulsecw",
    "pulse_drive": "RFQ:LLRF:Con01:AmpPulseDrive_Set",
    "pulse_time": "RFQ:LLRF:Con01:RFPulseOnTime_Set",
    "power_targets": "RFQ:LLRF:Con01:AutoC_PowerTargets",
    "target": "RFQ:LLRF:Con01:AutoC_CurrentTargetPower",
    "init_drive": "RFQ:LLRF:Con01:AutoC_InitDrive",
    "pulse_start": "RFQ:LLRF:Con01:AutoC_PulseStart",
    "pulse_end": "RFQ:LLRF:Con01:AutoC_PulseEnd",
    "pulse_step": "RFQ:LLRF:Con01:AutoC_PulseStep",
    "pulse_wait": "RFQ:LLRF:Con01:AutoC_PulseWaitTime",
    "power_wait": "RFQ:LLRF:Con01:AutoC_PowerWaitTime",
    "trigger_arc": "RFQ:SIM:TriggerArc",
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


def start_controller(env, ctl_log_fp, config_file="config.yaml"):
    env2 = env.copy()
    env2["RFQ_CONFIG_FILE"] = str(config_file)
    proc = subprocess.Popen(
        [sys.executable, "tests/integration_4/cases/controller_runner.py"],
        cwd=str(ROOT),
        env=env2,
        stdout=ctl_log_fp,
        stderr=subprocess.STDOUT,
    )
    time.sleep(1.0)
    return proc


def reset_to_idle(history, ctl_proc):
    caput(PV["start"], 0)
    current = append_status(history)
    if current == "IDLE":
        return True, current
    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", history, timeout=25, ctl_proc=ctl_proc)
    caput(PV["reset"], 0)
    return ok, status


def normalize_vacuum():
    caput(PV["vac2"], 1e-6)
    caput(PV["vac3"], 1e-6)
    caput(PV["vac6"], 1e-6)


def configure_case_defaults():
    caput(PV["pulse_cw"], 1)
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)


def read_log_since(offset):
    with CTL_LOG.open("r", encoding="utf-8") as fp:
        fp.seek(offset)
        return fp.read()


def create_temp_config(name, modifier):
    src = ROOT / "config.yaml"
    dst = RESULT_DIR / f"{name}.yaml"
    with src.open("r", encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp)
    modifier(cfg)
    with dst.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(cfg, fp, allow_unicode=True, sort_keys=False)
    return dst


def e01_all_zero_targets(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [0.0] * 10)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)
    ok_error, _ = wait_for_status(lambda s: s == "ERROR", history, timeout=45, ctl_proc=ctl_proc)
    ok_start_zero, start_val = wait_for_pv(PV["start"], lambda v: v is not None and int(v) == 0, timeout=15)
    log_text = read_log_since(log_offset)
    has_log = "power_targets waveform PV 为空或全零" in log_text

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_error_or_not_started": ok_error,
        "start_cleared": ok_start_zero and int(start_val) == 0 if start_val is not None else False,
        "error_log_present": has_log,
    }
    passed = all(checks.values())
    return {
        "id": "E-01",
        "name": "AutoC_PowerTargets 全为 0",
        "output": {
            "status_timeline": history,
            "start_after_error": start_val,
            "error_log_present": has_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e02_pulse_start_gt_end(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_start"], 120.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)
    ok_completed, _ = wait_for_status(lambda s: s == "COMPLETED", history, timeout=90, ctl_proc=ctl_proc)
    pulse_time_after = as_float(caget(PV["pulse_time"]))
    log_text = read_log_since(log_offset)
    has_no_expand_write = "展脉宽:" not in log_text
    has_reached_log = "脉宽已达目标" in log_text

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "completed_without_looping": ok_completed,
        "pulse_time_kept_at_start": pulse_time_after is not None and abs(pulse_time_after - 0.12) <= 0.001,
        "no_pulse_expand_write": has_no_expand_write,
        "reached_target_log_present": has_reached_log,
    }
    passed = all(checks.values())
    return {
        "id": "E-02",
        "name": "pulse_start > pulse_end",
        "output": {
            "status_timeline": history,
            "pulse_time_after_s": pulse_time_after,
            "has_no_expand_write": has_no_expand_write,
            "has_reached_log": has_reached_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e03_pulse_step_zero(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 0.0)

    caput(PV["start"], 1)
    ok_active, _ = wait_for_status(
        lambda s: s in ("ADJUSTING_POWER", "EXPANDING_PULSE"),
        history,
        timeout=60,
        ctl_proc=ctl_proc,
    )
    pulse_before = as_float(caget(PV["pulse_time"]))
    time.sleep(12.0)
    append_status(history)
    pulse_after = as_float(caget(PV["pulse_time"]))
    final_status = get_status()
    controller_alive = ctl_proc.poll() is None

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_active_states": ok_active,
        "controller_not_crashed": controller_alive,
        "not_enter_error": final_status != "ERROR",
        "no_progress_risk_observed": (
            pulse_before is not None and pulse_after is not None and abs(pulse_after - pulse_before) <= 0.001
        ),
    }
    passed = all(checks.values())
    return {
        "id": "E-03",
        "name": "pulse_step = 0",
        "output": {
            "status_timeline": history,
            "pulse_before_s": pulse_before,
            "pulse_after_s": pulse_after,
            "final_status": final_status,
            "controller_alive": controller_alive,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e06_modify_pulse_end_while_paused(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 5.0)

    caput(PV["start"], 1)
    ok_expanding = wait_for_condition(
        lambda: get_status() == "EXPANDING_PULSE",
        history,
        timeout=80,
        interval=0.2,
        ctl_proc=ctl_proc,
    )

    caput(PV["start"], 0)
    ok_paused, _ = wait_for_status(lambda s: s == "PAUSED", history, timeout=20, ctl_proc=ctl_proc)
    pulse_when_paused = as_float(caget(PV["pulse_time"]))

    caput(PV["pulse_end"], 130.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["start"], 1)
    ok_resume = wait_for_condition(
        lambda: caget(PV["pulse_time"]) is not None and float(caget(PV["pulse_time"])) >= 0.129,
        history,
        timeout=180,
        interval=0.2,
        ctl_proc=ctl_proc,
    )
    pulse_after_resume = as_float(caget(PV["pulse_time"]))

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_expanding_before_pause": ok_expanding,
        "paused_successfully": ok_paused,
        "resume_uses_new_pulse_end": ok_resume and pulse_after_resume is not None and pulse_after_resume >= 0.129,
        "pulse_after_resume_gt_old_end": pulse_after_resume is not None and pulse_after_resume > 0.11,
    }
    passed = all(checks.values())
    return {
        "id": "E-06",
        "name": "PAUSED 期间修改 AutoC_PulseEnd",
        "output": {
            "status_timeline": history,
            "pulse_when_paused_s": pulse_when_paused,
            "pulse_after_resume_s": pulse_after_resume,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e07_modify_power_targets_while_paused(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [30.0, 40.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["init_drive"], 100.0)

    caput(PV["start"], 1)
    ok_adjusting = wait_for_condition(
        lambda: get_status() == "ADJUSTING_POWER" and caget(PV["target"]) is not None and float(caget(PV["target"])) >= 29.9,
        history,
        timeout=80,
        interval=0.2,
        ctl_proc=ctl_proc,
    )

    caput(PV["start"], 0)
    ok_paused, _ = wait_for_status(lambda s: s == "PAUSED", history, timeout=20, ctl_proc=ctl_proc)
    target_before = as_float(caget(PV["target"]))

    caput(PV["power_targets"], [15.0, 25.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["start"], 1)
    ok_new_target = wait_for_condition(
        lambda: caget(PV["target"]) is not None and abs(float(caget(PV["target"])) - 15.0) <= 0.1,
        history,
        timeout=40,
        interval=0.2,
        ctl_proc=ctl_proc,
    )
    target_after = as_float(caget(PV["target"]))

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_adjusting_before_pause": ok_adjusting,
        "paused_successfully": ok_paused,
        "new_targets_applied_on_resume": ok_new_target and target_after is not None and abs(target_after - 15.0) <= 0.1,
    }
    passed = all(checks.values())
    return {
        "id": "E-07",
        "name": "PAUSED 期间修改 AutoC_PowerTargets",
        "output": {
            "status_timeline": history,
            "target_before_pause": target_before,
            "target_after_resume": target_after,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e04_max_faults_zero(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()
    caput(PV["power_targets"], [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)

    caput(PV["start"], 1)
    ok_adjusting, _ = wait_for_status(lambda s: s == "ADJUSTING_POWER", history, timeout=80, ctl_proc=ctl_proc)
    caput(PV["trigger_arc"], 1)
    ok_error, _ = wait_for_status(lambda s: s == "ERROR", history, timeout=30, ctl_proc=ctl_proc)
    rf_on_in_error = caget(PV["rf_on"])

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_adjusting": ok_adjusting,
        "first_fault_enters_error": ok_error,
        "rf_off_in_error": rf_on_in_error is not None and int(rf_on_in_error) == 0,
    }
    passed = all(checks.values())
    return {
        "id": "E-04",
        "name": "max_faults = 0",
        "output": {
            "status_timeline": history,
            "rf_on_in_error": rf_on_in_error,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e05_pv_read_fail(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_case_defaults()

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)
    ok_error, _ = wait_for_status(lambda s: s == "ERROR", history, timeout=45, ctl_proc=ctl_proc)
    log_text = read_log_since(log_offset)
    has_log = ("power_targets waveform PV 为空或全零" in log_text) or ("无法读取初始Drive PV" in log_text)

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_error": ok_error,
        "critical_pv_read_fail_log_present": has_log,
    }
    passed = all(checks.values())
    return {
        "id": "E-05",
        "name": "关键 PV 读取失败",
        "output": {
            "status_timeline": history,
            "critical_fail_log_present": has_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e08_long_chinese_truncation():
    text = "状态异常" * 30
    out = PVManager.safe_status(text)
    encoded = out.encode("utf-8")
    decoded = encoded.decode("utf-8")
    checks = {
        "valid_utf8_after_truncate": decoded == out,
        "bytes_within_limit": len(encoded) <= 40,
        "no_replacement_char": "�" not in out,
    }
    passed = all(checks.values())
    return {
        "id": "E-08",
        "name": "超长中文状态字符串截断",
        "output": {
            "input_len_chars": len(text),
            "output_text": out,
            "output_len_chars": len(out),
            "output_len_bytes": len(encoded),
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def e09_mixed_lang_truncation():
    text = "Status状态混合-0123456789-异常告警-" * 4
    out = PVManager.safe_status(text)
    encoded = out.encode("utf-8")
    decoded = encoded.decode("utf-8")
    checks = {
        "valid_utf8_after_truncate": decoded == out,
        "bytes_within_limit": len(encoded) <= 40,
        "no_replacement_char": "�" not in out,
    }
    passed = all(checks.values())
    return {
        "id": "E-09",
        "name": "中英文混合长字符串截断",
        "output": {
            "input_len_chars": len(text),
            "output_text": out,
            "output_len_chars": len(out),
            "output_len_bytes": len(encoded),
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 第4章 边界与异常测试结果（E-01 ~ E-09）")
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

    tmp_cfgs = []
    sim_proc = None
    ctl_proc = None
    with SIM_LOG.open("a", encoding="utf-8") as sim_log_fp, CTL_LOG.open("a", encoding="utf-8") as ctl_log_fp:
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

            ctl_proc = start_controller(env, ctl_log_fp, "config.yaml")
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（默认配置）")

            case_e01 = e01_all_zero_targets(ctl_proc)
            case_e02 = e02_pulse_start_gt_end(ctl_proc)
            case_e03 = e03_pulse_step_zero(ctl_proc)
            case_e06 = e06_modify_pulse_end_while_paused(ctl_proc)
            case_e07 = e07_modify_power_targets_while_paused(ctl_proc)

            terminate_process(ctl_proc)
            ctl_proc = None
            time.sleep(0.6)

            cfg_e04 = create_temp_config("config_max_faults_0", lambda c: c["loop"].update({"max_faults": 0}))
            tmp_cfgs.append(cfg_e04)
            ctl_proc = start_controller(env, ctl_log_fp, cfg_e04)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（max_faults=0）")
            case_e04 = e04_max_faults_zero(ctl_proc)
            terminate_process(ctl_proc)
            ctl_proc = None
            time.sleep(0.6)

            def _e05_modifier(cfg):
                cfg["pv"]["control"]["power_targets"] = "RFQ:NONEXIST:AutoC_PowerTargets"
                cfg["pv"]["control"]["init_drive"] = "RFQ:NONEXIST:AutoC_InitDrive"

            cfg_e05 = create_temp_config("config_pv_read_fail", _e05_modifier)
            tmp_cfgs.append(cfg_e05)
            ctl_proc = start_controller(env, ctl_log_fp, cfg_e05)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（PV读失败配置）")
            case_e05 = e05_pv_read_fail(ctl_proc)

            case_e08 = e08_long_chinese_truncation()
            case_e09 = e09_mixed_lang_truncation()

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "cases": [
                    case_e01,
                    case_e02,
                    case_e03,
                    case_e04,
                    case_e05,
                    case_e06,
                    case_e07,
                    case_e08,
                    case_e09,
                ],
            }
            JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            write_markdown(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            terminate_process(ctl_proc)
            terminate_process(sim_proc)
            for cfg in tmp_cfgs:
                if cfg.exists():
                    cfg.unlink()


if __name__ == "__main__":
    main()

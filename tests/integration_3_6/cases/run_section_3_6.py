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
RESULT_DIR = ROOT / "tests" / "integration_3_6" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_3_6_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_3_6_RESULT.md"


PV = {
    "start": "RFQ:LLRF:Con01:AutoC_Start",
    "reset": "RFQ:LLRF:Con01:AutoC_Reset",
    "status": "RFQ:LLRF:Con01:AutoC_Status",
    "rf_on": "RFQ:LLRF:Con01:Opr_RFOn",
    "pulse_cw": "RFQ:LLRF:Con01:pulsecw",
    "power_targets": "RFQ:LLRF:Con01:AutoC_PowerTargets",
    "init_drive": "RFQ:LLRF:Con01:AutoC_InitDrive",
    "pulse_start": "RFQ:LLRF:Con01:AutoC_PulseStart",
    "pulse_end": "RFQ:LLRF:Con01:AutoC_PulseEnd",
    "pulse_step": "RFQ:LLRF:Con01:AutoC_PulseStep",
    "pulse_wait": "RFQ:LLRF:Con01:AutoC_PulseWaitTime",
    "power_wait": "RFQ:LLRF:Con01:AutoC_PowerWaitTime",
    "block_rf_on": "RFQ:SIM:BlockRFOn",
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


def configure_case_defaults():
    caput(PV["vac2"], 1e-6)
    caput(PV["vac3"], 1e-6)
    caput(PV["vac6"], 1e-6)
    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.5)
    caput(PV["power_wait"], 0.5)


def read_log_since(log_path, offset):
    with log_path.open("r", encoding="utf-8") as fp:
        fp.seek(offset)
        return fp.read()


def tc_int_12(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history)
    configure_case_defaults()

    caput(PV["block_rf_on"], 1)
    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)

    ok_error, _ = wait_for_status(lambda s: s == "ERROR", history, timeout=180, ctl_proc=ctl_proc)
    rf_on_in_error = caget(PV["rf_on"])

    log_text = read_log_since(CTL_LOG, log_offset)
    retry_attempt_count = log_text.count("RF启动尝试")
    has_retry_log = "正在重置Interlock故障" in log_text
    has_max_retry_log = "已达到最大重试次数" in log_text

    caput(PV["block_rf_on"], 0)
    caput(PV["reset"], 1)
    ok_back_idle, _ = wait_for_status(lambda s: s == "IDLE", history, timeout=30, ctl_proc=ctl_proc)
    caput(PV["reset"], 0)

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_error_after_retries": ok_error,
        "rf_off_in_error": rf_on_in_error is not None and int(rf_on_in_error) == 0,
        "retry_count_reached_max_5": retry_attempt_count >= 5,
        "retry_logs_present": has_retry_log and has_max_retry_log,
        "manual_reset_back_to_idle": ok_back_idle,
    }
    passed = all(checks.values())

    return {
        "id": "TC-INT-12",
        "name": "RF 启动后 rf_on 未响应，触发重试",
        "output": {
            "status_timeline": history,
            "rf_on_in_error": rf_on_in_error,
            "retry_attempt_count": retry_attempt_count,
            "has_retry_log": has_retry_log,
            "has_max_retry_log": has_max_retry_log,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 3.6 集成测试结果（TC-INT-12）")
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
        [sys.executable, "tests/integration_3_6/cases/controller_runner.py"],
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
            caput(PV["block_rf_on"], 0)

            ctl_proc = start_controller(env, ctl_log_fp)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出")

            case_12 = tc_int_12(ctl_proc)

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "cases": [case_12],
            }
            JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            write_markdown(report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            terminate_process(ctl_proc)
            terminate_process(sim_proc)


if __name__ == "__main__":
    main()

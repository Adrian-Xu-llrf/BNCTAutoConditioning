#!/usr/bin/env python3
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import epics
import psutil
import yaml


ROOT = Path(__file__).resolve().parents[3]
RESULT_DIR = ROOT / "tests" / "integration_5" / "results"
SIM_LOG = RESULT_DIR / "sim_ioc.log"
CTL_LOG = RESULT_DIR / "controller.log"
JSON_OUT = RESULT_DIR / "SECTION_5_RESULT.json"
MD_OUT = RESULT_DIR / "SECTION_5_RESULT.md"


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


def read_log_since(offset):
    with CTL_LOG.open("r", encoding="utf-8") as fp:
        fp.seek(offset)
        return fp.read()


def get_proc_metrics(proc):
    p = psutil.Process(proc.pid)
    return {
        "rss_mb": round(p.memory_info().rss / (1024 * 1024), 2),
        "num_threads": p.num_threads(),
    }


def start_controller(env, ctl_log_fp, config_file="config.yaml"):
    env2 = env.copy()
    env2["RFQ_CONFIG_FILE"] = str(config_file)
    proc = subprocess.Popen(
        [sys.executable, "tests/integration_5/cases/controller_runner.py"],
        cwd=str(ROOT),
        env=env2,
        stdout=ctl_log_fp,
        stderr=subprocess.STDOUT,
    )
    time.sleep(1.0)
    return proc


def create_temp_config(name, modifier):
    src = ROOT / "config.yaml"
    dst = RESULT_DIR / f"{name}.yaml"
    with src.open("r", encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp)
    modifier(cfg)
    with dst.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(cfg, fp, allow_unicode=True, sort_keys=False)
    return dst


def reset_to_idle(history, ctl_proc):
    caput(PV["start"], 0)
    current = append_status(history)
    if current == "IDLE":
        return True, current
    caput(PV["reset"], 1)
    ok, status = wait_for_status(lambda s: s == "IDLE", history, timeout=30, ctl_proc=ctl_proc)
    caput(PV["reset"], 0)
    return ok, status


def normalize_vacuum():
    caput(PV["vac2"], 1e-6)
    caput(PV["vac3"], 1e-6)
    caput(PV["vac6"], 1e-6)


def configure_fast_conditioning():
    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 20.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 120.0)
    caput(PV["pulse_step"], 5.0)
    caput(PV["pulse_wait"], 0.2)
    caput(PV["power_wait"], 0.2)
    caput(PV["pulse_drop"], 20.0)


def configure_stability_quick_cycles():
    # 5.1 使用快速参数跑10轮，重点验证长期循环下的进程资源与状态稳定性
    caput(PV["pulse_cw"], 1)
    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["init_drive"], 100.0)
    caput(PV["pulse_start"], 100.0)
    caput(PV["pulse_end"], 110.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_wait"], 0.1)
    caput(PV["power_wait"], 0.1)
    caput(PV["pulse_drop"], 5.0)


def s51_long_run_stability(ctl_proc, cycles=10):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_stability_quick_cycles()

    cycle_metrics = []
    completed_cycles = 0
    completion_log_seen = 0
    for i in range(cycles):
        cycle_log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
        caput(PV["start"], 1)
        ok_completed, _ = wait_for_status(lambda s: s == "COMPLETED", history, timeout=150, ctl_proc=ctl_proc)
        ok_start_zero = False
        has_completion_log = False
        if ok_completed:
            ok_start_zero, _ = wait_for_pv(
                PV["start"],
                lambda v: v is not None and int(v) == 0,
                timeout=10,
                interval=0.2,
            )
            if not ok_start_zero:
                caput(PV["start"], 0)
                ok_start_zero = True
            has_completion_log = "老练成功完成" in read_log_since(cycle_log_offset)
            if has_completion_log:
                completion_log_seen += 1
        metrics = get_proc_metrics(ctl_proc)
        metrics["cycle"] = i + 1
        metrics["completed"] = bool(ok_completed)
        metrics["start_cleared"] = bool(ok_start_zero)
        metrics["completion_log_seen"] = bool(has_completion_log)
        cycle_metrics.append(metrics)
        if not ok_completed:
            break
        completed_cycles += 1
        caput(PV["reset"], 1)
        ok_back_idle, _ = wait_for_status(lambda s: s == "IDLE", history, timeout=40, ctl_proc=ctl_proc)
        caput(PV["reset"], 0)
        if not ok_back_idle:
            break

    rss_values = [m["rss_mb"] for m in cycle_metrics]
    thread_values = [m["num_threads"] for m in cycle_metrics]
    rss_growth = (max(rss_values) - min(rss_values)) if rss_values else None
    thread_delta = (max(thread_values) - min(thread_values)) if thread_values else None

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "all_10_cycles_completed": completed_cycles == cycles,
        "memory_growth_within_80mb": rss_growth is not None and rss_growth <= 80.0,
        "thread_delta_within_2": thread_delta is not None and thread_delta <= 2,
        "completion_log_seen_in_cycles": completion_log_seen >= 1,
    }
    passed = all(checks.values())
    return {
        "id": "S-5.1",
        "name": "长时间运行测试（10次完整循环）",
        "output": {
            "status_timeline": history,
            "completed_cycles": completed_cycles,
            "completion_log_seen": completion_log_seen,
            "cycle_metrics": cycle_metrics,
            "rss_growth_mb": rss_growth,
            "thread_delta": thread_delta,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def s52_fault_recovery_stress(ctl_proc, loops=20):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_fast_conditioning()

    caput(PV["power_targets"], [10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    caput(PV["pulse_end"], 120.0)
    caput(PV["pulse_step"], 10.0)
    caput(PV["pulse_drop"], 5.0)

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)
    ok_active, _ = wait_for_status(
        lambda s: s in ("ADJUSTING_POWER", "EXPANDING_PULSE"),
        history,
        timeout=120,
        ctl_proc=ctl_proc,
    )

    recovered = 0
    pulse_drop_count = 0
    per_fault = []
    for i in range(loops):
        ready_for_inject = wait_for_condition(
            lambda: (
                caget(PV["rf_on"]) is not None
                and int(caget(PV["rf_on"])) == 1
                and caget(PV["arc_status"]) is not None
                and int(caget(PV["arc_status"])) == 1
                and caget(PV["interlock_status"]) is not None
                and int(caget(PV["interlock_status"])) == 1
                and get_status() in ("ADJUSTING_POWER", "EXPANDING_PULSE")
                and caget(PV["pulse_time"]) is not None
                and float(caget(PV["pulse_time"])) >= 0.109
            ),
            history,
            timeout=120,
            interval=0.2,
            ctl_proc=ctl_proc,
        )
        if not ready_for_inject:
            break

        pulse_before = as_float(caget(PV["pulse_time"]))
        per_fault_log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
        caput(PV["trigger_arc"], 1)
        ok_arc0, _ = wait_for_pv(PV["arc_status"], lambda v: v is not None and int(v) == 0, timeout=5)
        ok_recovered = wait_for_condition(
            lambda: (
                caget(PV["arc_status"]) is not None
                and int(caget(PV["arc_status"])) == 1
                and caget(PV["rf_on"]) is not None
                and int(caget(PV["rf_on"])) == 1
                and get_status() in ("INITIALIZING", "ADJUSTING_POWER", "EXPANDING_PULSE")
            ),
            history,
            timeout=90,
            interval=0.2,
            ctl_proc=ctl_proc,
        )
        time.sleep(1.0)
        stable_after_recovery = (
            caget(PV["rf_on"]) is not None
            and int(caget(PV["rf_on"])) == 1
            and caget(PV["arc_status"]) is not None
            and int(caget(PV["arc_status"])) == 1
            and caget(PV["interlock_status"]) is not None
            and int(caget(PV["interlock_status"])) == 1
            and get_status() in ("INITIALIZING", "ADJUSTING_POWER", "EXPANDING_PULSE")
        )
        fault_done_log = "Arc故障处理完成" in read_log_since(per_fault_log_offset)
        pulse_after = as_float(caget(PV["pulse_time"]))
        if pulse_before is not None and pulse_after is not None and pulse_after < pulse_before - 1e-6:
            pulse_drop_count += 1
        per_fault.append(
            {
                "index": i + 1,
                "ready_for_inject": bool(ready_for_inject),
                "arc_to_0": bool(ok_arc0),
                "recovered": bool(ok_recovered),
                "stable_after_recovery": bool(stable_after_recovery),
                "fault_done_log": bool(fault_done_log),
                "pulse_before_s": pulse_before,
                "pulse_after_s": pulse_after,
            }
        )
        if not (ok_arc0 and ok_recovered and stable_after_recovery and fault_done_log):
            break
        recovered += 1
        time.sleep(1.5)

    log_text = read_log_since(log_offset)
    counts = [int(x) for x in re.findall(r"检测到Arc故障 \(第(\d+)次\)", log_text)]
    monotonic = all(b >= a for a, b in zip(counts, counts[1:])) if counts else False
    final_status = get_status()
    controller_alive = ctl_proc.poll() is None

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_active_before_injection": ok_active,
        "all_20_faults_recovered": recovered == loops,
        "fault_count_monotonic": monotonic and len(counts) >= recovered,
        "pulse_drop_observed": pulse_drop_count >= 1,
        "controller_still_running": controller_alive and final_status != "ERROR",
    }
    passed = all(checks.values())
    return {
        "id": "S-5.2",
        "name": "故障-恢复循环压力测试（20次）",
        "output": {
            "status_timeline": history,
            "recovered_count": recovered,
            "pulse_drop_count": pulse_drop_count,
            "fault_count_logs_found": len(counts),
            "fault_count_last": counts[-1] if counts else None,
            "final_status": final_status,
            "per_fault": per_fault,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def s53_concurrent_fault_injection(ctl_proc):
    history = []
    ok_idle, idle_status = reset_to_idle(history, ctl_proc)
    normalize_vacuum()
    configure_fast_conditioning()
    caput(PV["power_targets"], [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    log_offset = CTL_LOG.stat().st_size if CTL_LOG.exists() else 0
    caput(PV["start"], 1)
    ok_active, _ = wait_for_status(
        lambda s: s in ("ADJUSTING_POWER", "EXPANDING_PULSE"),
        history,
        timeout=120,
        ctl_proc=ctl_proc,
    )

    caput(PV["trigger_arc"], 1)
    caput(PV["trigger_interlock"], 1)

    ok_recovered = wait_for_condition(
        lambda: (
            caget(PV["arc_status"]) is not None
            and int(caget(PV["arc_status"])) == 1
            and caget(PV["interlock_status"]) is not None
            and int(caget(PV["interlock_status"])) == 1
            and caget(PV["rf_on"]) is not None
            and int(caget(PV["rf_on"])) == 1
            and get_status() in ("INITIALIZING", "ADJUSTING_POWER", "EXPANDING_PULSE")
        ),
        history,
        timeout=120,
        interval=0.2,
        ctl_proc=ctl_proc,
    )

    log_text = read_log_since(log_offset)
    arc_faults = len(re.findall(r"检测到Arc故障", log_text))
    vac_faults = len(re.findall(r"检测到VacInterlock故障", log_text))
    final_status = get_status()

    checks = {
        "idle_ready": bool(ok_idle and idle_status == "IDLE"),
        "entered_active_before_injection": ok_active,
        "recovered_after_concurrent_injection": ok_recovered,
        "no_deadlock_or_error": final_status != "ERROR",
        "both_fault_callbacks_seen": arc_faults >= 1 and vac_faults >= 1,
    }
    passed = all(checks.values())
    return {
        "id": "S-5.3",
        "name": "并发故障注入测试",
        "output": {
            "status_timeline": history,
            "arc_fault_logs": arc_faults,
            "vac_fault_logs": vac_faults,
            "final_status": final_status,
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def s54_log_integrity():
    text = CTL_LOG.read_text(encoding="utf-8") if CTL_LOG.exists() else ""
    checks = {
        "state_transition_logs": "状态转换" in text,
        "rf_startup_logs": ("RF启动成功" in text) or ("RF启动失败" in text),
        "power_adjust_logs": "Drive:" in text,
        "fault_trigger_logs": "检测到Arc故障" in text,
        "fault_recovery_step_logs": "VacReset" in text and "ResetPWFaultStat1" in text and "ResetPWFaultStat2" in text,
        "pulse_expand_logs": ("展脉宽:" in text) or ("脉宽已达目标" in text),
        "completion_summary_logs": "老练成功完成" in text,
    }
    passed = all(checks.values())
    return {
        "id": "S-5.4",
        "name": "日志完整性验证",
        "output": {
            "controller_log_size_bytes": len(text.encode("utf-8")),
        },
        "checks": checks,
        "conclusion": "通过" if passed else "不通过",
    }


def write_markdown(report):
    lines = []
    lines.append("# 第5章 稳定性测试结果（S-5.1 ~ S-5.4）")
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

            case_51 = s51_long_run_stability(ctl_proc, cycles=10)

            terminate_process(ctl_proc)
            ctl_proc = None
            time.sleep(0.8)

            def _stress_cfg(cfg):
                cfg["loop"]["max_faults"] = 200
                cfg["loop"]["rf_startup"]["max_retry"] = 8
                cfg["loop"]["rf_startup"]["retry_interval"] = 2

            cfg_stress = create_temp_config("config_stress_faults", _stress_cfg)
            tmp_cfgs.append(cfg_stress)
            ctl_proc = start_controller(env, ctl_log_fp, cfg_stress)
            if ctl_proc.poll() is not None:
                raise RuntimeError("controller 进程异常退出（stress配置）")

            case_52 = s52_fault_recovery_stress(ctl_proc, loops=20)
            case_53 = s53_concurrent_fault_injection(ctl_proc)

            case_54 = s54_log_integrity()

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "python": sys.version.split()[0],
                "cases": [case_51, case_52, case_53, case_54],
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

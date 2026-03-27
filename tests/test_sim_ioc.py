#!/usr/bin/env python3
"""
sim_ioc.py 自验证脚本
自动启动 IOC 子进程，用 caproto 同步客户端测试功率仿真和故障注入。

运行:
    python tests/test_sim_ioc.py
"""

import sys
import os
import time
import subprocess

# 确保能 import caproto
try:
    from caproto.sync.client import read, write
except ImportError:
    print("[FAIL] 未安装 caproto，请先: pip install caproto")
    sys.exit(1)

# ==================== PV 名称 ====================
PV_RF_ON        = 'RFQ:LLRF:Con01:Opr_RFOn'
PV_PULSE_CW     = 'RFQ:LLRF:Con01:pulsecw'
PV_PULSE_DRIVE  = 'RFQ:LLRF:Con01:AmpPulseDrive_Set'
PV_CW_DRIVE     = 'RFQ:LLRF:Con01:AmpCWDrive_Set'
PV_POWER        = 'RFQ:LLRF:Con01_RFIn03:Power'
PV_ARC_STATUS   = 'RFQ:LLRF:Con01:Arc_Status_Rd'
PV_INTLK_STATUS = 'RFQ:LLRF:Con01:Interlock_Status_Rd'
PV_RESET_INTLK  = 'RFQ:LLRF:Con01:ResetInterlock'
PV_TRIG_ARC     = 'RFQ:SIM:TriggerArc'
PV_TRIG_INTLK   = 'RFQ:SIM:TriggerInterlock'
PV_VAC4         = 'RFQ:Vac4'

# ==================== 工具函数 ====================

def get(pv, timeout=3):
    resp = read(pv, timeout=timeout)
    return resp.data[0]

def put(pv, value, timeout=3):
    write(pv, [value], timeout=timeout)

def reset_pvs():
    """恢复 IOC 到初始状态"""
    put(PV_RF_ON, 0)
    put(PV_PULSE_DRIVE, 0.0)
    put(PV_CW_DRIVE, 0.0)
    put(PV_PULSE_CW, 0)
    time.sleep(0.5)

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []

def check(name, condition, detail=""):
    tag = PASS if condition else FAIL
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((name, condition))

# ==================== 启动 IOC ====================

def start_ioc():
    sim_path = os.path.join(os.path.dirname(__file__), 'sim_ioc.py')
    proc = subprocess.Popen(
        [sys.executable, sim_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 等待 IOC 就绪（读到 "就绪" 或超时）
    deadline = time.time() + 10
    while time.time() < deadline:
        line = proc.stdout.readline()
        if line:
            print("  [IOC]", line.rstrip())
        if "就绪" in line or "RFQ 仿真 IOC" in line:
            # 额外等一下让所有 PV 注册完成
            time.sleep(1)
            return proc
    return proc

# ==================== 测试用例 ====================

def test_ioc_reachable():
    print("\n--- 1. IOC 连通性 ---")
    try:
        val = get(PV_POWER)
        check("能读取 Power PV", val is not None, f"value={val}")
        val = get(PV_ARC_STATUS)
        check("Arc_Status 初始值=1", val == 1, f"value={val}")
        val = get(PV_INTLK_STATUS)
        check("Interlock_Status 初始值=1", val == 1, f"value={val}")
    except Exception as e:
        check("IOC 连通性", False, str(e))


def test_cw_power_simulation():
    print("\n--- 2. CW 模式功率仿真 (drive=100 → power≈10kW) ---")
    reset_pvs()

    put(PV_PULSE_CW, 1)          # CW 模式
    put(PV_RF_ON, 1)
    put(PV_CW_DRIVE, 100.0)

    # 一阶低通，等待收敛（理论稳态10kW，10步后=10×0.3+...≈9.9kW）
    print("  等待功率收敛 (3s)...")
    time.sleep(3)

    power = get(PV_POWER)
    check("CW drive=100 → power 在 [8, 12] kW",
          power is not None and 8.0 <= power <= 12.0,
          f"power={power:.3f} kW")


def test_pulse_power_simulation():
    print("\n--- 3. 脉冲模式功率仿真 (drive=500 → power≈50kW) ---")
    reset_pvs()

    put(PV_PULSE_CW, 0)          # 脉冲模式
    put(PV_RF_ON, 1)
    put(PV_PULSE_DRIVE, 500.0)

    print("  等待功率收敛 (5s)...")
    time.sleep(5)

    power = get(PV_POWER)
    check("脉冲 drive=500 → power 在 [40, 55] kW",
          power is not None and 40.0 <= power <= 55.0,
          f"power={power:.3f} kW")


def test_rf_off_decay():
    print("\n--- 4. RF 关闭后功率衰减 ---")
    reset_pvs()

    # 先建立功率
    put(PV_PULSE_CW, 1)
    put(PV_RF_ON, 1)
    put(PV_CW_DRIVE, 500.0)
    time.sleep(4)
    power_before = get(PV_POWER)
    check("关闭前 power > 10 kW", power_before is not None and power_before > 10,
          f"power={power_before:.2f} kW")

    # 关闭 RF
    put(PV_RF_ON, 0)
    time.sleep(2)
    power_after = get(PV_POWER)
    check("RF关闭后 power < 1 kW",
          power_after is not None and power_after < 1.0,
          f"power={power_after:.3f} kW")


def test_trigger_arc():
    print("\n--- 5. 弧光故障注入 (TriggerArc=1) ---")
    reset_pvs()
    put(PV_RF_ON, 1)
    time.sleep(0.3)

    put(PV_TRIG_ARC, 1)
    time.sleep(0.5)

    arc = get(PV_ARC_STATUS)
    rf  = get(PV_RF_ON)
    trig = get(PV_TRIG_ARC)

    check("Arc_Status → 0",      arc == 0,  f"arc_status={arc}")
    check("RF_On → 0",           rf == 0,   f"rf_on={rf}")
    check("TriggerArc 自动清零", trig == 0, f"trigger={trig}")


def test_trigger_interlock():
    print("\n--- 6. 联锁故障注入 (TriggerInterlock=1) ---")
    reset_pvs()
    put(PV_RF_ON, 1)
    time.sleep(0.3)

    put(PV_TRIG_INTLK, 1)
    time.sleep(0.5)

    intlk = get(PV_INTLK_STATUS)
    rf    = get(PV_RF_ON)
    trig  = get(PV_TRIG_INTLK)

    check("Interlock_Status → 0",    intlk == 0, f"interlock={intlk}")
    check("RF_On → 0",               rf == 0,    f"rf_on={rf}")
    check("TriggerInterlock 自动清零", trig == 0, f"trigger={trig}")


def test_fault_reset():
    print("\n--- 7. 故障复位 (ResetInterlock=1 → 延迟1s → 恢复) ---")
    # 先触发故障
    put(PV_TRIG_ARC, 1)
    time.sleep(0.5)
    check("复位前 Arc_Status=0", get(PV_ARC_STATUS) == 0,
          f"arc={get(PV_ARC_STATUS)}")

    # 复位
    put(PV_RESET_INTLK, 1)
    print("  等待复位延迟 (2s)...")
    time.sleep(2)

    arc  = get(PV_ARC_STATUS)
    intlk = get(PV_INTLK_STATUS)
    check("复位后 Arc_Status=1",      arc == 1,  f"arc={arc}")
    check("复位后 Interlock_Status=1", intlk == 1, f"intlk={intlk}")


def test_drive_zero_power_zero():
    print("\n--- 8. Drive=0 时 power 归零 ---")
    reset_pvs()
    put(PV_PULSE_CW, 1)
    put(PV_RF_ON, 1)
    put(PV_CW_DRIVE, 0.0)
    time.sleep(3)

    power = get(PV_POWER)
    check("drive=0 → power < 0.1 kW",
          power is not None and power < 0.1,
          f"power={power:.4f} kW")


# ==================== 主程序 ====================

if __name__ == '__main__':
    project_root = os.path.join(os.path.dirname(__file__), '..')
    sim_path = os.path.join(project_root, 'tests', 'sim_ioc.py')

    print("=" * 55)
    print("RFQ sim_ioc.py 自动验证脚本")
    print("=" * 55)
    print("启动仿真 IOC 子进程...")
    proc = start_ioc()

    # 等待 IOC 端口监听就绪
    time.sleep(2)

    try:
        test_ioc_reachable()
        test_cw_power_simulation()
        test_pulse_power_simulation()
        test_rf_off_decay()
        test_trigger_arc()
        test_trigger_interlock()
        test_fault_reset()
        test_drive_zero_power_zero()
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        proc.terminate()
        proc.wait()

    # 汇总
    total  = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed
    print("\n" + "=" * 55)
    print(f"结果: {passed}/{total} 通过", end="")
    if failed:
        print(f"  (\033[31m{failed} 失败\033[0m)")
        for name, ok in results:
            if not ok:
                print(f"  [FAIL] {name}")
    else:
        print("  \033[32m全部通过\033[0m")
    print("=" * 55)

    sys.exit(0 if failed == 0 else 1)

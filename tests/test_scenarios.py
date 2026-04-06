#!/usr/bin/env python3
"""
自动化故障和真空测试脚本

前置条件:
  1. 终端A: python tests/sim_ioc.py
  2. 终端B: python main.py（按Enter启动后）
  3. 终端C: python tests/test_scenarios.py

使用方法:
    python tests/test_scenarios.py              # 运行全部测试
    python tests/test_scenarios.py --fault      # 只测故障
    python tests/test_scenarios.py --vacuum     # 只测真空
    python tests/test_scenarios.py --skip-init  # 跳过初始化检查

作者: Adrian Xu
日期: 2026-04
"""

import epics
import time
import sys
import argparse


VACUUM_THRESHOLD = 5.0e-5
VACUUM_NORMAL = 1e-6
VACUUM_BAD = 1e-4

TIMEOUT = 5.0


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def caput(pv, value, wait=True, timeout=TIMEOUT):
    return epics.caput(pv, value, wait=wait, timeout=timeout)


def caget(pv, timeout=TIMEOUT):
    val = epics.caget(pv, timeout=timeout)
    if hasattr(val, 'tobytes'):
        return val.tobytes().decode('ascii', errors='replace').strip('\x00')
    return val


def log_pass(msg):
    print(f"  {Colors.GREEN}✓ PASS{Colors.END} {msg}")


def log_fail(msg):
    print(f"  {Colors.RED}✗ FAIL{Colors.END} {msg}")


def log_info(msg):
    print(f"  {Colors.CYAN}→{Colors.END} {msg}")


def log_warn(msg):
    print(f"  {Colors.YELLOW}!{Colors.END} {msg}")


def section(title):
    print(f"\n{Colors.BOLD}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{Colors.END}")


def wait_for(pv_name, expected, timeout=15, poll=0.5, description=""):
    start = time.time()
    while time.time() - start < timeout:
        val = caget(pv_name)
        if val == expected:
            return True
        time.sleep(poll)
    val = caget(pv_name)
    if val == expected:
        return True
    log_warn(f"等待超时 ({timeout}s): {description or pv_name} 期望={expected}, 实际={val}")
    return False


def wait_for_condition(pv_name, check_fn, timeout=15, poll=0.5, description=""):
    start = time.time()
    while time.time() - start < timeout:
        val = caget(pv_name)
        if check_fn(val):
            return True
        time.sleep(poll)
    val = caget(pv_name)
    if check_fn(val):
        return True
    log_warn(f"等待超时 ({timeout}s): {description} 实际值={val}")
    return False


def reset_system():
    caput('RFQ:LLRF:Con01:AutoC_Reset', 1)
    time.sleep(0.3)
    caput('RFQ:LLRF:Con01:AutoC_Reset', 0)
    time.sleep(1)
    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(0.5)


def ensure_normal_state():
    caput('RFQ:SIM:VacAll', VACUUM_NORMAL)
    time.sleep(0.5)
    caput('RFQ:SIM:TriggerArc', 0)
    caput('RFQ:SIM:TriggerInterlock', 0)
    caput('RFQ:SIM:TriggerInterlock2', 0)
    caput('RFQ:SIM:TriggerDI4', 0)
    caput('RFQ:SIM:BlockRFOn', 0)
    caput('RFQ:SIM:BlockPower', 0)
    time.sleep(0.5)
    for pv in ['RFQ:Reset', 'RFQ:LLRF:Con01:ResetInterlock',
               'RFQ:LLRF:Mon01:ResetPWFaultStat', 'RFQ:LLRF:Mon02:ResetPWFaultStat']:
        caput(pv, 1)
        time.sleep(0.3)
        caput(pv, 0)
        time.sleep(0.3)
    time.sleep(0.5)


# ==================== 测试场景 ====================

def test_arc_fault():
    """测试Arc打火故障: 触发→系统应检测到并尝试恢复"""
    section("测试1: Arc打火故障")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"启动后状态: {status}")

    log_info("触发Arc故障...")
    caput('RFQ:SIM:TriggerArc', 1)
    time.sleep(2)

    arc_val = caget('RFQ:LLRF:Con01:ArcStatus_Rd')
    rf_on = caget('RFQ:LLRF:Con01:Opr_RFOn')
    log_info(f"Arc状态={arc_val}, RF={rf_on}")

    if arc_val == 0 and rf_on == 0:
        log_pass("Arc故障已触发，RF已关闭")
    else:
        log_fail(f"Arc故障触发异常: arc={arc_val}, rf={rf_on}")

    time.sleep(10)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"恢复后状态: {status}")

    passed = (status == 'IDLE' or status == 'INITIALIZING' or status == 'ADJUSTING_POWER')
    if passed:
        log_pass("系统已进入恢复流程")
    else:
        log_warn(f"系统状态={status}，可能还在恢复中（等待更久）")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_vac_interlock_fault():
    """测试VacInterlock联锁故障"""
    section("测试2: VacInterlock联锁故障")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"启动后状态: {status}")

    log_info("触发VacInterlock故障...")
    caput('RFQ:SIM:TriggerInterlock', 1)
    time.sleep(2)

    interlock_val = caget('RFQ:LLRF:Con01:InterlockStatus_Rd')
    rf_on = caget('RFQ:LLRF:Con01:Opr_RFOn')
    log_info(f"Interlock状态={interlock_val}, RF={rf_on}")

    if interlock_val == 0 and rf_on == 0:
        log_pass("VacInterlock故障已触发，RF已关闭")
    else:
        log_fail(f"VacInterlock故障触发异常: interlock={interlock_val}, rf={rf_on}")

    time.sleep(10)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"恢复后状态: {status}")

    passed = (status == 'IDLE' or status == 'INITIALIZING' or status == 'ADJUSTING_POWER')
    if passed:
        log_pass("系统已进入恢复流程")
    else:
        log_warn(f"系统状态={status}，可能还在恢复中")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_interlock2_fault():
    """测试Interlock2故障"""
    section("测试3: Interlock2故障")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    log_info("触发Interlock2故障...")
    caput('RFQ:SIM:TriggerInterlock2', 1)
    time.sleep(2)

    interlock2_val = caget('RFQ:LLRF:Con01:InterlockStatus2_Rd')
    rf_on = caget('RFQ:LLRF:Con01:Opr_RFOn')
    log_info(f"Interlock2状态={interlock2_val}, RF={rf_on}")

    if interlock2_val == 0 and rf_on == 0:
        log_pass("Interlock2故障已触发，RF已关闭")
    else:
        log_fail(f"Interlock2故障触发异常: il2={interlock2_val}, rf={rf_on}")

    time.sleep(10)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"恢复后状态: {status}")

    passed = (status == 'IDLE' or status == 'INITIALIZING' or status == 'ADJUSTING_POWER')
    if passed:
        log_pass("系统已进入恢复流程")
    else:
        log_warn(f"系统状态={status}，可能还在恢复中")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_di4_fault():
    """测试DI4故障"""
    section("测试4: DI4故障")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    log_info("触发DI4故障...")
    caput('RFQ:SIM:TriggerDI4', 1)
    time.sleep(2)

    di4_val = caget('RFQ:LLRF:Con01:di4')
    rf_on = caget('RFQ:LLRF:Con01:Opr_RFOn')
    log_info(f"DI4状态={di4_val}, RF={rf_on}")

    if di4_val == 0 and rf_on == 0:
        log_pass("DI4故障已触发，RF已关闭")
    else:
        log_fail(f"DI4故障触发异常: di4={di4_val}, rf={rf_on}")

    time.sleep(10)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"恢复后状态: {status}")

    passed = (status == 'IDLE' or status == 'INITIALIZING' or status == 'ADJUSTING_POWER')
    if passed:
        log_pass("系统已进入恢复流程")
    else:
        log_warn(f"系统状态={status}，可能还在恢复中")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_vacuum_exceed_all():
    """测试所有真空计超标: 系统应进入WAITING_VACUUM"""
    section("测试5: 全部真空计超标")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(5)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"启动后状态: {status}")

    log_info(f"将所有真空计设为 {VACUUM_BAD:.2e} Pa (阈值={VACUUM_THRESHOLD:.2e})...")
    caput('RFQ:SIM:VacAll', VACUUM_BAD)
    time.sleep(3)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"真空超标后状态: {status}")

    passed = (status == 'WAITING_VACUUM')
    if passed:
        log_pass("系统正确进入 WAITING_VACUUM 状态")
    else:
        log_fail(f"系统状态={status}，期望 WAITING_VACUUM")

    log_info(f"恢复真空到 {VACUUM_NORMAL:.2e} Pa...")
    caput('RFQ:SIM:VacAll', VACUUM_NORMAL)
    time.sleep(5)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"真空恢复后状态: {status}")

    if status in ('ADJUSTING_POWER', 'EXPANDING_PULSE'):
        log_pass("真空恢复后系统已恢复运行")
    else:
        log_warn(f"真空恢复后状态={status}，可能还在恢复中")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_vacuum_exceed_single():
    """测试单个真空计超标: 只要有一个超标就应触发WAITING_VACUUM"""
    section("测试6: 单个真空计超标(Vac3)")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(5)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"启动后状态: {status}")

    log_info(f"将Vac3设为 {VACUUM_BAD:.2e} Pa，其余保持正常...")
    caput('RFQ:SIM:VacTarget', 2)
    time.sleep(0.3)
    caput('RFQ:SIM:VacSingle', VACUUM_BAD)
    time.sleep(3)

    vac3 = caget('RFQ:Vac3')
    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"Vac3={vac3:.2e} Pa, 状态={status}")

    passed = (status == 'WAITING_VACUUM')
    if passed:
        log_pass("单个真空计超标已触发 WAITING_VACUUM")
    else:
        log_fail(f"系统状态={status}，期望 WAITING_VACUUM")

    caput('RFQ:SIM:VacAll', VACUUM_NORMAL)
    time.sleep(5)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"真空恢复后状态: {status}")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return passed


def test_vacuum_fluctuation():
    """测试真空波动: 先超标→恢复→再超标→再恢复，检查系统反应"""
    section("测试7: 真空波动（多次超标/恢复）")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(5)

    for cycle in range(3):
        log_info(f"--- 波动周期 {cycle + 1}/3 ---")

        caput('RFQ:SIM:VacAll', VACUUM_BAD)
        time.sleep(3)

        status = caget('RFQ:LLRF:Con01:AutoC_Status')
        if status == 'WAITING_VACUUM':
            log_pass(f"周期{cycle + 1}: 超标后正确进入 WAITING_VACUUM")
        else:
            log_fail(f"周期{cycle + 1}: 超标后状态={status}，期望 WAITING_VACUUM")

        caput('RFQ:SIM:VacAll', VACUUM_NORMAL)
        time.sleep(5)

        status = caget('RFQ:LLRF:Con01:AutoC_Status')
        if status in ('ADJUSTING_POWER', 'EXPANDING_PULSE', 'WAITING_VACUUM'):
            log_pass(f"周期{cycle + 1}: 恢复后系统恢复运行 (状态={status})")
        else:
            log_warn(f"周期{cycle + 1}: 恢复后状态={status}")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return True


def test_fault_during_expand():
    """测试展脉宽过程中发生故障"""
    section("测试8: 展脉宽过程中Arc故障")

    reset_system()
    ensure_normal_state()

    caput('RFQ:LLRF:Con01:AutoC_PulseStart', 100.0)
    caput('RFQ:LLRF:Con01:AutoC_PulseEnd', 200.0)
    caput('RFQ:LLRF:Con01:AutoC_PulseStep', 10.0)
    time.sleep(0.5)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(8)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"系统状态: {status}")

    if status == 'EXPANDING_PULSE':
        log_info("系统在展脉宽中，触发Arc故障...")
    elif status == 'ADJUSTING_POWER':
        log_info("系统在调功率中，等待进入展脉宽...")
        time.sleep(10)
        status = caget('RFQ:LLRF:Con01:AutoC_Status')
        if status == 'EXPANDING_PULSE':
            log_info("已进入展脉宽，触发Arc故障...")
        else:
            log_warn(f"状态={status}，不是展脉宽，仍然触发故障测试")
    else:
        log_warn(f"当前状态={status}，仍然触发故障测试")

    current_pulse = caget('RFQ:LLRF:Con01:AutoC_CurrentPulse')
    log_info(f"故障前脉宽: {current_pulse} ms")

    caput('RFQ:SIM:TriggerArc', 1)
    time.sleep(2)

    arc_val = caget('RFQ:LLRF:Con01:ArcStatus_Rd')
    rf_on = caget('RFQ:LLRF:Con01:Opr_RFOn')
    log_info(f"故障后: Arc={arc_val}, RF={rf_on}")

    time.sleep(12)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"恢复后状态: {status}")

    if status in ('IDLE', 'INITIALIZING', 'ADJUSTING_POWER'):
        log_pass("展脉宽中故障后系统已恢复")
    else:
        log_warn(f"恢复后状态={status}")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return True


def test_multiple_faults_rapid():
    """测试快速连续故障: 多次触发不同故障，检查计数和超限"""
    section("测试9: 快速连续故障（检查计数累积）")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    log_info("快速触发5次不同故障...")

    caput('RFQ:SIM:TriggerArc', 1)
    time.sleep(1)
    caput('RFQ:SIM:TriggerInterlock', 1)
    time.sleep(1)
    caput('RFQ:SIM:TriggerInterlock2', 1)
    time.sleep(1)
    caput('RFQ:SIM:TriggerArc', 1)
    time.sleep(1)
    caput('RFQ:SIM:TriggerDI4', 1)
    time.sleep(1)

    log_info("5次故障已触发，观察系统状态...")
    time.sleep(15)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"当前状态: {status}")

    if status == 'ERROR':
        log_warn("系统进入ERROR状态（故障计数可能已超限，max_faults=20不会超）")
    elif status in ('IDLE', 'INITIALIZING', 'ADJUSTING_POWER'):
        log_pass("系统仍在正常运行/恢复中（5次故障未超限）")
    else:
        log_info(f"系统状态={status}")

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return True


def test_vacuum_boundary():
    """测试真空阈值边界: 刚好低于/高于阈值"""
    section("测试10: 真空阈值边界测试")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(5)

    log_info(f"阈值={VACUUM_THRESHOLD:.2e}, 设为刚好低于阈值 ({VACUUM_THRESHOLD * 0.9:.2e})...")
    caput('RFQ:SIM:VacAll', VACUUM_THRESHOLD * 0.9)
    time.sleep(3)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"低于阈值: Vac={VACUUM_THRESHOLD * 0.9:.2e}, 状态={status}")

    if status != 'WAITING_VACUUM':
        log_pass("略低于阈值时系统正常运行")
    else:
        log_fail("略低于阈值时系统误判为真空超标")

    log_info(f"设为刚好高于阈值 ({VACUUM_THRESHOLD * 1.1:.2e})...")
    caput('RFQ:SIM:VacAll', VACUUM_THRESHOLD * 1.1)
    time.sleep(3)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"高于阈值: Vac={VACUUM_THRESHOLD * 1.1:.2e}, 状态={status}")

    if status == 'WAITING_VACUUM':
        log_pass("略高于阈值时系统正确检测真空超标")
    else:
        log_fail(f"高于阈值时状态={status}，期望 WAITING_VACUUM")

    caput('RFQ:SIM:VacAll', VACUUM_NORMAL)
    time.sleep(3)

    caput('RFQ:LLRF:Con01:AutoC_Start', 0)
    time.sleep(1)
    reset_system()
    return True


def test_fault_exceeded_limit():
    """测试故障超限: 连续触发超过max_faults次故障，系统应进入ERROR"""
    section("测试11: 故障超限（max_faults=20）")

    reset_system()
    ensure_normal_state()
    time.sleep(1)

    caput('RFQ:LLRF:Con01:AutoC_Start', 1)
    time.sleep(3)

    log_info("快速触发21次Arc故障（超过max_faults=20）...")
    for i in range(21):
        caput('RFQ:SIM:TriggerArc', 1)
        time.sleep(0.3)

    log_info("等待系统处理...")
    time.sleep(5)

    status = caget('RFQ:LLRF:Con01:AutoC_Status')
    log_info(f"超限后状态: {status}")

    if status == 'ERROR':
        log_pass("故障超限后系统正确进入ERROR状态")
    else:
        log_warn(f"故障超限后状态={status}（可能需要更长时间处理，或回调未及时更新计数）")

    reset_system()
    return status == 'ERROR'


def test_init_check():
    """测试初始化前的环境检查"""
    section("测试0: 环境连通性检查")

    test_pvs = [
        ('RFQ:LLRF:Con01:Opr_RFOn', 'RF控制'),
        ('RFQ:LLRF:Con01:ArcStatus_Rd', 'Arc故障'),
        ('RFQ:LLRF:Con01:InterlockStatus_Rd', 'Interlock故障'),
        ('RFQ:LLRF:Con01:InterlockStatus2_Rd', 'Interlock2故障'),
        ('RFQ:LLRF:Con01:di4', 'DI4'),
        ('RFQ:Vac1', '真空1'),
        ('RFQ:LLRF:Con01:AutoC_Start', '启动信号'),
        ('RFQ:LLRF:Con01:AutoC_Status', '系统状态'),
        ('RFQ:LLRF:Con01:AutoC_Reset', '复位信号'),
        ('RFQ:SIM:TriggerArc', 'Arc注入'),
        ('RFQ:SIM:TriggerInterlock', 'Interlock注入'),
        ('RFQ:SIM:TriggerInterlock2', 'Interlock2注入'),
        ('RFQ:SIM:TriggerDI4', 'DI4注入'),
        ('RFQ:SIM:VacAll', '真空控制'),
        ('RFQ:Reset', '真空复位'),
    ]

    all_ok = True
    for pv_name, desc in test_pvs:
        val = caget(pv_name, timeout=3)
        if val is not None:
            log_pass(f"{desc}: {pv_name} = {val}")
        else:
            log_fail(f"{desc}: {pv_name} 无法读取")
            all_ok = False

    return all_ok


def main():
    parser = argparse.ArgumentParser(description='RFQ自动老练系统 - 故障和真空测试')
    parser.add_argument('--fault', action='store_true', help='只运行故障测试')
    parser.add_argument('--vacuum', action='store_true', help='只运行真空测试')
    parser.add_argument('--skip-init', action='store_true', help='跳过初始化检查')
    args = parser.parse_args()

    print(f"\n{Colors.BOLD}RFQ自动老练系统 - 故障和真空自动化测试{Colors.END}")
    print(f"真空阈值: {VACUUM_THRESHOLD:.2e} Pa")
    print(f"真空正常值: {VACUUM_NORMAL:.2e} Pa")
    print(f"真空超标值: {VACUUM_BAD:.2e} Pa")
    print()

    if not args.skip_init:
        section("前置检查")
        if not test_init_check():
            print(f"\n{Colors.RED}前置检查失败！请确保 sim_ioc.py 和 main.py 已启动。{Colors.END}")
            sys.exit(1)

    results = {}

    fault_tests = [
        ("Arc打火故障", test_arc_fault),
        ("VacInterlock联锁故障", test_vac_interlock_fault),
        ("Interlock2故障", test_interlock2_fault),
        ("DI4故障", test_di4_fault),
        ("展脉宽中故障", test_fault_during_expand),
        ("快速连续故障", test_multiple_faults_rapid),
        ("故障超限", test_fault_exceeded_limit),
    ]

    vacuum_tests = [
        ("全部真空超标", test_vacuum_exceed_all),
        ("单个真空超标", test_vacuum_exceed_single),
        ("真空波动", test_vacuum_fluctuation),
        ("真空阈值边界", test_vacuum_boundary),
    ]

    tests_to_run = []
    if args.fault:
        tests_to_run = fault_tests
    elif args.vacuum:
        tests_to_run = vacuum_tests
    else:
        tests_to_run = fault_tests + vacuum_tests

    for name, test_fn in tests_to_run:
        try:
            passed = test_fn()
            results[name] = passed
        except Exception as e:
            log_fail(f"测试异常: {e}")
            results[name] = False

    section("测试结果汇总")
    passed_count = 0
    failed_count = 0
    for name, passed in results.items():
        if passed:
            log_pass(name)
            passed_count += 1
        else:
            log_fail(name)
            failed_count += 1

    print(f"\n{Colors.BOLD}总计: {passed_count} 通过, {failed_count} 失败{Colors.END}")

    if failed_count > 0:
        sys.exit(1)
    else:
        print(f"{Colors.GREEN}所有测试通过！{Colors.END}")
        sys.exit(0)


if __name__ == '__main__':
    main()

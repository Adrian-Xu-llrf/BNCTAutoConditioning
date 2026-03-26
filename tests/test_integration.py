#!/usr/bin/env python3
"""
RFQ 自动老练系统 - 集成测试脚本
需要先启动 sim_ioc.py 再运行本测试。

使用方法:
    # 终端A: 启动仿真IOC
    python tests/sim_ioc.py

    # 终端B: 运行测试
    python -m pytest tests/test_integration.py -v -s

    # 运行单个测试
    python -m pytest tests/test_integration.py::TestNormalStartup -v -s

作者: Adrian Xu
日期: 2025-11
"""

import time
import threading
import logging
import pytest
import epics

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rfq.core.config import Config
from rfq.core.state import RFQState
from rfq.core.controller import RFQController

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('RFQ.Test')

# ==================== PV 名称常量 ====================
PV_START = 'RFQ:LLRF:Con01:AutoC_Start'
PV_RESET = 'RFQ:LLRF:Con01:AutoC_Reset'
PV_STATUS = 'RFQ:LLRF:Con01:AutoC_Status'
PV_RF_ON = 'RFQ:LLRF:Con01:Opr_RFOn'
PV_POWER = 'RFQ:LLRF:Con01_RFIn03:Power'
PV_TARGET_POWER = 'RFQ:LLRF:Con01:AutoC_TargetPower'
PV_INIT_DRIVE = 'RFQ:LLRF:Con01:AutoC_InitDrive'
PV_PULSE_CW = 'RFQ:LLRF:Con01:pulsecw'
PV_PULSE_DRIVE = 'RFQ:LLRF:Con01:AmpPulseDrive_Set'
PV_CW_DRIVE = 'RFQ:LLRF:Con01:AmpCWDrive_Set'
PV_PULSE_TIME = 'RFQ:LLRF:Con01:RFPulseOnTime_Set'
PV_PULSE_START = 'RFQ:LLRF:Con01:AutoC_PulseStart'
PV_PULSE_END = 'RFQ:LLRF:Con01:AutoC_PulseEnd'
PV_PULSE_STEP = 'RFQ:LLRF:Con01:AutoC_PulseStep'
PV_DRIVE_STEP1 = 'RFQ:LLRF:Con01:AutoC_DriveStep1'
PV_DRIVE_STEP2 = 'RFQ:LLRF:Con01:AutoC_DriveStep2'
PV_MARGIN_LARGE = 'RFQ:LLRF:Con01:AutoC_MarginLarge'
PV_MARGIN_SMALL = 'RFQ:LLRF:Con01:AutoC_MarginSmall'
PV_WAIT_TIME = 'RFQ:LLRF:Con01:WaitTime_Set'
PV_VAC4 = 'RFQ:Vac4'
PV_VAC_CAV = 'IA-RFQ-CR:VG01_CH02_CavE:Pres'
PV_TRIGGER_ARC = 'RFQ:SIM:TriggerArc'
PV_TRIGGER_INTERLOCK = 'RFQ:SIM:TriggerInterlock'
PV_ARC_STATUS = 'RFQ:LLRF:Con01:Arc_Status'
PV_INTERLOCK_STATUS = 'RFQ:LLRF:Con01:Interlock_Status'

# ==================== 测试超时常量 ====================
TIMEOUT_SHORT = 10     # 短超时（秒）
TIMEOUT_MEDIUM = 30    # 中等超时
TIMEOUT_LONG = 120     # 长超时（功率收敛等）
POLL_INTERVAL = 0.5    # 轮询间隔


def wait_for_state(controller, target_state, timeout=TIMEOUT_MEDIUM):
    """等待控制器到达指定状态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if controller.current_state == target_state:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_state_not(controller, exclude_state, timeout=TIMEOUT_MEDIUM):
    """等待控制器离开指定状态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if controller.current_state != exclude_state:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_pv(pv_name, expected_value, timeout=TIMEOUT_SHORT, tolerance=None):
    """等待PV达到预期值"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        val = epics.caget(pv_name, timeout=2.0)
        if tolerance is not None:
            if val is not None and abs(val - expected_value) < tolerance:
                return True
        else:
            if val == expected_value:
                return True
        time.sleep(POLL_INTERVAL)
    return False


def run_controller_background(controller):
    """在后台线程运行控制器"""
    t = threading.Thread(target=controller.run, daemon=True, name='RFQController')
    t.start()
    return t


def reset_all_pvs():
    """重置所有PV到初始状态"""
    epics.caput(PV_START, 0, wait=True)
    epics.caput(PV_RESET, 0, wait=True)
    epics.caput(PV_RF_ON, 0, wait=True)
    epics.caput(PV_PULSE_DRIVE, 0.0, wait=True)
    epics.caput(PV_CW_DRIVE, 0.0, wait=True)
    epics.caput(PV_PULSE_CW, 0, wait=True)
    epics.caput(PV_PULSE_TIME, 100.0, wait=True)
    epics.caput(PV_TARGET_POWER, 50.0, wait=True)
    epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
    epics.caput(PV_PULSE_START, 100.0, wait=True)
    epics.caput(PV_PULSE_END, 1000.0, wait=True)
    epics.caput(PV_PULSE_STEP, 50.0, wait=True)
    epics.caput(PV_DRIVE_STEP1, 10.0, wait=True)
    epics.caput(PV_DRIVE_STEP2, 2.0, wait=True)
    epics.caput(PV_MARGIN_LARGE, 5.0, wait=True)
    epics.caput(PV_MARGIN_SMALL, 1.0, wait=True)
    epics.caput(PV_WAIT_TIME, 0.5, wait=True)
    epics.caput(PV_VAC4, 1e-6, wait=True)
    epics.caput(PV_VAC_CAV, 1e-6, wait=True)
    epics.caput(PV_ARC_STATUS, 1, wait=True)
    epics.caput(PV_INTERLOCK_STATUS, 1, wait=True)
    time.sleep(1)


# ==================== Fixtures ====================

@pytest.fixture(scope='session')
def check_ioc():
    """验证仿真IOC是否在运行"""
    val = epics.caget(PV_STATUS, timeout=5.0)
    if val is None:
        pytest.skip(
            "仿真IOC未运行。请先在另一个终端执行: python tests/sim_ioc.py"
        )


@pytest.fixture(autouse=True)
def setup_teardown(check_ioc):
    """每个测试前后重置环境"""
    reset_all_pvs()
    yield
    # 测试后清理: 停止老练，关闭RF
    epics.caput(PV_START, 0, wait=True)
    epics.caput(PV_RF_ON, 0, wait=True)
    time.sleep(1)


@pytest.fixture
def config():
    """加载配置"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    return Config(config_path)


@pytest.fixture
def controller(config):
    """创建控制器实例"""
    ctrl = RFQController(config)
    yield ctrl
    # 确保控制器停止
    if ctrl.current_state not in (RFQState.ERROR, RFQState.STOPPED, RFQState.COMPLETED):
        ctrl.set_state(RFQState.STOPPED)


# ==================== 测试场景 ====================

class TestIOCConnection:
    """测试 IOC 连接和基本 PV 读写"""

    def test_read_status_pv(self):
        """验证能读取状态PV"""
        val = epics.caget(PV_STATUS, timeout=3.0)
        assert val is not None, "无法读取 AutoC_Status PV"

    def test_read_write_target_power(self):
        """验证目标功率PV可读可写"""
        epics.caput(PV_TARGET_POWER, 42.0, wait=True)
        time.sleep(0.5)
        val = epics.caget(PV_TARGET_POWER, timeout=3.0)
        assert abs(val - 42.0) < 0.1, f"目标功率写入/读取不一致: {val}"

    def test_vacuum_pv_initial(self):
        """验证真空PV初始值正常"""
        v1 = epics.caget(PV_VAC4, timeout=3.0)
        v2 = epics.caget(PV_VAC_CAV, timeout=3.0)
        assert v1 is not None and v1 < 1e-4, f"Vac4 初始值异常: {v1}"
        assert v2 is not None and v2 < 1e-4, f"VacCav 初始值异常: {v2}"

    def test_fault_pv_initial(self):
        """验证故障PV初始值（正常=1）"""
        arc = epics.caget(PV_ARC_STATUS, timeout=3.0)
        intlk = epics.caget(PV_INTERLOCK_STATUS, timeout=3.0)
        assert arc == 1, f"Arc初始状态异常: {arc}"
        assert intlk == 1, f"Interlock初始状态异常: {intlk}"


class TestPowerSimulation:
    """测试功率仿真模型"""

    def test_power_responds_to_drive(self):
        """验证功率随Drive变化: drive=500 -> power≈50kW"""
        epics.caput(PV_PULSE_CW, 0, wait=True)  # CW模式
        epics.caput(PV_RF_ON, 1, wait=True)
        epics.caput(PV_CW_DRIVE, 500.0, wait=True)

        # 等待功率收敛 (一阶低通, 需要多个时间常数)
        time.sleep(5)
        power = epics.caget(PV_POWER, timeout=3.0)
        assert power is not None, "无法读取功率"
        assert abs(power - 50.0) < 5.0, f"功率未收敛到50kW: {power:.2f}kW"

    def test_power_decay_on_rf_off(self):
        """验证RF关闭后功率衰减"""
        # 先建立功率
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_RF_ON, 1, wait=True)
        epics.caput(PV_CW_DRIVE, 500.0, wait=True)
        time.sleep(5)

        # 关闭RF
        epics.caput(PV_RF_ON, 0, wait=True)
        time.sleep(3)

        power = epics.caget(PV_POWER, timeout=3.0)
        assert power is not None and power < 1.0, f"RF关闭后功率未衰减: {power:.2f}kW"

    def test_power_zero_when_drive_zero(self):
        """验证Drive=0时功率为0"""
        epics.caput(PV_RF_ON, 1, wait=True)
        epics.caput(PV_CW_DRIVE, 0.0, wait=True)
        time.sleep(3)

        power = epics.caget(PV_POWER, timeout=3.0)
        assert power is not None and power < 0.1, f"Drive=0时功率不为零: {power:.2f}kW"


class TestFaultInjection:
    """测试故障注入机制"""

    def test_trigger_arc_fault(self):
        """验证弧光故障注入: arc_status→0, rf_on→0"""
        epics.caput(PV_RF_ON, 1, wait=True)
        time.sleep(0.5)

        epics.caput(PV_TRIGGER_ARC, 1, wait=True)
        time.sleep(1)

        arc = epics.caget(PV_ARC_STATUS, timeout=3.0)
        rf_on = epics.caget(PV_RF_ON, timeout=3.0)
        assert arc == 0, f"弧光故障未触发: arc_status={arc}"
        assert rf_on == 0, f"弧光故障后RF未关闭: rf_on={rf_on}"

    def test_trigger_interlock_fault(self):
        """验证联锁故障注入: interlock_status→0, rf_on→0"""
        epics.caput(PV_RF_ON, 1, wait=True)
        time.sleep(0.5)

        epics.caput(PV_TRIGGER_INTERLOCK, 1, wait=True)
        time.sleep(1)

        intlk = epics.caget(PV_INTERLOCK_STATUS, timeout=3.0)
        rf_on = epics.caget(PV_RF_ON, timeout=3.0)
        assert intlk == 0, f"联锁故障未触发: interlock_status={intlk}"
        assert rf_on == 0, f"联锁故障后RF未关闭: rf_on={rf_on}"

    def test_fault_reset_interlock(self):
        """验证联锁故障复位"""
        # 先触发故障
        epics.caput(PV_TRIGGER_ARC, 1, wait=True)
        time.sleep(1)

        # 执行复位
        epics.caput('RFQ:LLRF:Con01:ResetInterlock', 1, wait=True)
        time.sleep(2)

        arc = epics.caget(PV_ARC_STATUS, timeout=3.0)
        intlk = epics.caget(PV_INTERLOCK_STATUS, timeout=3.0)
        assert arc == 1, f"弧光复位失败: arc_status={arc}"
        assert intlk == 1, f"联锁复位失败: interlock_status={intlk}"

    def test_trigger_pv_auto_clear(self):
        """验证触发PV自动清零"""
        epics.caput(PV_TRIGGER_ARC, 1, wait=True)
        time.sleep(1)

        val = epics.caget(PV_TRIGGER_ARC, timeout=3.0)
        assert val == 0, f"触发PV未自动清零: TriggerArc={val}"


class TestNormalStartup:
    """场景: 正常启动 - AutoC_Start=1 后状态 IDLE → INITIALIZING → ADJUSTING_POWER"""

    def test_idle_to_initializing(self, controller):
        """验证启动信号触发状态转换"""
        assert controller.current_state == RFQState.IDLE

        # 启动控制器（后台线程）
        t = run_controller_background(controller)
        time.sleep(1)

        # 设置启动信号
        epics.caput(PV_START, 1, wait=True)

        # 等待离开IDLE
        assert wait_for_state_not(controller, RFQState.IDLE, timeout=TIMEOUT_SHORT), \
            f"控制器未离开IDLE状态，当前: {controller.current_state}"

    def test_full_startup_sequence(self, controller):
        """验证完整启动序列: IDLE → INITIALIZING → ADJUSTING_POWER"""
        t = run_controller_background(controller)

        epics.caput(PV_START, 1, wait=True)

        # 等待到达 ADJUSTING_POWER（跳过中间的 INITIALIZING）
        success = wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)

        assert success or controller.current_state in (
            RFQState.ADJUSTING_POWER,
            RFQState.EXPANDING_PULSE,
            RFQState.COMPLETED,
        ), f"启动序列异常，当前状态: {controller.current_state}"


class TestPowerConvergence:
    """场景: 功率收敛 - Drive逐步增大, power收敛至目标值"""

    def test_cw_mode_convergence(self, controller):
        """CW模式下功率收敛到目标值"""
        # 设置CW模式，目标50kW (drive需要500)
        epics.caput(PV_PULSE_CW, 0, wait=True)  # CW
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        epics.caput(PV_DRIVE_STEP1, 50.0, wait=True)  # 大步长加快收敛
        epics.caput(PV_DRIVE_STEP2, 10.0, wait=True)
        epics.caput(PV_MARGIN_LARGE, 10.0, wait=True)
        epics.caput(PV_MARGIN_SMALL, 2.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # CW模式下到达COMPLETED表示功率收敛
        success = wait_for_state(controller, RFQState.COMPLETED, timeout=TIMEOUT_LONG)

        if not success:
            # 检查是否在调节过程中
            power = epics.caget(PV_POWER, timeout=3.0)
            drive = epics.caget(PV_CW_DRIVE, timeout=3.0)
            logger.info(f"当前状态: {controller.current_state}, power={power}, drive={drive}")

        assert success, f"CW模式功率未能收敛，当前状态: {controller.current_state}"

    def test_drive_increases_monotonically(self, controller):
        """验证Drive逐步增大"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # 等待进入ADJUSTING_POWER
        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)

        # 采样Drive值
        drives = []
        for _ in range(5):
            time.sleep(3)
            d = epics.caget(PV_CW_DRIVE, timeout=3.0)
            if d is not None:
                drives.append(d)

        if len(drives) >= 2:
            # 功率低于目标时Drive应递增
            assert drives[-1] >= drives[0], \
                f"Drive未递增: {drives}"


class TestPulseExpansion:
    """场景: 脉冲展宽 - 脉冲模式下功率达标后进入EXPANDING_PULSE"""

    def test_enters_expanding_pulse(self, controller):
        """脉冲模式下功率达标后进入展脉宽状态"""
        # 脉冲模式
        epics.caput(PV_PULSE_CW, 1, wait=True)
        epics.caput(PV_TARGET_POWER, 10.0, wait=True)  # 较低目标，加快达标
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        epics.caput(PV_DRIVE_STEP1, 20.0, wait=True)
        epics.caput(PV_DRIVE_STEP2, 5.0, wait=True)
        epics.caput(PV_MARGIN_LARGE, 5.0, wait=True)
        epics.caput(PV_MARGIN_SMALL, 2.0, wait=True)
        epics.caput(PV_PULSE_START, 1.0, wait=True)
        epics.caput(PV_PULSE_END, 3.0, wait=True)  # 短展宽范围
        epics.caput(PV_WAIT_TIME, 0.5, wait=True)  # 最短等待
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # 等待到达 EXPANDING_PULSE 或 COMPLETED
        deadline = time.time() + TIMEOUT_LONG
        reached_expanding = False
        while time.time() < deadline:
            state = controller.current_state
            if state == RFQState.EXPANDING_PULSE:
                reached_expanding = True
                break
            if state == RFQState.COMPLETED:
                reached_expanding = True  # 可能直接完成
                break
            if state in (RFQState.ERROR, RFQState.STOPPED):
                break
            time.sleep(POLL_INTERVAL)

        assert reached_expanding, \
            f"未进入EXPANDING_PULSE状态，当前: {controller.current_state}"


class TestArcFaultRecovery:
    """场景: 弧光故障恢复 - TriggerArc=1后故障计数+1, 自动复位, 重新初始化"""

    def test_arc_fault_during_operation(self, controller):
        """运行中触发弧光故障，系统应自动恢复"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # 等待进入ADJUSTING_POWER
        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(2)

        # 注入弧光故障
        logger.info("注入弧光故障...")
        epics.caput(PV_TRIGGER_ARC, 1, wait=True)
        time.sleep(5)

        # 系统应记录故障并尝试恢复
        fault_count = controller.fault_handler.get_fault_count()
        logger.info(f"故障计数: {fault_count}")
        assert fault_count >= 1, "弧光故障未被计数"

        # 等待系统恢复（回到IDLE或重新进入ADJUSTING_POWER）
        deadline = time.time() + TIMEOUT_MEDIUM
        recovered = False
        while time.time() < deadline:
            state = controller.current_state
            if state in (RFQState.IDLE, RFQState.INITIALIZING, RFQState.ADJUSTING_POWER):
                recovered = True
                break
            if state == RFQState.ERROR:
                break
            time.sleep(POLL_INTERVAL)

        # 恢复或进入ERROR都是合理结果
        assert recovered or controller.current_state == RFQState.ERROR, \
            f"故障后状态异常: {controller.current_state}"


class TestFaultExceeded:
    """场景: 故障超限 - 连续触发超过max_faults次故障后进入ERROR状态"""

    def test_fault_count_exceeds_limit(self, controller):
        """连续故障超限后进入ERROR"""
        # 设置较低的最大故障次数以加速测试
        controller.config._cfg['loop']['max_faults'] = 3
        controller.fault_handler.config._cfg['loop']['max_faults'] = 3

        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # 等待启动
        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)

        # 连续注入故障
        for i in range(4):
            time.sleep(3)
            logger.info(f"注入故障 {i+1}/4")
            epics.caput(PV_TRIGGER_ARC, 1, wait=True)
            time.sleep(5)
            # 如果已经到ERROR就不用再触发了
            if controller.current_state == RFQState.ERROR:
                break

        # 等待进入ERROR
        success = wait_for_state(controller, RFQState.ERROR, timeout=TIMEOUT_MEDIUM)
        assert success, f"故障超限后未进入ERROR，当前: {controller.current_state}"


class TestVacuumExcursion:
    """场景: 真空超标暂停 - 真空超标后进入WAITING_VACUUM, 恢复后继续"""

    def test_vacuum_triggers_wait(self, controller):
        """真空超标触发等待状态"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        # 等待进入ADJUSTING_POWER
        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(2)

        # 注入真空超标 (阈值 5e-5 Pa)
        logger.info("注入真空超标...")
        epics.caput(PV_VAC4, 1e-4, wait=True)
        time.sleep(1)

        # 等待进入WAITING_VACUUM
        success = wait_for_state(controller, RFQState.WAITING_VACUUM, timeout=TIMEOUT_SHORT)
        assert success, f"真空超标后未进入WAITING_VACUUM，当前: {controller.current_state}"

    def test_vacuum_recovery(self, controller):
        """真空恢复后自动继续"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(2)

        # 真空超标
        epics.caput(PV_VAC4, 1e-4, wait=True)
        time.sleep(1)
        wait_for_state(controller, RFQState.WAITING_VACUUM, timeout=TIMEOUT_SHORT)

        # 真空恢复
        logger.info("真空恢复...")
        epics.caput(PV_VAC4, 1e-6, wait=True)
        time.sleep(1)

        # 应回到ADJUSTING_POWER
        success = wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_SHORT)
        assert success, f"真空恢复后未返回ADJUSTING_POWER，当前: {controller.current_state}"


class TestUserStopAndReset:
    """场景: 用户停止 - AutoC_Start=0 后暂停, AutoC_Reset=1 后停止"""

    def test_pause_on_start_zero(self, controller):
        """Start=0触发暂停"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(1)

        # 用户暂停
        logger.info("用户暂停 (Start=0)...")
        epics.caput(PV_START, 0, wait=True)

        success = wait_for_state(controller, RFQState.PAUSED, timeout=TIMEOUT_SHORT)
        assert success, f"未进入PAUSED状态，当前: {controller.current_state}"

    def test_resume_after_pause(self, controller):
        """暂停后恢复运行"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(1)

        # 暂停
        epics.caput(PV_START, 0, wait=True)
        wait_for_state(controller, RFQState.PAUSED, timeout=TIMEOUT_SHORT)

        # 恢复
        logger.info("用户恢复 (Start=1)...")
        epics.caput(PV_START, 1, wait=True)

        # 应恢复到之前的活动状态
        success = wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_SHORT)
        assert success, f"恢复后未返回ADJUSTING_POWER，当前: {controller.current_state}"

    def test_reset_from_error(self, controller):
        """从ERROR状态Reset回到IDLE"""
        # 手动设置为ERROR
        controller.error_message = "测试错误"
        controller.set_state(RFQState.ERROR)

        t = run_controller_background(controller)

        # 发送Reset
        time.sleep(1)
        epics.caput(PV_RESET, 1, wait=True)
        time.sleep(3)

        assert controller.current_state == RFQState.IDLE, \
            f"Reset后未回到IDLE，当前: {controller.current_state}"


class TestParameterHotUpdate:
    """场景: 暂停期间热修改参数"""

    def test_parameter_reload_on_resume(self, controller):
        """暂停后修改目标功率，恢复后生效"""
        epics.caput(PV_PULSE_CW, 0, wait=True)
        epics.caput(PV_TARGET_POWER, 50.0, wait=True)
        epics.caput(PV_INIT_DRIVE, 100.0, wait=True)
        time.sleep(0.5)

        t = run_controller_background(controller)
        epics.caput(PV_START, 1, wait=True)

        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_MEDIUM)
        time.sleep(1)

        # 暂停
        epics.caput(PV_START, 0, wait=True)
        wait_for_state(controller, RFQState.PAUSED, timeout=TIMEOUT_SHORT)

        # 修改目标功率
        new_target = 30.0
        epics.caput(PV_TARGET_POWER, new_target, wait=True)
        time.sleep(0.5)

        # 恢复
        epics.caput(PV_START, 1, wait=True)
        wait_for_state(controller, RFQState.ADJUSTING_POWER, timeout=TIMEOUT_SHORT)
        time.sleep(1)

        # 验证参数已更新
        assert abs(controller.target_power - new_target) < 0.1, \
            f"目标功率未更新: {controller.target_power} (期望: {new_target})"


# ==================== 主入口 ====================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s', '--tb=short'])

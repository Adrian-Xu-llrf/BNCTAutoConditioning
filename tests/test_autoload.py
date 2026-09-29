#!/usr/bin/env python3
"""
自动加载模式端到端测试

验证状态流程: IDLE → INITIALIZING → STABLE_BUILDING → ADJUSTING_POWER
             → CLOSING_LOOP → AUTO_REGULATING → AUTO_MAINTAINING

通过 MockPVManager 模拟硬件行为，无需真实 EPICS IOC。
"""

import logging
import os
import time
import yaml

from rfq.core.controller import RFQController
from rfq.core.state import RFQState

logging.basicConfig(level=logging.DEBUG, format='%(name)s [%(levelname)s] %(message)s')
logger = logging.getLogger('test_autoload')


# ---------------------------------------------------------------------------
# MockPVManager — 字典存储，模拟真实 PV 读写
# ---------------------------------------------------------------------------

class MockPVManager:
    """模拟 PVManager，用字典存储 PV 值，无 EPICS 依赖"""

    def __init__(self):
        self._store = {}
        self._pv_names = {}
        self._callbacks = {}

    def register(self, pv_key, pv_name):
        self._pv_names[pv_key] = pv_name
        if pv_key not in self._store:
            self._store[pv_key] = None

    def register_group(self, group_dict, prefix):
        for key, pv_name in group_dict.items():
            self.register(f"{prefix}.{key}", pv_name)

    def register_list(self, pv_name_list, prefix):
        for i, pv_name in enumerate(pv_name_list):
            self.register(f"{prefix}.{i}", pv_name)

    def get(self, pv_key, timeout=3.0):
        return self._store.get(pv_key)

    def put(self, pv_key, value, wait=False):
        self._store[pv_key] = value
        for cb in self._callbacks.get(pv_key, []):
            cb(value)
        return True

    def get_pv_object(self, pv_key):
        return None

    def get_pv_name(self, pv_key):
        return self._pv_names.get(pv_key, pv_key)

    def check_all_connected(self):
        return (True, [])

    def get_registered_count(self):
        return len(self._store)

    def add_callback(self, pv_key, callback):
        self._callbacks.setdefault(pv_key, []).append(callback)

    @classmethod
    def reset_instance(cls):
        pass


# ---------------------------------------------------------------------------
# MockConfig — 从 config.yaml 加载真实的 PV 名称
# ---------------------------------------------------------------------------

class MockConfig:
    def __init__(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            self._cfg = yaml.safe_load(f)

    def get(self, *keys, default=None):
        value = self._cfg
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @property
    def pv(self):
        return self._cfg.get('pv', {})

    @property
    def vacuum(self):
        return self._cfg.get('vacuum', {})

    @property
    def loop(self):
        return self._cfg.get('loop', {})

    def reload_if_changed(self):
        return False


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

def _set_all_pvs(pv):
    """在控制器创建前设置所有 PV 默认值（真空值必须在 VacuumChecker 初始化前设置）"""
    # 真空 — 必须先于 VacuumChecker.__init__
    for i in range(6):
        pv.put(f'vacuum.{i}', 1e-6)

    # 故障 — 正常
    pv.put('fault.arc', 1)
    pv.put('fault.VacInterlock', 1)
    pv.put('fault.interlock2', 1)
    pv.put('fault.di4', 1)

    # RF
    pv.put('rf.pulse_cw', 0)
    pv.put('rf.rf_on', 1)
    pv.put('rf.pulse_drive', 0.0)
    pv.put('rf.cw_drive', 0.0)
    pv.put('rf.sweep', 0)
    pv.put('rf.tracking', 0)
    pv.put('rf.Amp_Limiter', 1000.0)
    pv.put('rf.power', 0.0)
    pv.put('rf.detuning_error', 0.0)
    pv.put('rf.freq_start', 162.620)

    # 闭环 PV
    pv.put('rf.setpoint_set', 0.0)
    pv.put('rf.error_read', 0.0)
    pv.put('rf.loop_status_read', 0)
    pv.put('rf.close_loop', 0)

    # 控制
    pv.put('control.start', 1)
    pv.put('control.reset', 0)
    pv.put('control.power_targets', [30.0])
    pv.put('control.init_drive', 10.0)
    pv.put('control.pulse_start', 1.0)
    pv.put('control.pulse_end', 100.0)
    pv.put('control.pulse_step', 10.0)
    pv.put('control.drive_step1', 10.0)
    pv.put('control.drive_step2', 2.0)
    pv.put('control.margin_large', 5.0)
    pv.put('control.margin_small', 1.0)
    pv.put('control.pulse_wait', 1.0)
    pv.put('control.wait_before_expand', 0.01)
    pv.put('control.current_target_power', 0.0)
    pv.put('control.current_pulse', 1.0)
    pv.put('control.pulse_drop', 10.0)

    # 稳定建场
    pv.put('control.stable_step', 10.0)
    pv.put('control.stable_margin', 1.0)
    pv.put('control.stable_power', 5.0)

    # 自动加载
    pv.put('control.auto_load', 1)
    pv.put('control.setpoint_step', 1)
    pv.put('control.setpoint_margin', 1.0)


def create_controller():
    """创建注入 MockPVManager 的控制器"""
    config = MockConfig()
    pv = MockPVManager()
    _set_all_pvs(pv)

    ctrl = RFQController(config, pv_manager=pv)
    ctrl._sleep = lambda s: None
    ctrl.rf_manager._sleep = lambda s: None
    ctrl.power_controller._sleep = lambda s: None
    ctrl.pulse_controller._sleep = lambda s: None

    return ctrl, pv


def jump_to_state(ctrl, target_state):
    """通过直接设置 current_state 跳转到目标状态（绕过转换表校验，仅测试用）"""
    old = ctrl.current_state
    ctrl.current_state = target_state
    ctrl.state_enter_time = time.time()
    logger.info(f"测试跳转: {old} → {target_state}")


# ---------------------------------------------------------------------------
# 单元测试：AUTO_REGULATING 状态行为
# ---------------------------------------------------------------------------

def test_auto_regulating_setpoint_step_is_int():
    """验证 adjust_setpoint 使用整数步进"""
    from rfq.controllers.power import PowerController

    pv = MockPVManager()
    config = MockConfig()
    pc = PowerController(config, pv, sleep_func=lambda s: None)

    pv.register('rf.power', 'TEST:power')
    pv.register('rf.setpoint_set', 'TEST:setpoint')
    pv.register('rf.Amp_Limiter', 'TEST:limiter')

    pv.put('rf.power', 25.0)
    pv.put('rf.setpoint_set', 500.0)
    pv.put('rf.Amp_Limiter', 1000.0)

    reached, msg = pc.adjust_setpoint(target_power=30.0, step=1, margin=1.0)
    new_setpoint = pv.get('rf.setpoint_set')
    assert new_setpoint == 501, f"Expected 501, got {new_setpoint}"
    assert not reached
    logger.info(f"✓ setpoint整数步进: 500 -> {new_setpoint}")


def test_auto_regulating_converges():
    """验证 AUTO_REGULATING 在功率达标后收敛到 AUTO_MAINTAINING"""
    ctrl, pv = create_controller()
    jump_to_state(ctrl, RFQState.AUTO_REGULATING)

    ctrl.params.target_power = 30.0
    ctrl.params.setpoint_step = 5
    ctrl.params.setpoint_margin = 2.0

    pv.put('rf.power', 29.5)
    pv.put('rf.setpoint_set', 600.0)

    ctrl._handle_auto_regulating()
    assert ctrl.current_state == RFQState.AUTO_MAINTAINING, (
        f"Expected AUTO_MAINTAINING, got {ctrl.current_state}"
    )
    logger.info("✓ 功率达标后直接收敛到 AUTO_MAINTAINING")


def test_auto_regulating_steps_setpoint():
    """验证 AUTO_REGULATING 在功率不达标时增加 setpoint"""
    ctrl, pv = create_controller()
    jump_to_state(ctrl, RFQState.AUTO_REGULATING)

    ctrl.params.target_power = 30.0
    ctrl.params.setpoint_step = 3
    ctrl.params.setpoint_margin = 1.0

    pv.put('rf.power', 25.0)
    pv.put('rf.setpoint_set', 500.0)

    ctrl._handle_auto_regulating()
    assert ctrl.current_state == RFQState.AUTO_REGULATING
    assert pv.get('rf.setpoint_set') == 503, f"Expected 503, got {pv.get('rf.setpoint_set')}"
    logger.info(f"✓ 功率不足时增加setpoint: 500 -> {pv.get('rf.setpoint_set')}")


def test_auto_regulating_reduces_setpoint():
    """验证 AUTO_REGULATING 在功率过高时减少 setpoint"""
    ctrl, pv = create_controller()
    jump_to_state(ctrl, RFQState.AUTO_REGULATING)

    ctrl.params.target_power = 30.0
    ctrl.params.setpoint_step = 3
    ctrl.params.setpoint_margin = 1.0

    pv.put('rf.power', 35.0)
    pv.put('rf.setpoint_set', 700.0)

    ctrl._handle_auto_regulating()
    assert ctrl.current_state == RFQState.AUTO_REGULATING
    assert pv.get('rf.setpoint_set') == 697, f"Expected 697, got {pv.get('rf.setpoint_set')}"
    logger.info(f"✓ 功率过高时减少setpoint: 700 -> {pv.get('rf.setpoint_set')}")


def test_auto_regulating_upper_limit():
    """验证 setpoint 不超过 Amp_Limiter"""
    ctrl, pv = create_controller()
    jump_to_state(ctrl, RFQState.AUTO_REGULATING)

    ctrl.params.target_power = 100.0
    ctrl.params.setpoint_step = 5
    ctrl.params.setpoint_margin = 1.0

    pv.put('rf.power', 10.0)
    pv.put('rf.setpoint_set', 998.0)
    pv.put('rf.Amp_Limiter', 1000.0)

    ctrl._handle_auto_regulating()
    assert pv.get('rf.setpoint_set') == 1000.0, f"Should be clamped to 1000, got {pv.get('rf.setpoint_set')}"
    logger.info(f"✓ setpoint上限保护: clamped to {pv.get('rf.setpoint_set')}")


# ---------------------------------------------------------------------------
# 端到端测试：完整自动加载流程
# ---------------------------------------------------------------------------

def test_autoload_full_flow():
    """测试自动加载模式完整流程: IDLE → ... → AUTO_MAINTAINING"""
    ctrl, pv = create_controller()

    # ===== IDLE → INITIALIZING =====
    assert ctrl.current_state == RFQState.IDLE
    ctrl._handle_idle()
    assert ctrl.current_state == RFQState.INITIALIZING
    logger.info("✓ IDLE → INITIALIZING")

    # ===== INITIALIZING → STABLE_BUILDING =====
    ctrl._handle_initializing()
    assert ctrl.current_state == RFQState.STABLE_BUILDING, f"Expected STABLE_BUILDING, got {ctrl.current_state}"
    logger.info("✓ INITIALIZING → STABLE_BUILDING")

    # ===== STABLE_BUILDING → ADJUSTING_POWER =====
    for i in range(20):
        drive = pv.get('rf.cw_drive')
        pv.put('rf.power', drive * 0.1)
        pv.put('rf.detuning_error', 0.0)
        ctrl._handle_stable_building()
        if ctrl.current_state == RFQState.ADJUSTING_POWER:
            break

    assert ctrl.current_state == RFQState.ADJUSTING_POWER, f"Expected ADJUSTING_POWER, got {ctrl.current_state}"
    logger.info(f"✓ STABLE_BUILDING → ADJUSTING_POWER (drive={pv.get('rf.cw_drive'):.0f}, power={pv.get('rf.power'):.1f}kW)")

    # ===== ADJUSTING_POWER → CLOSING_LOOP =====
    for i in range(200):
        drive = pv.get('rf.cw_drive')
        pv.put('rf.power', drive * 0.1)
        ctrl._handle_adjusting_power()
        if ctrl.current_state != RFQState.ADJUSTING_POWER:
            break

    assert ctrl.current_state == RFQState.CLOSING_LOOP, f"Expected CLOSING_LOOP, got {ctrl.current_state}"
    logger.info(f"✓ ADJUSTING_POWER → CLOSING_LOOP (power={pv.get('rf.power'):.1f}kW)")

    # ===== CLOSING_LOOP → AUTO_REGULATING =====
    pv.put('rf.error_read', 2.0)

    for i in range(20):
        if pv.get('rf.close_loop') == 1:
            pv.put('rf.loop_status_read', 1)
        ctrl._handle_closing_loop()
        if ctrl.current_state != RFQState.CLOSING_LOOP:
            break

    assert ctrl.current_state == RFQState.AUTO_REGULATING, f"Expected AUTO_REGULATING, got {ctrl.current_state}"
    logger.info("✓ CLOSING_LOOP → AUTO_REGULATING")

    # ===== AUTO_REGULATING → AUTO_MAINTAINING =====
    # 闭环后 setpoint 控制 power，模拟 power ≈ setpoint * 0.05
    # 设置初始 setpoint 为闭环时的合理值
    pv.put('rf.setpoint_set', 580.0)
    pv.put('rf.power', 580.0 * 0.05)  # 29.0kW

    for i in range(500):
        setpoint = pv.get('rf.setpoint_set')
        pv.put('rf.power', setpoint * 0.05)
        ctrl._handle_auto_regulating()
        if ctrl.current_state != RFQState.AUTO_REGULATING:
            break

    assert ctrl.current_state == RFQState.AUTO_MAINTAINING, (
        f"Expected AUTO_MAINTAINING, got {ctrl.current_state}, "
        f"power={pv.get('rf.power'):.1f}kW, target={ctrl.params.target_power}"
    )

    logger.info("=" * 55)
    logger.info("自动加载完整流程测试通过!")
    logger.info(f"  最终状态: {ctrl.current_state}")
    logger.info(f"  最终功率: {pv.get('rf.power'):.1f}kW (目标: {ctrl.params.target_power}kW)")
    logger.info(f"  最终setpoint: {pv.get('rf.setpoint_set')}")
    logger.info("=" * 55)


if __name__ == '__main__':
    test_auto_regulating_setpoint_step_is_int()
    test_auto_regulating_converges()
    test_auto_regulating_steps_setpoint()
    test_auto_regulating_reduces_setpoint()
    test_auto_regulating_upper_limit()
    test_autoload_full_flow()
    print("\n所有测试通过!")

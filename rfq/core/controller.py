#!/usr/bin/env python3
"""
RFQ主控制器 - 状态机版本
使用状态机模式管理老练流程

作者: Chengye Xu
日期: 2026-03
"""

import time
import logging
from ..utils.pv_manager import PVManager
from ..controllers.fault import FaultHandler
from ..controllers.vacuum import VacuumChecker
from ..controllers.power import PowerController
from ..controllers.pulse import PulseController
from .state import RFQState, StateTransitionError, LEGAL_TRANSITIONS
from .rf_manager import RFManager
from .params import ConditioningParams, ParameterLoader

logger = logging.getLogger('RFQ.Controller')


class RFQController:
    """RFQ自动老练控制器 - 状态机版本"""

    def __init__(self, config, pv_manager=None):
        """
        初始化RFQ控制器

        Args:
            config: 配置对象
            pv_manager: 可选的PVManager实例（测试注入用）
        """
        self.config = config

        if pv_manager is not None:
            self.pv_manager = pv_manager
        else:
            PVManager.reset_instance()
            self.pv_manager = PVManager(config)
            self._register_all_pvs()
            logger.info(f"PVManager已注册 {self.pv_manager.get_registered_count()} 个PV")

        self.fault_handler = FaultHandler(config, self.pv_manager)
        self.vacuum_checker = VacuumChecker(config, self.pv_manager)
        self.power_controller = PowerController(config, self.pv_manager)
        self.pulse_controller = PulseController(config, self.pv_manager)

        # RF管理器
        self.rf_manager = RFManager(self.pv_manager, self.fault_handler, sleep_func=self._sleep)
        self._apply_runtime_config()

        # 参数管理
        self.params = ConditioningParams()
        self.param_loader = ParameterLoader(self.pv_manager, self.config)

        # 状态机相关
        self.current_state = RFQState.IDLE
        self.error_message = ""
        self.state_before_pause = None
        self.terminal_cleaned = {}
        self.state_enter_time = 0
        self._pulse_step_start_time = 0

        # 状态标志
        self._wait_before_power = False
        self._need_reset_pulse = False
        self._is_auto_recovery = False
        self._is_auto_load = False
        self._waiting_for_switch = False
        self._switch_wait_start = 0
        self._stable_detuning_count = 0

        # 状态集合常量
        self.active_states = frozenset({
            RFQState.STABLE_BUILDING,
            RFQState.ADJUSTING_POWER,
            RFQState.WAITING_VACUUM,
            RFQState.EXPANDING_PULSE,
            RFQState.AUTO_MAINTAINING,
            RFQState.AUTO_REGULATING,
        })
        self.states_need_rf = frozenset({
            RFQState.STABLE_BUILDING,
            RFQState.ADJUSTING_POWER,
            RFQState.EXPANDING_PULSE,
            RFQState.AUTO_MAINTAINING,
            RFQState.AUTO_REGULATING,
        })
        self.terminal_states = frozenset({
            RFQState.COMPLETED,
            RFQState.ERROR,
            RFQState.STOPPED,
        })

        # 状态处理函数映射
        self.state_handlers = {
            RFQState.IDLE: self._handle_idle,
            RFQState.INITIALIZING: self._handle_initializing,
            RFQState.PAUSED: self._handle_paused,
            RFQState.STABLE_BUILDING: self._handle_stable_building,
            RFQState.ADJUSTING_POWER: self._handle_adjusting_power,
            RFQState.WAITING_VACUUM: self._handle_waiting_vacuum,
            RFQState.EXPANDING_PULSE: self._handle_expanding_pulse,
            RFQState.CLOSING_LOOP: self._handle_closing_loop,
            RFQState.AUTO_REGULATING: self._handle_auto_regulating,
            RFQState.AUTO_MAINTAINING: self._handle_auto_maintaining,
            RFQState.COMPLETED: self._handle_completed,
            RFQState.ERROR: self._handle_error,
            RFQState.STOPPED: self._handle_stopped,
        }

    def set_state(self, new_state):
        """
        设置新状态并记录状态转换

        Args:
            new_state: 新状态(RFQState枚举)

        Raises:
            StateTransitionError: 非法状态转换
        """
        if self.current_state == new_state:
            return

        allowed = LEGAL_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            raise StateTransitionError(
                f"非法状态转换: {self.current_state} (#{self.current_state.get_code()}) -> "
                f"{new_state} (#{new_state.get_code()})，"
                f"允许的目标状态: {[s.name for s in allowed]}"
            )

        old_state = self.current_state
        self.current_state = new_state
        self.state_enter_time = time.time()
        self._pulse_step_start_time = 0
        logger.info(f"状态转换: {old_state} (#{old_state.get_code()}) -> {new_state} (#{new_state.get_code()})")
        self.update_status(new_state.get_code())

    # ==================== 基础工具方法 ====================

    def _register_all_pvs(self):
        """从config.yaml批量注册所有PV"""
        pv_cfg = self.config.pv
        self.pv_manager.register_group(pv_cfg.get('rf', {}), 'rf')
        self.pv_manager.register_group(pv_cfg.get('fault', {}), 'fault')
        self.pv_manager.register_group(pv_cfg.get('control', {}), 'control')
        self.pv_manager.register_list(pv_cfg.get('vacuum', []), 'vacuum')

    def update_status(self, code: int):
        """更新状态码到EPICS（整数，对应 RFQState.value）"""
        logger.info(f"状态码: {code}")
        self.pv_manager.put('control.status', code)

    def _get_pv(self, pv_key):
        return self.pv_manager.get(pv_key)

    def _put_pv(self, pv_key, value):
        return self.pv_manager.put(pv_key, value)

    def _sleep(self, seconds):
        """统一休眠方法，便于测试注入"""
        time.sleep(seconds)

    def _apply_runtime_config(self):
        """
        将 config 中所有需要缓存的运行时参数重新应用到各子模块（支持热加载）

        说明：vacuum / power / pulse 等模块在方法调用时直接读取 self.config，
        无需在此刷新；只有缓存型字段（FaultHandler 滑动窗口、RFManager 启动参数）
        需要显式重新应用。
        """
        # RF 启动参数
        rf_startup_cfg = self.config.get('loop', 'rf_startup', default={})
        start_freq_cfg = rf_startup_cfg.get('start_frequency')
        self.rf_manager.configure_startup(
            max_retries=int(rf_startup_cfg.get('max_retry', 3)),
            retry_interval=float(rf_startup_cfg.get('retry_interval', 5.0)),
            start_frequency=float(start_freq_cfg) if start_freq_cfg is not None else None,
        )
        # 故障滑动窗口参数
        self.fault_handler.reload_config()

    def _sleep_loop(self):
        """按配置循环间隔休眠"""
        self._sleep(float(self.config.loop.get('interval', 1)))

    def _reset_stable_building_state(self):
        """清理稳定建场阶段的连续判稳状态"""
        self._stable_detuning_count = 0

    # ==================== 条件检查（拆分自 _check_common_conditions） ====================

    def _check_pause_signal(self):
        """
        检查用户暂停/停止信号

        Returns:
            RFQState or None
        """
        start_signal = self._get_pv('control.start')
        logger.debug(f"检查条件: start={start_signal}, state={self.current_state}")

        if start_signal == 0:
            if self.current_state in self.active_states:
                logger.debug(f"检测到暂停信号，保存当前状态: {self.current_state}")
                self.state_before_pause = self.current_state
                return RFQState.PAUSED
            else:
                logger.debug("检测到停止信号（非活动状态）")
                self.error_message = "用户停止"
                return RFQState.STOPPED
        return None

    def _check_rf_status(self):
        """
        检查RF在线状态

        Returns:
            RFQState or None
        """
        if self.current_state not in self.states_need_rf:
            return None

        rf_on = self._get_pv('rf.rf_on')
        logger.debug(f"检查RF状态: rf_on={rf_on}")
        if rf_on == 1:
            return None

        fault_count = self.fault_handler.get_fault_count()
        last_fault = self.fault_handler.get_last_fault_type()

        # 主动读各故障 PV，定位触发原因（0=故障，1=正常）
        fault_pv_status = {
            name: self._get_pv(key)
            for key, name in zip(
                self.fault_handler.FAULT_PV_KEYS,
                self.fault_handler.FAULT_NAMES,
            )
        }
        tripped = [name for name, val in fault_pv_status.items() if val == 0]
        fault_detail = f"触发故障: {tripped}" if tripped else "所有故障PV当前正常（瞬时触发或原因不明）"

        logger.warning(
            f"检测到RF已关闭 | callback记录: 计数={fault_count}, 类型={last_fault} | {fault_detail}"
        )
        if self.fault_handler.is_fault_exceeded():
            logger.error("故障次数超限，进入ERROR状态")
            self.error_message = "故障次数超限"
            return RFQState.ERROR

        # 故障未超限：执行复位，重置到IDLE准备重启
        # 先确认 start 信号仍为1，避免竞态条件导致卡死在 IDLE
        if self._get_pv('control.start') != 1:
            logger.warning("RF掉线且start信号已清除，转为ERROR状态")
            self.error_message = "RF掉线且start信号已清除"
            return RFQState.ERROR

        self.fault_handler.reset_all_faults()
        self.fault_handler.check_fault_status()
        self.reset(clear_faults=False)
        return RFQState.IDLE

    def _check_limits(self):
        """
        检查故障和迭代次数限制

        Returns:
            RFQState or None
        """
        fault_count = self.fault_handler.get_fault_count()
        iteration_count = self.power_controller.get_iteration_count()
        logger.debug(f"计数器检查: faults={fault_count}, iterations={iteration_count}")

        if self.fault_handler.is_fault_exceeded():
            logger.error(f"故障次数超限: {fault_count}")
            self.error_message = "故障次数超限"
            return RFQState.ERROR

        if iteration_count >= self.config.loop['max_iterations']:
            logger.error(f"迭代次数超限: {iteration_count}")
            self.error_message = "迭代次数超限"
            return RFQState.ERROR

        return None

    def _check_common_conditions(self):
        """
        检查所有状态下的通用条件

        Returns:
            RFQState or None
        """
        # 依次检查：暂停信号 → 真空状态 → RF状态 → 计数限制
        return (self._check_pause_signal()
                or self._check_vacuum_status()
                or self._check_rf_status()
                or self._check_limits())

    def _check_vacuum_status(self):
        """
        检查真空状态，在工作状态和初始化阶段生效

        Returns:
            RFQState or None
        """
        if self.current_state == RFQState.WAITING_VACUUM:
            return None

        if self.current_state not in self.states_need_rf and self.current_state != RFQState.INITIALIZING:
            return None

        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        if not is_ok:
            logger.warning(f"通用条件检测到真空不达标: {vacuum_value:.2e} Pa ({vacuum_pv})")
            return RFQState.WAITING_VACUUM
        return None

    # ==================== 重置与清理 ====================

    def _check_reset_signal(self):
        """
        检查并处理reset信号

        Returns:
            bool: 如果检测到reset信号返回True
        """
        if self._get_pv('control.reset') == 1:
            self._put_pv('control.reset', 0)
            self.reset()
            return True
        return False

    def _cleanup_terminal_state(self, state_name, cleanup_func=None):
        """清理终止状态（只执行一次）"""
        if state_name not in self.terminal_cleaned:
            if cleanup_func:
                cleanup_func()
            self.terminal_cleaned[state_name] = True

    def reset(self, clear_faults=True):
        """
        重置状态机到IDLE状态

        Args:
            clear_faults: True=手动复位（清零故障计数，回到初始状态）；
                          False=自动恢复（保留故障计数和功率目标，脉宽退 pulse_drop）
        """
        logger.info(f"执行Reset，状态机重置到IDLE (clear_faults={clear_faults})")
        if clear_faults:
            self._put_pv('control.start', 0)

        # 清除状态相关变量
        self.error_message = ""
        self.state_before_pause = None
        self.terminal_cleaned.clear()
        self._reset_stable_building_state()

        # 重置计数器
        self.power_controller.reset_iteration_count()
        # 注意：_wait_before_power 和 _need_reset_pulse 仅在手动复位时清除
        # 自动恢复时保留这些跨状态协调标志，避免跳过等待保护

        if clear_faults:
            self._reset_manual()
        else:
            self._reset_auto_recovery()

        self.set_state(RFQState.IDLE)
        logger.info("系统已重置")

    def _reset_manual(self):
        """手动复位：回到最初状态（第一个功率目标，初始脉宽）"""
        self._is_auto_load = False
        p = self.params
        p.target_index = 0
        self._wait_before_power = False
        self._need_reset_pulse = False
        logger.info("手动Reset：功率目标索引归零")
        self.fault_handler.reset_fault_count()

        if p.power_targets:
            first_target = p.power_targets[0]
            self._put_pv('control.current_target_power', first_target)
            logger.info(f"手动Reset：目标功率恢复至第一个目标 {first_target} kW")
        else:
            logger.warning("功率目标列表为空，无法恢复目标功率PV")

        # 从PV重新读取初始脉宽
        pulse_start_from_pv = self._get_pv('control.pulse_start')
        if pulse_start_from_pv is not None:
            p.pulse_start = pulse_start_from_pv
            p.original_pulse_start = pulse_start_from_pv
            pulse_time_s = float(p.pulse_start) / 1000.0
            self._put_pv('rf.pulse_time', pulse_time_s)
            self._put_pv('control.current_pulse', p.pulse_start)
            logger.info(f"手动Reset：脉宽恢复至PV设定值 {p.pulse_start:.1f}ms")
        elif p.original_pulse_start is not None:
            p.pulse_start = p.original_pulse_start
            pulse_time_s = float(p.pulse_start) / 1000.0
            self._put_pv('rf.pulse_time', pulse_time_s)
            self._put_pv('control.current_pulse', p.pulse_start)
            logger.info(f"手动Reset：PV读取失败，使用缓存初始值 {p.pulse_start:.1f}ms")
        else:
            logger.warning("脉宽参数未初始化，等待下次初始化时从PV加载")

    def _reset_auto_recovery(self):
        """自动恢复：保持当前功率目标，脉宽下降 pulse_drop"""
        # 自动加载模式下无脉宽概念，仅保留目标功率
        if self._is_auto_load:
            logger.info("自动加载模式Trip恢复: 保持目标功率不变")
            self._is_auto_recovery = True
            return

        p = self.params
        self._is_auto_recovery = True
        if p.pulse_start is not None and p.original_pulse_start is not None:
            current_pulse_ms = self._get_pv('rf.pulse_time') * 1000
            pulse_drop_val = self.pv_manager.get('control.pulse_drop')
            pulse_drop = float(pulse_drop_val) if pulse_drop_val is not None else 20.0
            new_pulse_start = current_pulse_ms - pulse_drop
            if new_pulse_start < p.original_pulse_start:
                new_pulse_start = p.original_pulse_start
                logger.warning(f"Trip后脉宽已降至初始值 {new_pulse_start:.1f}ms，无法再降")
            else:
                logger.info(f"Trip后脉宽下降 {pulse_drop:.1f}ms: {current_pulse_ms:.1f} -> {new_pulse_start:.1f}ms")
            p.pulse_start = new_pulse_start
            pulse_time_s = float(p.pulse_start) / 1000.0
            self._put_pv('rf.pulse_time', pulse_time_s)
            self._put_pv('control.current_pulse', p.pulse_start)
            logger.info(f"更新脉宽PV: {p.pulse_start:.1f}ms")
        else:
            logger.warning("脉宽参数未初始化，无法执行Trip后脉宽调整")

    # ==================== 状态处理函数 ====================

    def _handle_idle(self):
        """处理IDLE状态 - 等待启动信号"""
        start_signal = self._get_pv('control.start')
        logger.debug(f"IDLE状态检查: start={start_signal}")
        if start_signal == 1:
            logger.debug("检测到启动信号，进入初始化")
            self.set_state(RFQState.INITIALIZING)
        self._sleep(1)

    def _handle_initializing(self):
        """处理INITIALIZING状态 - 初始化RF系统"""
        logger.debug("开始初始化流程")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"初始化中检测到异常: {new_state}")
            self.set_state(new_state)
            return

        try:
            pv_ok, failed = self.pv_manager.check_all_connected()
            if not pv_ok:
                self.error_message = f"PV连接失败: {failed}"
                logger.error(f"PV健康检查未通过: {failed}")
                self.set_state(RFQState.ERROR)
                return
            logger.info("PV健康检查通过，所有PV已连接")

            logger.debug("步骤1/3: 加载参数")
            self.config.reload_if_changed()
            self._apply_runtime_config()
            if not self.param_loader.load(self.params, is_auto_recovery=self._is_auto_recovery):
                self.error_message = "参数加载失败"
                self.set_state(RFQState.ERROR)
                return

            logger.debug("步骤2/3: 配置RF模式")
            if not self.rf_manager.setup_mode(self.params.pulse_start):
                self.error_message = "RF模式配置失败"
                self.set_state(RFQState.ERROR)
                return

            # 读取自动加载模式
            auto_load_val = self._get_pv('control.auto_load')
            self._is_auto_load = (auto_load_val == 1)
            if self._is_auto_load:
                if self.rf_manager.is_pulse_mode:
                    self.error_message = "自动加载模式只能在CW模式下使用"
                    logger.error(self.error_message)
                    self.set_state(RFQState.ERROR)
                    return
                logger.info("自动加载模式: 加载到目标功率后持续监控，Trip自动恢复")

            logger.debug("步骤3/3: 启动RF系统")
            if not self.rf_manager.startup(
                self.params.init_drive,
                should_stop=lambda: self._get_pv('control.start') == 0,
            ):
                if self._get_pv('control.start') == 0:
                    logger.info("RF启动被用户中断")
                    self.error_message = "用户停止"
                    self.set_state(RFQState.STOPPED)
                else:
                    self.error_message = "RF启动失败"
                    self.set_state(RFQState.ERROR)
                return

            logger.info("初始化完成，进入稳定建场状态")
            self._is_auto_recovery = False
            self.set_state(RFQState.STABLE_BUILDING)

        except Exception as e:
            # 区分 EPICS 通信异常和逻辑异常
            import epics.ca
            if isinstance(e, (epics.ca.ChannelAccessException, TimeoutError, OSError)):
                logger.error(f"EPICS通信异常: {e}")
            else:
                logger.error(f"初始化逻辑异常: {e}", exc_info=True)
            self.error_message = f"初始化异常: {e}"
            self.set_state(RFQState.ERROR)

    def _handle_stable_building(self):
        """处理STABLE_BUILDING状态 - detuning门控Drive爬升至稳定功率"""
        logger.debug("=== STABLE_BUILDING状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"STABLE_BUILDING通用条件触发状态转换: {new_state}")
            self._reset_stable_building_state()
            self.set_state(new_state)
            return

        stable_timeout = float(self.config.get('loop', 'stable_timeout_seconds', default=60.0))
        stable_cycles = int(self.config.get('loop', 'stable_detuning_cycles', default=3))
        elapsed_total = time.time() - self.state_enter_time
        if elapsed_total > stable_timeout:
            current_power = self._get_pv('rf.power')
            detuning = self._get_pv('rf.detuning_error')
            self.error_message = (
                "稳定建场超时: "
                f"{elapsed_total:.1f}s > {stable_timeout:.1f}s, "
                f"power={current_power}, detuning={detuning}"
            )
            logger.error(self.error_message)
            self._reset_stable_building_state()
            self.set_state(RFQState.ERROR)
            return

        if self.rf_manager.current_drive_pv is None:
            self.error_message = "稳定建场失败: 当前Drive PV未配置"
            logger.error(self.error_message)
            self._reset_stable_building_state()
            self.set_state(RFQState.ERROR)
            return

        current_power = self._get_pv('rf.power')
        stable_power = self._get_pv('control.stable_power')
        if current_power is None or stable_power is None:
            self.error_message = (
                f"稳定建场参数读取失败: rf.power={current_power}, stable_power={stable_power}"
            )
            logger.error(self.error_message)
            self._reset_stable_building_state()
            self.set_state(RFQState.ERROR)
            return

        if current_power >= stable_power:
            logger.info(
                f"STABLE_BUILDING: 当前功率 {current_power:.1f}kW 已达到建场目标 "
                f"{stable_power:.1f}kW，进入调功率状态"
            )
            self._reset_stable_building_state()
            self.set_state(RFQState.ADJUSTING_POWER)
            return

        detuning = self._get_pv('rf.detuning_error')
        stable_margin = self._get_pv('control.stable_margin')
        stable_step = self._get_pv('control.stable_step')
        if None in (detuning, stable_margin, stable_step):
            self.error_message = (
                "稳定建场参数读取失败: "
                f"detuning={detuning}, stable_margin={stable_margin}, stable_step={stable_step}"
            )
            logger.error(self.error_message)
            self._reset_stable_building_state()
            self.set_state(RFQState.ERROR)
            return

        if abs(detuning) <= stable_margin:
            self._stable_detuning_count += 1
            logger.debug(
                f"STABLE_BUILDING detuning稳定计数: {self._stable_detuning_count}/{stable_cycles}, "
                f"detuning={detuning:.3f}, margin={stable_margin:.3f}"
            )
            if self._stable_detuning_count < stable_cycles:
                self._sleep_loop()
                return

            old_drive = self._get_pv(self.rf_manager.current_drive_pv)
            if old_drive is None:
                self.error_message = f"稳定建场失败: 无法读取Drive PV {self.rf_manager.current_drive_pv}"
                logger.error(self.error_message)
                self._reset_stable_building_state()
                self.set_state(RFQState.ERROR)
                return

            new_drive = self.power_controller.step_drive(
                self.rf_manager.current_drive_pv,
                stable_step,
            )
            if new_drive is None:
                self.error_message = f"稳定建场失败: Drive步进失败 {self.rf_manager.current_drive_pv}"
                logger.error(self.error_message)
                self._reset_stable_building_state()
                self.set_state(RFQState.ERROR)
                return

            logger.info(
                "STABLE_BUILDING步进Drive: "
                f"detuning={detuning:.3f}, margin={stable_margin:.3f}, step={stable_step:.3f}, "
                f"drive={old_drive:.3f}->{new_drive:.3f}, power={current_power:.1f}kW/"
                f"{stable_power:.1f}kW"
            )
            self._reset_stable_building_state()

            current_power = self._get_pv('rf.power')
            if current_power is None:
                self.error_message = "稳定建场失败: 步进后无法读取rf.power"
                logger.error(self.error_message)
                self._reset_stable_building_state()
                self.set_state(RFQState.ERROR)
                return

            if current_power >= stable_power:
                logger.info(
                    f"STABLE_BUILDING完成: 当前功率 {current_power:.1f}kW 达到建场目标 "
                    f"{stable_power:.1f}kW，进入调功率状态"
                )
                self._reset_stable_building_state()
                self.set_state(RFQState.ADJUSTING_POWER)
                return
        else:
            if self._stable_detuning_count > 0:
                logger.debug(
                    f"STABLE_BUILDING detuning脱离窗口，稳定计数清零: "
                    f"|{detuning:.3f}| > {stable_margin:.3f}"
                )
            self._stable_detuning_count = 0
            logger.debug(
                f"STABLE_BUILDING detuning未进入允许窗口: |{detuning:.3f}| > {stable_margin:.3f}"
            )

        self._sleep_loop()

    def _handle_adjusting_power(self):
        """处理ADJUSTING_POWER状态 - 调节功率"""
        logger.debug("=== ADJUSTING_POWER状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        # 展脉宽后加功率前的非阻塞等待
        if self._wait_before_power:
            self._wait_before_power = False
            adjust_power_start_time = time.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"{adjust_power_start_time} 开始调功率")

        # 检查真空
        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空检查: ok={is_ok}, value={vacuum_value:.2e} Pa, pv={vacuum_pv}")
        if not is_ok:
            logger.warning("真空不达标，进入等待状态")
            self.set_state(RFQState.WAITING_VACUUM)
            return

        # 调节功率
        current_power = self._get_pv('rf.power')
        logger.debug(f"功率调节前: current={current_power}kW, target={self.params.target_power}kW")

        power_ok, power_msg = self.power_controller.adjust(
            self.rf_manager.current_drive_pv,
            self.params.target_power
        )
        logger.debug(power_msg)

        if power_ok:
            logger.info(f"功率已达标，模式: {'脉冲' if self.rf_manager.is_pulse_mode else 'CW'}")
            if self._is_auto_load:
                logger.info('自动加载模式: 功率达标，进入闭环调节')
                self.set_state(RFQState.CLOSING_LOOP)
            elif self.rf_manager.is_pulse_mode:
                logger.info('功率达标，准备展脉宽')
                self.set_state(RFQState.EXPANDING_PULSE)
            else:
                self.set_state(RFQState.COMPLETED)
        elif self.power_controller.fatal_error:
            self.error_message = self.power_controller.fatal_error
            self.set_state(RFQState.ERROR)
        else:
            logger.debug("功率未达标，继续调节")

        self._sleep_loop()

    def _handle_waiting_vacuum(self):
        """处理WAITING_VACUUM状态 - 等待真空恢复"""
        logger.debug("=== WAITING_VACUUM状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空恢复检查: ok={is_ok}, value={vacuum_value:.2e} Pa, pv={vacuum_pv}")

        if is_ok:
            logger.info("真空已恢复，返回功率调节状态")
            self.set_state(RFQState.ADJUSTING_POWER)
        else:
            logger.debug(f"等待真空恢复: {vacuum_value:.2e} Pa (阈值: {vacuum_pv})")
            self._sleep_loop()

    def _handle_expanding_pulse(self):
        """处理EXPANDING_PULSE状态 - 展宽脉冲"""
        logger.debug("=== EXPANDING_PULSE状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        # 每次展脉宽前维持wait_time秒 (非阻塞模式)
        if self._pulse_step_start_time == 0:
            self._pulse_step_start_time = self.state_enter_time
            wait_start_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._pulse_step_start_time))
            logger.info(f"展脉宽前等待开始: {wait_start_time}，共需等待 {self.params.wait_time:.1f} 秒")
        elapsed = time.time() - self._pulse_step_start_time
        if elapsed < self.params.wait_time:

            is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
            if not is_ok:
                logger.warning("等待期间真空不达标，进入等待状态")
                self.set_state(RFQState.WAITING_VACUUM)
            self._sleep_loop()
            return

        # 检查真空
        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空检查: ok={is_ok}, value={vacuum_value:.2e} Pa")
        if not is_ok:
            logger.warning("真空不达标，进入等待状态")
            self.set_state(RFQState.WAITING_VACUUM)
            return

        # 展宽脉冲
        current_pulse = self._get_pv('rf.pulse_time') * 1000
        logger.debug(f"脉宽扩展: current={current_pulse:.1f}ms, target={self.params.pulse_end}ms, step={self.params.pulse_step}ms")

        pulse_ok, pulse_msg = self.pulse_controller.expand(
            self.rf_manager.current_drive_pv,
            self.params.init_drive,
            self.params.pulse_end,
            self.params.pulse_step,
            should_stop=lambda: self._get_pv('control.start') == 0,
        )
        logger.debug(pulse_msg)

        if pulse_ok:
            new_pulse = self._get_pv('rf.pulse_time') * 1000
            self.params.pulse_start = new_pulse
            self._put_pv('control.current_pulse', self.params.pulse_start)

        if pulse_ok:
            if self.params.power_targets and self.params.target_index < len(self.params.power_targets) - 1:
                if not self._waiting_for_switch:
                    self._waiting_for_switch = True
                    self._switch_wait_start = time.time()
                    switch_wait_start_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._switch_wait_start))
                    logger.info(f"脉宽已达目标，{switch_wait_start_time} 开始等待 {self.params.wait_before_expand:.1f} 秒后再切换下一功率目标")
                    self._sleep_loop()
                    return

                elapsed = time.time() - self._switch_wait_start
                if elapsed < self.params.wait_before_expand:
                    remaining = self.params.wait_before_expand - elapsed
                    logger.debug(f"切换前等待中: {remaining:.1f}s remaining...")
                    self._sleep_loop()
                    return

                self._waiting_for_switch = False
                switch_complete_time = time.strftime('%Y-%m-%d %H:%M:%S')

                self.params.pulse_start = self.params.original_pulse_start
                pulse_time_s = float(self.params.pulse_start) / 1000.0
                self._put_pv('rf.pulse_time', pulse_time_s)
                self._put_pv('control.current_pulse', self.params.pulse_start)
                logger.info(f"恢复初始脉宽: {self.params.pulse_start}ms")

                self.params.target_index += 1
                next_target = self.params.power_targets[self.params.target_index]
                self._put_pv('control.current_target_power', next_target)
                logger.info(
                    f"{switch_complete_time} 切换到第{self.params.target_index + 1}/{len(self.params.power_targets)}个功率目标: "
                    f"{next_target} kW"
                )
                self.params.target_power = next_target
                self.power_controller.reset_iteration_count()

                logger.info("准备调节功率")

                self._wait_before_power = True
                self.set_state(RFQState.ADJUSTING_POWER)
            else:
                logger.debug("所有功率目标已完成，老练完成")
                self.set_state(RFQState.COMPLETED)
        else:
            self._put_pv('control.current_pulse', self._get_pv('rf.pulse_time') * 1000)
            self._pulse_step_start_time = time.time()

        self._sleep_loop()

    def _handle_closing_loop(self):
        """处理CLOSING_LOOP状态 - 自动加载模式：调节ampsetpoint使amperror<10后闭环"""
        logger.debug("=== CLOSING_LOOP状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"CLOSING_LOOP通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        closing_timeout = 30.0
        elapsed = time.time() - self.state_enter_time
        if elapsed > closing_timeout:
            amp_error = self._get_pv('rf.error_read')
            loop_status = self._get_pv('rf.loop_status_read')
            self.error_message = (
                f"闭环超时: {elapsed:.1f}s > {closing_timeout:.1f}s, "
                f"amperror={amp_error}, amploopstatus={loop_status}"
            )
            logger.error(self.error_message)
            self.set_state(RFQState.ERROR)
            return

        loop_status = self._get_pv('rf.loop_status_read')
        if loop_status == 1:
            logger.info("闭环完成: amploopstatus=1，进入闭环功率调节")
            self.set_state(RFQState.AUTO_REGULATING)
            return

        amp_error = self._get_pv('rf.error_read')
        if amp_error is None:
            self.error_message = "闭环失败: 无法读取 amperror"
            logger.error(self.error_message)
            self.set_state(RFQState.ERROR)
            return

        if abs(amp_error) >= 10:
            current_setpoint = self._get_pv('rf.setpoint_set')
            if current_setpoint is None:
                self.error_message = "闭环失败: 无法读取 ampsetpoint"
                logger.error(self.error_message)
                self.set_state(RFQState.ERROR)
                return

            new_setpoint = current_setpoint - amp_error
            self._put_pv('rf.setpoint_set', new_setpoint)
            logger.info(
                f"闭环调节: amperror={amp_error:.2f}, "
                f"ampsetpoint={current_setpoint:.2f}->{new_setpoint:.2f}"
            )
            self._sleep_loop()
            return

        logger.info(f"amperror={amp_error:.2f} < 10，执行闭环")
        self._put_pv('rf.close_loop', 1)
        self._sleep_loop()

    def _handle_auto_regulating(self):
        """处理AUTO_REGULATING状态 - 闭环后通过setpoint调节功率到目标值"""
        logger.debug("=== AUTO_REGULATING状态处理 ===")

        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"AUTO_REGULATING通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        current_power = self._get_pv('rf.power')
        target_power = self.params.target_power

        if current_power is None:
            self.error_message = "闭环功率调节: 无法读取功率"
            logger.error(self.error_message)
            self.set_state(RFQState.ERROR)
            return

        margin = self.params.setpoint_margin
        if abs(current_power - target_power) < margin:
            logger.info(
                f"闭环功率调节完成: {current_power:.1f}kW (目标={target_power:.1f}kW, 裕度={margin}kW)，"
                "进入自动加载监控"
            )
            self.set_state(RFQState.AUTO_MAINTAINING)
            return

        power_ok, power_msg = self.power_controller.adjust_setpoint(
            self.params.target_power,
            self.params.setpoint_step,
            self.params.setpoint_margin,
        )
        logger.debug(power_msg)

        self._sleep_loop()

    def _handle_auto_maintaining(self):
        """处理AUTO_MAINTAINING状态 - 自动加载模式：功率达标后监控等待"""
        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"自动加载监控状态转换: {new_state}")
            self.set_state(new_state)
            return
        self._sleep_loop()

    def _handle_paused(self):
        """处理PAUSED状态 - 已暂停，等待恢复"""
        if self._check_reset_signal():
            return

        start_signal = self._get_pv('control.start')
        logger.debug(f"PAUSED状态检查: start={start_signal}, saved_state={self.state_before_pause}")

        if start_signal == 1:
            logger.info("检测到恢复信号，重新加载控制参数...")
            saved_pulse_start = self.params.pulse_start
            self.config.reload_if_changed()
            self._apply_runtime_config()
            if not self.param_loader.load(self.params):
                logger.error("参数重新加载失败")
                self.error_message = "参数重新加载失败"
                self.set_state(RFQState.ERROR)
                return
            self.params.pulse_start = saved_pulse_start
            self._put_pv('control.current_pulse', self.params.pulse_start)

            if self.state_before_pause:
                logger.info(f"恢复运行，返回到状态: {self.state_before_pause}")
                self.set_state(self.state_before_pause)
                self.state_before_pause = None
            else:
                logger.warning("没有保存的暂停前状态，返回IDLE")
                self.set_state(RFQState.IDLE)
        else:
            logger.debug("继续暂停中...")
            self._sleep_loop()

    def _handle_completed(self):
        """处理COMPLETED状态 - 老练完成"""
        if 'completed' not in self.terminal_cleaned:
            logger.info("="*60)
            logger.info("老练成功完成")
            logger.info(f"总故障次数: {self.fault_handler.get_fault_count()}")
            logger.info(f"总迭代次数: {self.power_controller.get_iteration_count()}")
            logger.info("="*60)
            logger.info("将start PV设为0")
            self._put_pv('control.start', 0)
            self.terminal_cleaned['completed'] = True

        if self._check_reset_signal():
            return
        self._sleep(1)

    def _handle_error(self):
        """处理ERROR状态 - 错误处理"""
        if self._check_reset_signal():
            return

        def error_cleanup():
            logger.error(f"进入错误状态: {self.error_message}")
            self.rf_manager.shutdown()
            self._put_pv('control.start', 0)

        self._cleanup_terminal_state('error', error_cleanup)
        self._sleep(1)

    def _handle_stopped(self):
        """处理STOPPED状态 - 用户停止"""
        if self._check_reset_signal():
            return

        def stopped_cleanup():
            logger.warning("用户请求停止")
            self.rf_manager.shutdown()

        self._cleanup_terminal_state('stopped', stopped_cleanup)
        self._sleep(1)

    # ==================== 主运行循环 ====================

    def run(self):
        """运行状态机主循环"""
        logger.info("="*60)
        logger.info("RFQ自动老练系统 (状态机版本) 开始运行...")
        logger.info("="*60)

        try:
            while True:
                while self.current_state not in self.terminal_states:
                    handler = self.state_handlers.get(self.current_state)

                    if handler is None:
                        logger.error(f"未知状态: {self.current_state}")
                        self.error_message = f"未知状态: {self.current_state}"
                        self.set_state(RFQState.ERROR)
                        continue

                    handler()

                handler = self.state_handlers.get(self.current_state)
                if handler:
                    handler()

                logger.info(f"到达终止状态: {self.current_state}，等待 reset 信号恢复...")
                while self.current_state in self.terminal_states:
                    self._sleep(1)
                    if self._get_pv('control.reset') == 1:
                        self._put_pv('control.reset', 0)
                        self.reset()

        except KeyboardInterrupt:
            logger.warning("用户中断 (Ctrl+C)")
            self.rf_manager.shutdown()
            self.error_message = "用户中断"
            self.set_state(RFQState.STOPPED)
            self._handle_stopped()

        except StateTransitionError as e:
            logger.error(f"非法状态转换: {e}")
            self.rf_manager.shutdown()
            self.error_message = str(e)
            self.set_state(RFQState.ERROR)
            self._handle_error()

        except Exception as e:
            logger.error(f"系统异常: {e}", exc_info=True)
            self.rf_manager.shutdown()
            self.error_message = f"系统异常: {e}"
            self.set_state(RFQState.ERROR)
            self._handle_error()

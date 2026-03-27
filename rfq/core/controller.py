#!/usr/bin/env python3
"""
RFQ主控制器 - 状态机版本
使用状态机模式管理老练流程

作者: Chengye Xu
日期: 2025-11
"""

import time
import logging
from ..utils.pv_manager import PVManager
from ..controllers.fault import FaultHandler
from ..controllers.vacuum import VacuumChecker
from ..controllers.power import PowerController
from ..controllers.pulse import PulseController
from .state import RFQState, StateTransitionError

logger = logging.getLogger('RFQ.Controller')


class RFQController:
    """RFQ自动老练控制器 - 状态机版本"""

    def __init__(self, config, pv_manager=None):
        """
        初始化RFQ控制器

        Args:
            config: 配置对象
        """
        self.config = config
        # 允许注入PVManager便于测试和替换
        self.pv_manager = pv_manager or PVManager()
        self.fault_handler = FaultHandler(config)
        self.vacuum_checker = VacuumChecker(config)
        self.power_controller = PowerController(config)
        self.pulse_controller = PulseController(config)

        # 状态机相关
        self.current_state = RFQState.IDLE
        self.error_message = ""
        self.state_before_pause = None  # 保存暂停前的状态，用于恢复
        self.terminal_cleaned = {}  # 跟踪终止状态的清理状态
        self.state_enter_time = 0  # 记录进入当前状态的时间

        # 运行模式和参数
        self.is_pulse_mode = False
        self.current_drive_pv = None

        # 从PV读取的参数
        self.target_power = None
        self.init_drive = None
        self.pulse_start = None
        self.original_pulse_start = None  # 保存原始初始脉宽，展脉宽时不修改
        self.pulse_end = None
        self.pulse_step = None

        # 多目标功率列表（来自 config.yaml power_targets）
        # 为空时退回单目标模式（读 AutoC_TargetPower PV）
        self.power_targets = []
        self.target_index = 0

        # RF启动重试相关参数（来自配置，提供合理默认值）
        self.max_rf_startup_retries = int(self.config.loop.get('rf_startup_retries', 3))
        self.retry_interval = float(self.config.loop.get('rf_retry_interval', 5.0))
        self.rf_startup_retry_count = 0

        # 状态集合常量，避免重复构造，提高可读性
        self.active_states = frozenset({
            RFQState.ADJUSTING_POWER,
            RFQState.WAITING_VACUUM,
            RFQState.EXPANDING_PULSE,
        })
        self.states_need_rf = frozenset({
            RFQState.ADJUSTING_POWER,
            RFQState.WAITING_VACUUM,
            RFQState.EXPANDING_PULSE,
        })
        self.terminal_states = frozenset({RFQState.ERROR, RFQState.STOPPED})

        # 状态处理函数映射（初始化一次）
        self.state_handlers = {
            RFQState.IDLE: self._handle_idle,
            RFQState.INITIALIZING: self._handle_initializing,
            RFQState.PAUSED: self._handle_paused,
            RFQState.ADJUSTING_POWER: self._handle_adjusting_power,
            RFQState.WAITING_VACUUM: self._handle_waiting_vacuum,
            RFQState.EXPANDING_PULSE: self._handle_expanding_pulse,
            RFQState.COMPLETED: self._handle_completed,
            RFQState.ERROR: self._handle_error,
            RFQState.STOPPED: self._handle_stopped,
        }


    def set_state(self, new_state):
        """
        设置新状态并记录状态转换

        Args:
            new_state: 新状态(RFQState枚举)
        """
        if self.current_state != new_state:
            old_state = self.current_state
            self.current_state = new_state
            self.state_enter_time = time.time()
            # 记录状态转换，包含状态编号便于分析
            logger.info(f"状态转换: {old_state} (#{old_state.get_code()}) -> {new_state} (#{new_state.get_code()})")
            # status PV只显示状态名称（英文）
            self.update_status(new_state.name)

    def update_status(self, msg):
        """
        更新状态到EPICS

        Args:
            msg: 状态消息
        """
        logger.info(msg)
        safe_msg = self.pv_manager.safe_status(msg)
        self.pv_manager.put(self.config.get_pv('control.status'), safe_msg)

    def _get_pv(self, pv_key):
        """获取PV值的简化方法"""
        return self.pv_manager.get(self.config.get_pv(pv_key))

    def _put_pv(self, pv_key, value):
        """设置PV值的简化方法"""
        self.pv_manager.put(self.config.get_pv(pv_key), value)

    def _sleep(self, seconds):
        """统一休眠方法，便于后续性能测试替换或注入"""
        time.sleep(seconds)

    def _sleep_loop(self):
        """按配置循环间隔休眠"""
        self._sleep(float(self.config.loop.get('interval', 1)))

    def _check_reset_signal(self):
        """
        检查并处理reset信号

        Returns:
            bool: 如果检测到reset信号返回True
        """
        if self._get_pv('control.reset') == 1:
            self._put_pv('control.reset', 0)  # 清零信号
            self.reset()
            return True
        return False

    def _cleanup_terminal_state(self, state_name, cleanup_func=None):
        """
        清理终止状态（只执行一次）

        Args:
            state_name: 状态名称
            cleanup_func: 可选的清理函数
        """
        if state_name not in self.terminal_cleaned:
            if cleanup_func:
                cleanup_func()
            self.fault_handler.cleanup()
            self.vacuum_checker.cleanup()
            self.terminal_cleaned[state_name] = True

    def reset(self):
        """
        重置状态机到IDLE状态

        用途：
        - 清除错误状态
        - 重新开始老练流程
        - 响应Reset按钮操作
        """
        logger.info("执行Reset，状态机重置到IDLE")

        # 清除状态相关变量
        self.error_message = ""
        self.state_before_pause = None
        self.terminal_cleaned.clear()

        # 重置计数器
        self.power_controller.reset_iteration_count()
        self.fault_handler.reset_fault_count()
        self.target_index = 0
        self.original_pulse_start = None  # 重置原始脉宽，下次初始化时重新读取

        # 重新初始化监听器
        self.fault_handler = FaultHandler(self.config)
        self.vacuum_checker = VacuumChecker(self.config)

        # 设置状态为IDLE（会更新status PV并记录日志）
        self.set_state(RFQState.IDLE)
        logger.info("系统已重置")

    def _load_parameters(self):
        """
        从PV加载运行参数

        Returns:
            bool: 加载是否成功
        """
        logger.info("从PV加载参数...")
        self.config.reload()

        # 多目标模式：将当前目标写入 PV，再由下方统一读取
        cfg_targets = self.config.loop.get('power_targets') or []
        if cfg_targets:
            self.power_targets = [float(t) for t in cfg_targets]
            if self.target_index >= len(self.power_targets):
                self.target_index = 0
            self._put_pv('control.target_power', self.power_targets[self.target_index])
            logger.info(
                f"多目标模式 {self.power_targets}，"
                f"写入第{self.target_index + 1}/{len(self.power_targets)}个目标="
                f"{self.power_targets[self.target_index]} kW -> AutoC_TargetPower"
            )
        else:
            self.power_targets = []

        # 读取目标功率（单目标模式直接读PV，多目标模式读回刚写入的值）
        target_power_pv = self.config.get_pv('control.target_power')
        logger.debug(f"读取PV: {target_power_pv}")
        self.target_power = self._get_pv('control.target_power')
        if self.target_power is None:
            logger.error("无法读取目标功率PV")
            return False
        logger.info(f"目标功率: {self.target_power} kW")

        # 读取初始Drive
        init_drive_pv = self.config.get_pv('control.init_drive')
        logger.debug(f"读取PV: {init_drive_pv}")
        self.init_drive = self._get_pv('control.init_drive')
        if self.init_drive is None:
            logger.error("无法读取初始Drive PV")
            return False
        logger.info(f"初始Drive: {self.init_drive}")

        # 读取脉冲参数
        logger.debug("读取脉冲参数PVs...")
        self.pulse_start = self._get_pv('control.pulse_start')
        self.pulse_end = self._get_pv('control.pulse_end')

        # 从PV读取脉宽步长，读取失败则使用默认值0.5
        pulse_step_val = self._get_pv('control.pulse_step')
        self.pulse_step = float(pulse_step_val) if pulse_step_val is not None else 0.5
        logger.debug(f"脉冲参数: start={self.pulse_start}, end={self.pulse_end}, step={self.pulse_step}")

        if None in [self.pulse_start, self.pulse_end]:
            logger.warning("无法读取脉冲起止参数PV，使用默认值")
            self.pulse_start, self.pulse_end = 1.0, 500.0

        # 保存原始初始脉宽（仅首次加载时保存，后续不覆盖）
        if self.original_pulse_start is None:
            self.original_pulse_start = self.pulse_start
            logger.info(f"保存原始初始脉宽: {self.original_pulse_start} ms")

        logger.info(f"脉冲参数: {self.pulse_start}-{self.pulse_end} ms, 步长={self.pulse_step} ms")

        return True

    def _setup_rf_mode(self):
        """
        识别并配置RF模式（脉冲或连续波）

        Returns:
            bool: 配置是否成功
        """

        pulse_cw_value = self._get_pv('rf.pulse_cw')
        logger.debug(f"RF模式检测: pulse_cw={pulse_cw_value}")

        if pulse_cw_value == 1:
            self.is_pulse_mode = True
            self.current_drive_pv = self.config.get_pv('rf.pulse_drive')
            logger.debug(f"设置脉冲模式Drive PV: {self.current_drive_pv}")
            self._put_pv('rf.cw_drive', 0)
            pulse_time_s = float(self.pulse_start) / 1000.0
            logger.debug(f"设置初始脉宽: {pulse_time_s}s ({self.pulse_start}ms)")
            self._put_pv('rf.pulse_time', pulse_time_s)
            logger.info(f"脉冲模式: 起始脉宽={self.pulse_start}ms")
        else:
            self.is_pulse_mode = False
            self.current_drive_pv = self.config.get_pv('rf.cw_drive')
            logger.debug(f"设置CW模式Drive PV: {self.current_drive_pv}")
            self._put_pv('rf.pulse_drive', 0)
            logger.info("连续波模式")
        return True

    def _startup_rf(self):
        """启动RF系统，失败时自动重置故障并重试"""
        for attempt in range(self.max_rf_startup_retries):
            logger.info(f"RF启动尝试 {attempt + 1}/{self.max_rf_startup_retries}")

            logger.debug("启动RF步骤1: 打开RF")
            self._put_pv('rf.rf_on', 1)
            self._sleep(1.0)

            logger.debug(f"启动RF步骤2: 设置初始Drive={self.init_drive} -> {self.current_drive_pv}")
            self.pv_manager.put(self.current_drive_pv, self.init_drive)
            self._sleep(1.0)

            logger.debug("启动RF步骤3: 打开Swee")
            self._put_pv('rf.sweep', 1)
            self._put_pv('rf.tracking', 1)
            self._sleep(0.5)

            # 验证RF是否真的打开了
            rf_on = self._get_pv('rf.rf_on')
            logger.debug(f"启动RF步骤4: 验证RF状态 rf_on={rf_on}")

            if rf_on == 1:
                logger.info(f"RF启动成功（第{attempt + 1}次尝试）")
                self.rf_startup_retry_count = 0  # 重置重试计数

                return True

            # RF启动失败，说明有ARC故障
            logger.warning(f"RF启动失败（第{attempt + 1}次尝试）：RF on状态不为1，疑似ARC故障")
            self.rf_startup_retry_count = attempt + 1

            # 如果还有重试机会，重置故障并重试
            if attempt < self.max_rf_startup_retries - 1:
                logger.info(f"正在重置Interlock故障，等待{self.retry_interval}秒后重试...")
                self.fault_handler._reset_interlock_faults()
                self._sleep(self.retry_interval)
            else:
                logger.error(f"RF启动失败：已达到最大重试次数({self.max_rf_startup_retries})")
        
        return False

    def _shutdown_rf(self):
        """关闭RF系统（不操作sweep和tracking）"""
        logger.debug("开始关闭RF系统")
        if self.current_drive_pv:
            logger.debug(f"将Drive设为0: {self.current_drive_pv}")
            self.pv_manager.put(self.current_drive_pv, 0)
            self._sleep(0.5)
        logger.debug("关闭RF（不操作sweep和tracking）")
        self._put_pv('rf.rf_on', 0)
        logger.debug("RF已关闭")

    def _check_common_conditions(self):
        """
        检查所有状态下的通用条件（故障、停止信号等）

        Returns:
            RFQState or None: 如果需要转换状态返回新状态，否则返回None
        """
        # 检查用户暂停信号（start=0时暂停，而非停止）
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

        # 检查RF状态（在所有需要RF的状态下，必须保证RF on=1）
        # 不检查RF的状态：IDLE(未启动), INITIALIZING(正在启动RF), PAUSED(已暂停), 终止状态(COMPLETED/ERROR/STOPPED)
        if self.current_state in self.states_need_rf:
            rf_on = self._get_pv('rf.rf_on')
            logger.debug(f"检查RF状态: rf_on={rf_on}")
            if rf_on != 1:
                # RF关闭：先检查故障是否超限
                if self.fault_handler.is_fault_exceeded():
                    logger.error("RF已关闭且故障次数超限，进入ERROR状态")
                    self.error_message = "RF故障次数超限"
                    return RFQState.ERROR
                else:
                    # 故障未超限：记录故障并重置到IDLE准备重启
                    logger.warning("检测到RF已关闭，记录故障并重置到IDLE")
                    self.fault_handler.record_fault()
                    self.reset()
                    return RFQState.IDLE

        # 检查故障和迭代次数
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

        # 检查通用条件（包括RF状态）
        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"初始化中检测到异常: {new_state}")
            self.set_state(new_state)
            return

        try:
            # 加载参数
            logger.debug("步骤1/3: 加载参数")
            if not self._load_parameters():
                self.error_message = "参数加载失败"
                self.set_state(RFQState.ERROR)
                return

            # 配置RF模式
            logger.debug("步骤2/3: 配置RF模式")
            if not self._setup_rf_mode():
                self.error_message = "RF模式配置失败"
                self.set_state(RFQState.ERROR)
                return

            # 启动RF
            logger.debug("步骤3/3: 启动RF系统")
            if not self._startup_rf():
                self.error_message = "RF启动失败"
                self.set_state(RFQState.ERROR)
                return

            # 初始化成功，转到功率调节状态
            logger.info("初始化完成，进入功率调节状态")
            self.set_state(RFQState.ADJUSTING_POWER)

        except Exception as e:
            logger.error(f"初始化异常: {e}", exc_info=True)
            self.error_message = f"初始化异常: {e}"
            self.set_state(RFQState.ERROR)

    def _handle_adjusting_power(self):
        """处理ADJUSTING_POWER状态 - 调节功率"""
        logger.debug("=== ADJUSTING_POWER状态处理 ===")

        # 检查通用条件
        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        # 检查真空
        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空检查: ok={is_ok}, value={vacuum_value:.2e} Pa, pv={vacuum_pv}")
        if not is_ok:
            logger.warning(f"真空不达标，进入等待状态")
            self.set_state(RFQState.WAITING_VACUUM)
            return

        # 调节功率
        current_power = self._get_pv('rf.power')
        logger.debug(f"功率调节前: current={current_power}kW, target={self.target_power}kW")

        power_ok, power_msg = self.power_controller.adjust(
            self.current_drive_pv,
            self.target_power
        )
        logger.info(power_msg)  # 详细信息记录到日志

        if power_ok:
            # 功率达标
            logger.info(f"功率已达标，模式: {'脉冲' if self.is_pulse_mode else 'CW'}")
            if self.is_pulse_mode:

                logger.info('功率达标，准备展脉宽')
                self.set_state(RFQState.EXPANDING_PULSE)
            else:
                # CW模式：老练完成
                self.set_state(RFQState.COMPLETED)
        else:
            logger.debug("功率未达标，继续调节")

        self._sleep_loop()

    def _handle_waiting_vacuum(self):
        """处理WAITING_VACUUM状态 - 等待真空恢复"""
        logger.debug("=== WAITING_VACUUM状态处理 ===")

        # 检查通用条件
        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        # 检查真空是否恢复
        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空恢复检查: ok={is_ok}, value={vacuum_value:.2e} Pa, pv={vacuum_pv}")

        if is_ok:
            # 真空恢复，返回功率调节状态
            logger.info("真空已恢复，返回功率调节状态")
            self.set_state(RFQState.ADJUSTING_POWER)
        else:
            # 继续等待（详细信息记录到日志）
            logger.debug(f"等待真空恢复: {vacuum_value:.2e} Pa (阈值: {vacuum_pv})")
            self._sleep_loop()

    def _handle_expanding_pulse(self):
        """处理EXPANDING_PULSE状态 - 展宽脉冲"""
        logger.debug("=== EXPANDING_PULSE状态处理 ===")

        # 检查通用条件
        new_state = self._check_common_conditions()
        if new_state:
            logger.debug(f"通用条件触发状态转换: {new_state}")
            self.set_state(new_state)
            return

        # ============================================================
        # 修改：每次展脉宽前维持60s (非阻塞模式)
        # ============================================================
        wait_time_pv = self.config.get_pv('rf.wait_time')
        wait_time_val = self.pv_manager.get(wait_time_pv)
        elapsed = time.time() - self.state_enter_time
        if elapsed < wait_time_val:
            logger.debug(f"展脉宽前等待中: {wait_time_val - elapsed:.1f}s remaining...")
        try:
            wait_time_val = float(wait_time_val) if wait_time_val is not None else 60.0
        except ValueError:
            logger.warning(f"无效的等待时间值: {wait_time_val}, 使用默认值 60.0s")
            wait_time_val = 60.0

            # 检查真空
            is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
            if not is_ok:
                logger.warning("等待期间真空不达标，进入等待状态")
                self.set_state(RFQState.WAITING_VACUUM)
            return
        # ============================================================

        # 检查真空
        is_ok, vacuum_value, vacuum_pv = self.vacuum_checker.is_vacuum_ok()
        logger.debug(f"真空检查: ok={is_ok}, value={vacuum_value:.2e} Pa")
        if not is_ok:
            logger.warning("真空不达标，进入等待状态")
            self.set_state(RFQState.WAITING_VACUUM)
            return

        # 展宽脉冲
        current_pulse = self._get_pv('rf.pulse_time') * 1000  # 转换为ms
        logger.debug(f"脉宽扩展: current={current_pulse:.1f}ms, target={self.pulse_end}ms, step={self.pulse_step}ms")

        pulse_ok, pulse_msg = self.pulse_controller.expand(
            self.current_drive_pv,
            self.init_drive,
            self.pulse_end,
            self.pulse_step
        )
        logger.info(pulse_msg)  # 详细信息记录到日志

        if pulse_ok:
            # 脉宽已达目标
            logger.debug("脉宽已达目标")

            # 多目标模式：还有下一个目标则切换，否则完成
            if self.power_targets and self.target_index < len(self.power_targets) - 1:
                self.target_index += 1
                next_target = self.power_targets[self.target_index]
                self._put_pv('control.target_power', next_target)
                logger.info(
                    f"切换到第{self.target_index + 1}/{len(self.power_targets)}个功率目标: "
                    f"{next_target} kW"
                )
                self.target_power = next_target
                self.power_controller.reset_iteration_count()

                # 恢复初始脉宽，让下一个功率目标从原始脉宽重新开始展脉宽
                # （AutoC_PulseStart PV 全程不被修改，此处只重置实际脉冲时间）
                self.pulse_start = self.original_pulse_start
                pulse_time_s = float(self.pulse_start) / 1000.0
                self._put_pv('rf.pulse_time', pulse_time_s)
                logger.info(f"恢复初始脉宽: {self.pulse_start}ms，准备下一功率目标展脉宽")

                self.set_state(RFQState.ADJUSTING_POWER)
            else:
                logger.debug("所有功率目标已完成，老练完成")
                self.set_state(RFQState.COMPLETED)
        else:
            # 脉宽增加后，重置迭代计数并返回功率调节状态
            logger.debug("脉宽已增加，重置迭代计数并返回功率调节状态")
            self.power_controller.reset_iteration_count()
            self.set_state(RFQState.ADJUSTING_POWER)

        self._sleep_loop()

    def _handle_paused(self):
        """处理PAUSED状态 - 已暂停，等待恢复"""
        start_signal = self._get_pv('control.start')
        logger.debug(f"PAUSED状态检查: start={start_signal}, saved_state={self.state_before_pause}")

        if start_signal == 1:
            # 恢复运行前，重新加载所有控制参数（支持热修改）
            logger.info("检测到恢复信号，重新加载控制参数...")
            if not self._load_parameters():
                logger.error("参数重新加载失败")
                self.error_message = "参数重新加载失败"
                self.set_state(RFQState.ERROR)
                return

            if self.state_before_pause:
                logger.info(f"恢复运行，返回到状态: {self.state_before_pause}")
                self.set_state(self.state_before_pause)
                self.state_before_pause = None
            else:
                logger.warning("没有保存的暂停前状态，返回IDLE")
                self.set_state(RFQState.IDLE)
        else:
            # 继续暂停等待（状态已通过set_state设置）
            logger.debug("继续暂停中...")
            self._sleep_loop()

    def _handle_completed(self):
        """处理COMPLETED状态 - 老练完成"""
        # 检查reset信号
        if self._check_reset_signal():
            return

        # 首次进入时输出统计信息
        if 'completed' not in self.terminal_cleaned:
            logger.info("="*60)
            logger.info("老练成功完成")
            logger.info(f"总故障次数: {self.fault_handler.get_fault_count()}")
            logger.info(f"总迭代次数: {self.power_controller.get_iteration_count()}")
            logger.info("="*60)

            # 将start设为0
            logger.info("将start PV设为0")
            self._put_pv('control.start', 0)

            # 标记已处理
            self.terminal_cleaned['completed'] = True

        # 保持在COMPLETED状态，等待reset信号
        self._sleep(1)

    def _handle_error(self):
        """处理ERROR状态 - 错误处理"""
        # 检查reset信号
        if self._check_reset_signal():
            return

        # 首次进入时清理
        def error_cleanup():
            logger.error(f"进入错误状态: {self.error_message}")
            self._shutdown_rf()
            self._put_pv('control.start', 0)

        self._cleanup_terminal_state('error', error_cleanup)
        self._sleep(1)

    def _handle_stopped(self):
        """处理STOPPED状态 - 用户停止"""
        # 检查reset信号
        if self._check_reset_signal():
            return

        # 首次进入时清理
        def stopped_cleanup():
            logger.warning("用户请求停止")
            self._shutdown_rf()

        self._cleanup_terminal_state('stopped', stopped_cleanup)
        self._sleep(1)

    # ==================== 主运行循环 ====================

    def run(self):
        """运行状态机主循环"""
        logger.info("="*60)
        logger.info("RFQ自动老练系统 (状态机版本) 开始运行...")
        logger.info("="*60)

        # 状态处理函数映射与终止状态在初始化阶段已构建

        try:
            # 状态机主循环
            while self.current_state not in self.terminal_states:
                # 获取当前状态的处理函数
                handler = self.state_handlers.get(self.current_state)

                if handler is None:
                    logger.error(f"未知状态: {self.current_state}")
                    self.error_message = f"未知状态: {self.current_state}"
                    self.set_state(RFQState.ERROR)
                    continue

                # 执行状态处理函数
                handler()

            # 到达终止状态，执行最后一次处理
            handler = self.state_handlers.get(self.current_state)
            if handler:
                handler()

            logger.info(f"系统停止，最终状态: {self.current_state}")

        except KeyboardInterrupt:
            logger.warning("用户中断 (Ctrl+C)")
            self.error_message = "用户中断"
            self.set_state(RFQState.STOPPED)
            self._handle_stopped()

        except Exception as e:
            logger.error(f"系统异常: {e}", exc_info=True)
            self.error_message = f"系统异常: {e}"
            self.set_state(RFQState.ERROR)
            self._handle_error()

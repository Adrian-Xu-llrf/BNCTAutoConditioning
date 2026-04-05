#!/usr/bin/env python3
"""
参数管理模块
定义运行参数数据类和参数加载器

作者: Chengye Xu
日期: 2026-04
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger('RFQ.Params')


@dataclass
class ConditioningParams:
    """老练运行参数数据类，统一管理从 PV 读取的所有运行参数"""

    # 功率参数
    target_power: float = 0.0
    init_drive: float = 0.0
    power_targets: List[float] = field(default_factory=list)
    target_index: int = 0

    # 脉冲参数
    pulse_start: float = 1.0
    pulse_end: float = 500.0
    pulse_step: float = 0.5
    original_pulse_start: Optional[float] = None

    # 等待时间参数
    wait_time: float = 1.0
    wait_before_expand: float = 10.0

    def current_target(self):
        """获取当前功率目标"""
        if self.power_targets and self.target_index < len(self.power_targets):
            return self.power_targets[self.target_index]
        return self.target_power


class ParameterLoader:
    """参数加载器 - 从 EPICS PV 读取并验证运行参数"""

    def __init__(self, pv_manager, config):
        """
        初始化参数加载器

        Args:
            pv_manager: PVManager实例
            config: 配置对象
        """
        self.pv_manager = pv_manager
        self.config = config

    def _get_pv(self, key):
        return self.pv_manager.get(key)

    def _put_pv(self, key, value):
        return self.pv_manager.put(key, value)

    def load(self, params, is_auto_recovery=False):
        """
        从 PV 加载参数到 ConditioningParams 对象

        Args:
            params: ConditioningParams 实例（就地更新）
            is_auto_recovery: 是否为自动恢复模式（保留当前脉宽）

        Returns:
            bool: 加载是否成功
        """
        logger.info("从PV加载参数...")

        # 从 waveform PV 读取多目标功率列表
        raw = self._get_pv('control.power_targets')
        if raw is not None and len(raw) > 0:
            params.power_targets = [float(v) for v in raw if v > 0]
        else:
            params.power_targets = []

        if not params.power_targets:
            logger.error("power_targets waveform PV 为空或全零，无法启动")
            return False

        if params.target_index >= len(params.power_targets):
            params.target_index = 0

        current_target = params.power_targets[params.target_index]
        self._put_pv('control.current_target_power', current_target)
        params.target_power = current_target
        logger.info(
            f"多目标模式 {params.power_targets}，"
            f"第{params.target_index + 1}/{len(params.power_targets)}个目标="
            f"{current_target} kW -> AutoC_TargetPower"
        )

        # 读取初始Drive
        params.init_drive = self._get_pv('control.init_drive')
        if params.init_drive is None:
            logger.error("无法读取初始Drive PV")
            return False
        logger.info(f"初始Drive: {params.init_drive}")

        # 读取脉冲参数
        logger.debug("读取脉冲参数PVs...")
        if is_auto_recovery and params.pulse_start is not None:
            logger.info(f"自动恢复模式：保留当前脉宽 {params.pulse_start}ms，不从PV重新加载")
        else:
            params.pulse_start = self._get_pv('control.pulse_start')
        params.pulse_end = self._get_pv('control.pulse_end')

        # 读取 pulse_step
        pulse_step_val = self._get_pv('control.pulse_step')
        default_pulse_step = float(self.config.loop.get('pulse_step', 0.5))
        try:
            params.pulse_step = float(pulse_step_val) if pulse_step_val is not None else default_pulse_step
        except (ValueError, TypeError):
            logger.warning(f"pulse_step PV读取失败，使用默认值 {default_pulse_step}ms")
            params.pulse_step = default_pulse_step
        logger.info(f"pulse_step: {params.pulse_step} ms")

        if None in [params.pulse_start, params.pulse_end]:
            logger.warning("无法读取脉冲起止参数PV，使用默认值")
            params.pulse_start, params.pulse_end = 1.0, 500.0

        # 保存原始初始脉宽（仅首次加载时保存）
        if params.original_pulse_start is None:
            params.original_pulse_start = params.pulse_start
            logger.info(f"保存原始初始脉宽: {params.original_pulse_start} ms")

        logger.info(f"脉冲参数: {params.pulse_start}-{params.pulse_end} ms, 步长={params.pulse_step} ms")

        self._put_pv('control.current_pulse', params.pulse_start)

        # 读取 wait_time
        wait_time_val = self._get_pv('control.pulse_wait')
        default_wait = float(self.config.get('loop', 'wait_time_default', default=10.0))
        try:
            params.wait_time = float(wait_time_val) if wait_time_val is not None else default_wait
        except (ValueError, TypeError):
            logger.warning(f"pulse_wait PV读取失败，使用默认值 {default_wait}s")
            params.wait_time = default_wait
        logger.info(f"pulse_wait (wait_time): {params.wait_time} s")

        # 读取 wait_before_expand（PV单位为分钟，转为秒）
        wait_before_expand_min = self._get_pv('control.wait_before_expand')
        wait_before_expand_val = wait_before_expand_min * 60 if wait_before_expand_min is not None else None
        default_wait_expand = float(self.config.get('loop', 'wait_before_expand', default=1.0))
        try:
            params.wait_before_expand = float(wait_before_expand_val) if wait_before_expand_val is not None else default_wait_expand
        except (ValueError, TypeError):
            logger.warning(f"wait_before_expand PV读取失败，使用默认值 {default_wait_expand}s")
            params.wait_before_expand = default_wait_expand
        logger.info(f"wait_before_expand: {params.wait_before_expand} s")

        return True

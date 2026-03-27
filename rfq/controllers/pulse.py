#!/usr/bin/env python3
"""
脉冲控制模块
负责脉冲模式下的脉宽扩展

作者: Chengye Xu
日期: 2025-11
"""

import time
import logging
from ..utils.pv_manager import PVManager

logger = logging.getLogger('RFQ.PulseController')


class PulseController:
    """脉冲控制器"""

    def __init__(self, config):
        """
        初始化脉冲控制器

        Args:
            config: 配置对象
        """
        self.config = config
        self.pv_manager = PVManager()

    def expand(self, current_drive_pv, init_drive, pulse_end, pulse_step):
        """
        展脉宽

        Args:
            current_drive_pv: 当前使用的Drive PV
            init_drive: 初始Drive值
            pulse_end: 目标脉宽 (ms)
            pulse_step: 脉宽步长 (ms)

        Returns:
            tuple: (bool, str)
                - 是否完成
                - 状态消息
        """
        # 读取是否需要在展脉宽前降功率
        reduce_power = self.config.loop.get('reduce_power_before_expand', False)

        current_pulse = self.pv_manager.get(self.config.get_pv('rf.pulse_time'))
        if current_pulse is None:
            return False, "无法读取脉宽"
        current_ms = float(current_pulse) * 1000.0

        if current_ms >= pulse_end:
            msg = f"脉宽已达目标: {current_ms:.2f}ms"
            logger.info(msg)
            return True, msg

        new_ms = current_ms + pulse_step
        if new_ms > pulse_end:
            new_ms = pulse_end

        # 根据配置决定是否在展脉宽前降功率
        if reduce_power:
            # 模式1：展脉宽前降功率到init_drive（缓降）
            drive_step1 = self.pv_manager.get(self.config.get_pv('control.drive_step1'))
            current_drive_val = self.pv_manager.get(current_drive_pv)
            current = float(current_drive_val) if current_drive_val is not None else float(init_drive)
            target = float(init_drive)

            # 确保有步长，如果没有配置则使用默认小步长
            step = float(drive_step1) if drive_step1 and float(drive_step1) > 0 else 0.01

            # 所有情况下都缓降
            if current > target:
                logger.debug(f"缓降Drive到目标: step={step:.3f}, {current:.3f}->{target:.3f}")
                while current - step > target:
                    current -= step
                    self.pv_manager.put(current_drive_pv, current)
                    time.sleep(1.0)  # 增加等待时间到1秒，让降低更平缓
                # 最后设置为精确目标值
                self.pv_manager.put(current_drive_pv, target)
                time.sleep(1.0)
                logger.info(f"Drive已降至目标: {target:.3f}")
            else:
                logger.debug(f"当前Drive ({current:.3f}) 已低于或等于目标 ({target:.3f})，无需降低")
        else:
            # 模式2：不降功率，直接展脉宽（新增逻辑）
            logger.debug("直接展脉宽模式，不降低功率")

        # 设置新的脉宽值
        new_s = float(new_ms) / 1000.0
        self.pv_manager.put(self.config.get_pv('rf.pulse_time'), new_s)
        msg = f"展脉宽: {current_ms:.2f}→{new_ms:.2f}ms"
        logger.info(msg)
        time.sleep(2)

        return False, msg

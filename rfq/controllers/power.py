#!/usr/bin/env python3
"""
功率控制模块
负责调节RF功率到目标值

作者: Chengye Xu
日期: 2026-03
"""

import logging
import time
from ..utils.pv_manager import PVManager

logger = logging.getLogger('RFQ.PowerController')


class PowerController:
    """功率控制器"""

    def __init__(self, config):
        """
        初始化功率控制器

        Args:
            config: 配置对象
        """
        self.config = config
        self.pv_manager = PVManager()
        self.iteration_count = 0

    def adjust(self, current_drive_pv, target_power):
        """
        调节功率

        Args:
            current_drive_pv: 当前使用的Drive PV (脉冲或CW)
            target_power: 目标功率 (kW)

        Returns:fd
            tuple: (bool, str)
                - 是否达标
                - 状态消息
        """
        # 读取当前功率
        current_power = self.pv_manager.get(self.config.get_pv('rf.power'))
        if current_power is None:
            return False, "无法读取功率"

        # 读取当前Drive
        current_drive = self.pv_manager.get(current_drive_pv)
        if current_drive is None:
            logger.error(f"无法读取Drive PV: {current_drive_pv}")
            return False, "无法读取Drive"

        # 从PV读取调节参数（实时读取，支持在线调整）
        logger.debug("读取功率调节参数...")
        drive_step1 = self.pv_manager.get(self.config.get_pv('control.drive_step1'))
        drive_step2 = self.pv_manager.get(self.config.get_pv('control.drive_step2'))
        margin_large = self.pv_manager.get(self.config.get_pv('control.margin_large'))
        margin_small = self.pv_manager.get(self.config.get_pv('control.margin_small'))

        logger.debug(f"调节参数: step1={drive_step1}, step2={drive_step2}, margin_large={margin_large}, margin_small={margin_small}")

        # 检查参数是否读取成功
        if None in [drive_step1, drive_step2, margin_large, margin_small]:
            logger.error("调节参数读取失败")
            return False, "无法读取调节参数"

        # 计算误差
        error = current_power - target_power
        abs_error = abs(error)
        logger.debug(f"功率误差: error={error:.2f}kW, abs_error={abs_error:.2f}kW")

        # 检查功率是否达标
        if abs_error < margin_small:
            msg = f"功率达标: {current_power:.1f}kW"
            logger.info(msg)
            return True, msg

        # 确定调节步长（Drive是无量纲的）
        if abs_error >= margin_large:
            step = drive_step1  # 大步长
            adj_type = "大步"
        else:
            step = drive_step2  # 小步长
            adj_type = "小步"

        logger.debug(f"选择调节步长: type={adj_type}, step={step}")

        # 确定调节方向
        if error < 0:
            new_drive = current_drive + step
            action = "增加"
        else:
            new_drive = current_drive - step
            action = "减少"

        logger.debug(f"Drive调节: {action} {current_drive:.3f} -> {new_drive:.3f}")

        # 写入新的Drive值
        self.pv_manager.put(current_drive_pv, new_drive)
        self.iteration_count += 1
        logger.debug(f"迭代次数: {self.iteration_count}")

        msg = (
            f"{adj_type}{action} Drive: {current_drive:.1f}→{new_drive:.1f}, "
            f"功率={current_power:.1f}kW (目标={target_power:.1f}kW)"
        )
        time.sleep(2)  # 等待2秒，确保Drive有时间响应
        logger.info(msg)
        
        return False, msg

    def reset_iteration_count(self):
        """重置迭代计数器"""
        self.iteration_count = 0

    def get_iteration_count(self):
        """获取迭代次数"""
        return self.iteration_count

#!/usr/bin/env python3
"""
功率控制模块
负责调节RF功率到目标值

作者: Chengye Xu
日期: 2026-03
"""

import logging
import time

from rfq.core.pv_keys import PVKeys

logger = logging.getLogger('RFQ.PowerController')


class PowerController:
    """功率控制器"""

    def __init__(self, config, pv_manager, sleep_func=None):
        """
        初始化功率控制器

        Args:
            config: 配置对象
            pv_manager: PVManager单例实例
            sleep_func: 休眠函数（可注入替换，默认 time.sleep）
        """
        self.config = config
        self.pv_manager = pv_manager
        self._sleep = sleep_func or time.sleep
        self.iteration_count = 0
        self.fatal_error = None

    def step_drive(self, pv_key, step):
        """
        单步增加 Drive，带 AmpLimiter 上限保护

        供 STABLE_BUILDING 和 ADJUSTING_POWER 共用，避免重复实现边界检查。

        Args:
            pv_key: Drive PV 逻辑键
            step: 增量（正值）

        Returns:
            float or None: 写入后的新 Drive 值，读取失败返回 None
        """
        current = self.pv_manager.get(pv_key)
        if current is None:
            logger.error(f"step_drive: 无法读取 Drive PV: {pv_key}")
            return None

        amp_limiter = self.pv_manager.get(PVKeys.AMP_LIMITER)
        max_drive = float(amp_limiter) if amp_limiter is not None else self.config.loop.get('max_drive', 400)

        new_drive = min(float(current) + float(step), max_drive)
        self.pv_manager.put(pv_key, new_drive)
        logger.debug(f"step_drive: {pv_key} {current:.3f} → {new_drive:.3f} (上限={max_drive:.1f})")
        return new_drive

    def adjust(self, current_drive_key, target_power):
        """
        调节功率

        Args:
            current_drive_key: 当前使用的Drive PV key (如 'rf.pulse_drive' 或 'rf.cw_drive')
            target_power: 目标功率 (kW)

        Returns:
            tuple: (bool, str)
                - 是否达标
                - 状态消息
        """
        current_power = self.pv_manager.get('rf.power')
        if current_power is None:
            return False, "无法读取功率"

        current_drive = self.pv_manager.get(current_drive_key)
        if current_drive is None:
            logger.error(f"无法读取Drive PV: {current_drive_key}")
            return False, "无法读取Drive"

        amp_limiter = self.pv_manager.get(PVKeys.AMP_LIMITER)
        max_drive = float(amp_limiter) if amp_limiter is not None else self.config.loop.get('max_drive', 1000)
        if current_drive >= max_drive and current_power <= 0:
            msg = f"Drive已超限({current_drive:.1f}>={max_drive})且功率为0，硬件可能异常"
            logger.error(msg)
            self.fatal_error = msg
            return False, msg
        self.fatal_error = None

        logger.debug("读取功率调节参数...")
        drive_step1 = self.pv_manager.get('control.drive_step1')
        drive_step2 = self.pv_manager.get('control.drive_step2')
        margin_large = self.pv_manager.get('control.margin_large')
        margin_small = self.pv_manager.get('control.margin_small')

        logger.debug(f"调节参数: step1={drive_step1}, step2={drive_step2}, margin_large={margin_large}, margin_small={margin_small}")

        if None in [drive_step1, drive_step2, margin_large, margin_small]:
            logger.error("调节参数读取失败")
            return False, "无法读取调节参数"

        error = current_power - target_power
        abs_error = abs(error)
        logger.debug(f"功率误差: error={error:.2f}kW, abs_error={abs_error:.2f}kW")

        if abs_error < margin_small:
            msg = f"功率达标: {current_power:.1f}kW"
            logger.info(msg)
            return True, msg

        if abs_error >= margin_large:
            step = drive_step1
            adj_type = "大步"
        else:
            step = drive_step2
            adj_type = "小步"

        logger.debug(f"选择调节步长: type={adj_type}, step={step}")

        if error < 0:
            if current_drive >= max_drive:
                msg = f"Drive已达AmpLimiter上限({max_drive:.1f})，无法继续增加，功率={current_power:.1f}kW (目标={target_power:.1f}kW)"
                logger.warning(msg)
                self._sleep(2)
                return False, msg
            new_drive = self.step_drive(current_drive_key, step)
            action = "增加"
        else:
            new_drive = max(current_drive - step, 0)
            self.pv_manager.put(current_drive_key, new_drive)
            action = "减少"

        self.iteration_count += 1
        logger.debug(f"迭代次数: {self.iteration_count}")

        msg = (
            f"{adj_type}{action} Drive: {current_drive:.1f}→{new_drive:.1f}, "
            f"功率={current_power:.1f}kW (目标={target_power:.1f}kW)"
        )
        logger.info(msg)
        self._sleep(2)

        return False, msg

    def reset_iteration_count(self):
        """重置迭代计数器"""
        self.iteration_count = 0

    def get_iteration_count(self):
        """获取迭代次数"""
        return self.iteration_count

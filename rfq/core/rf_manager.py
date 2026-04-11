#!/usr/bin/env python3
"""
RF管理模块
封装RF系统的启停和模式配置

作者: Chengye Xu
日期: 2026-04
"""

import time
import logging

logger = logging.getLogger('RFQ.RFManager')


class RFManager:
    """RF系统管理器 - 封装RF启停和模式配置"""

    def __init__(self, pv_manager, fault_handler, sleep_func=None):
        """
        初始化RF管理器

        Args:
            pv_manager: PVManager实例
            fault_handler: FaultHandler实例（用于启动失败时复位故障）
            sleep_func: 休眠函数（可注入替换，默认 time.sleep）
        """
        self.pv_manager = pv_manager
        self.fault_handler = fault_handler
        self._sleep = sleep_func or time.sleep

        # RF模式状态
        self.is_pulse_mode = False
        self.current_drive_pv = None

        # 重试参数（由 configure_startup 设置）
        self.max_retries = 3
        self.retry_interval = 5.0
        self.retry_count = 0
        self.start_frequency = None

    def configure_startup(self, max_retries, retry_interval, start_frequency=None):
        """
        配置RF启动重试参数

        Args:
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）
            start_frequency: RF启动时写入的起始频率 (MHz)，None则跳过写入
        """
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.start_frequency = start_frequency

    def setup_mode(self, pulse_start):
        """
        识别并配置RF模式（脉冲或连续波）

        Args:
            pulse_start: 初始脉宽（ms），脉冲模式下使用

        Returns:
            bool: 配置是否成功
        """
        pulse_cw_value = self.pv_manager.get('rf.pulse_cw')
        logger.debug(f"RF模式检测: pulse_cw={pulse_cw_value}")

        if pulse_cw_value == 1:
            self.is_pulse_mode = True
            self.current_drive_pv = 'rf.pulse_drive'
            logger.debug(f"设置脉冲模式Drive PV: {self.pv_manager.get_pv_name('rf.pulse_drive')}")
            pulse_time_s = float(pulse_start) / 1000.0
            logger.debug(f"设置初始脉宽: {pulse_time_s}s ({pulse_start}ms)")
            self.pv_manager.put('rf.pulse_time', pulse_time_s)
            logger.info(f"脉冲模式: 起始脉宽={pulse_start}ms")
        else:
            self.is_pulse_mode = False
            self.current_drive_pv = 'rf.cw_drive'
            logger.debug(f"设置CW模式Drive PV: {self.pv_manager.get_pv_name('rf.cw_drive')}")
            logger.info("连续波模式")
        return True

    def startup(self, init_drive, should_stop=None):
        """
        启动RF系统，失败时自动重置故障并重试

        Args:
            init_drive: 初始Drive值
            should_stop: 停止检查回调（返回True时中断启动流程）

        Returns:
            bool: 启动是否成功
        """
        for attempt in range(self.max_retries):
            if should_stop and should_stop():
                logger.info("检测到停止信号，中断RF启动")
                return False

            logger.info(f"RF启动尝试 {attempt + 1}/{self.max_retries}")

            if self.start_frequency is not None:
                logger.debug(f"启动RF步骤0: 写入起始频率 {self.start_frequency} MHz -> {self.pv_manager.get_pv_name('rf.freq_start')}")
                self.pv_manager.put('rf.freq_start', float(self.start_frequency))

            logger.debug("启动RF步骤1: 清零 pulse_drive 和 cw_drive，确保 RF 打开前 Drive 为 0")
            self.pv_manager.put('rf.pulse_drive', 0)
            self.pv_manager.put('rf.cw_drive', 0)
            self._sleep(0.5)

            logger.debug("启动RF步骤2: 打开RF")
            self.pv_manager.put('rf.rf_on', 1)
            self._sleep(1.0)

            # 在写入初始 Drive 之前先验证 RF 已打开
            rf_on = self.pv_manager.get('rf.rf_on')
            logger.debug(f"启动RF步骤3: 验证RF状态 rf_on={rf_on}")
            if rf_on != 1:
                logger.warning(f"RF启动失败（第{attempt + 1}次尝试）：RF on状态不为1，疑似ARC故障")
                self.retry_count = attempt + 1
                if attempt < self.max_retries - 1:
                    logger.info(f"正在重置Interlock故障，等待{self.retry_interval}秒后重试...")
                    self.fault_handler.reset_all_faults()
                    self._sleep(self.retry_interval)
                else:
                    logger.error(f"RF启动失败：已达到最大重试次数({self.max_retries})")
                continue

            logger.debug(f"启动RF步骤4: 设置初始Drive={init_drive} -> {self.pv_manager.get_pv_name(self.current_drive_pv)}")
            self.pv_manager.put(self.current_drive_pv, init_drive)
            self._sleep(1.0)

            logger.debug("启动RF步骤5: 打开Sweep和Tracking")
            self.pv_manager.put('rf.sweep', 1)
            self.pv_manager.put('rf.tracking', 1)
            self._sleep(0.5)

            # 再次确认RF仍然打开（防止写 Drive 后被硬件保护关闭）
            rf_on = self.pv_manager.get('rf.rf_on')
            logger.debug(f"启动RF步骤6: 复核RF状态 rf_on={rf_on}")

            if rf_on == 1:
                logger.info(f"RF启动成功（第{attempt + 1}次尝试）")
                self.retry_count = 0
                return True

            # 写入 Drive 后 RF 被关闭
            logger.warning(f"RF启动失败（第{attempt + 1}次尝试）：写入Drive后RF on状态不为1，疑似ARC故障")
            self.retry_count = attempt + 1

            if attempt < self.max_retries - 1:
                logger.info(f"正在重置Interlock故障，等待{self.retry_interval}秒后重试...")
                self.fault_handler.reset_all_faults()
                self._sleep(self.retry_interval)
            else:
                logger.error(f"RF启动失败：已达到最大重试次数({self.max_retries})")

        return False

    def shutdown(self):
        """关闭RF系统（不操作sweep和tracking）"""
        logger.debug("开始关闭RF系统")
        if self.current_drive_pv:
            logger.debug(f"将Drive设为0: {self.pv_manager.get_pv_name(self.current_drive_pv)}")
            self.pv_manager.put(self.current_drive_pv, 0)
            self._sleep(0.5)
        logger.debug("关闭RF（不操作sweep和tracking）")
        self.pv_manager.put('rf.rf_on', 0)
        logger.debug("RF已关闭")

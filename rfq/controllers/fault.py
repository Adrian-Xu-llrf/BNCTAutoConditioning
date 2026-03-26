#!/usr/bin/env python3
"""
故障处理模块 - 使用callback监听
负责故障检测、计数和复位

作者: Chengye Xu
日期: 2025-11
"""

import time
import logging
import threading
import epics
from ..utils.pv_manager import PVManager

logger = logging.getLogger('RFQ.FaultHandler')


class FaultHandler:
    """故障处理器 - 事件驱动版本"""

    def __init__(self, config):
        """
        初始化故障处理器

        Args:
            config: 配置对象
        """
        self.config = config
        self.pv_manager = PVManager()

        # 故障状态
        self.fault_count = 0
        self.fault_exceeded = False
        self.lock = threading.Lock()

        # 创建PV对象用于callback
        self.pv_arc = epics.PV(self.config.get_pv('fault.arc'))
        self.pv_interlock = epics.PV(self.config.get_pv('fault.interlock'))
        self.pv_SSAComp = epics.PV(self.config.get_pv('fault.SSAComp'))
        self.pv_ReflectedPowerComp = epics.PV(self.config.get_pv('fault.ReflectedPowerComp'))


        # 注册callback
        self.pv_arc.add_callback(self._on_arc_change)
        self.pv_interlock.add_callback(self._on_interlock_change)
        self.pv_SSAComp.add_callback(self._on_SSAComp_change)
        self.pv_ReflectedPowerComp.add_callback(self._on_ReflectedPowerComp_change)

        logger.info("故障监听器已启动")

    


    def _on_arc_change(self, pvname=None, value=None, **kwargs):
        """
        Arc PV变化回调

        Args:
            pvname: PV名称
            value: PV值
        """
        logger.debug(f"Arc PV变化: {pvname}={value}")
        if value == 0:
            self._handle_fault('Arc', value)

    def _on_interlock_change(self, pvname=None, value=None, **kwargs):
        """
        Interlock PV变化回调

        Args:
            pvname: PV名称
            value: PV值
        """
        logger.debug(f"Interlock PV变化: {pvname}={value}")
        if value == 0:
            self._handle_fault('Interlock', value)

    def _on_SSAComp_change(self, pvname=None, value=None, **kwargs):
        """
        SSAComp PV变化回调

        Args:
            pvname: PV名称
            value: PV值
        """
        logger.debug(f"SSAComp PV变化: {pvname}={value}")
        if value == 0:
            self._handle_fault('SSAComp', value)

    def _on_ReflectedPowerComp_change(self, pvname=None, value=None, **kwargs):
        """
        ReflectedPowerComp PV变化回调

        Args:
            pvname: PV名称
            value: PV值
        """
        logger.debug(f"ReflectedPowerComp PV变化: {pvname}={value}")
        if value == 0:
            self._handle_fault('ReflectedPowerComp', value)



    def _handle_fault(self, fault_type, value):
        """
        处理故障事件

        Args:
            fault_type: 故障类型（Arc或Interlock）
            value: PV值
        """
        with self.lock:
            self.fault_count += 1
            logger.warning(f"检测到{fault_type}故障 (第{self.fault_count}次): value={value}")

            # 检查是否超过最大故障次数
            if self.fault_count >= self.config.loop['max_faults']:
                logger.error("故障次数超限")
                self.fault_exceeded = True
                return

            # 根据故障类型执行相应的复位操作
            if fault_type in ('Arc', 'Interlock'):
                self._reset_interlock_faults()
            elif fault_type in ('SSAComp', 'ReflectedPowerComp'):
                self._reset_pw_faults()

            # 故障复位后不自动打开RF，等待状态机重新初始化
            logger.info("故障已复位，等待状态机重新初始化")

    def _reset_interlock_faults(self):
        reset_pv = self.config.get_pv('fault.reset_interlock')
        logger.info(f"正在复位Interlock故障: {reset_pv}")
        logger.debug(f"步骤1: 设置reset PV为1")
        self.pv_manager.put(reset_pv, 1)
        time.sleep(1)
        logger.debug(f"步骤2: 设置reset PV为0")
        self.pv_manager.put(reset_pv, 0)
        time.sleep(2)
        logger.debug("Interlock故障复位完成")

    def _reset_pw_faults(self):
        reset_pv = self.config.get_pv('fault.ResetPWFaultStat')
        logger.info(f"正在复位功率故障: {reset_pv}")
        logger.debug(f"步骤1: 设置reset PV为1")
        self.pv_manager.put(reset_pv, 1)
        time.sleep(1)
        logger.debug(f"步骤2: 设置reset PV为0")
        self.pv_manager.put(reset_pv, 0)
        time.sleep(2)
        logger.debug("功率故障复位完成")

    def is_fault_exceeded(self):
        """
        检查故障是否超限

        Returns:
            bool: True表示故障次数超限需要停止
        """
        with self.lock:
            return self.fault_exceeded

    def get_fault_count(self):
        """
        获取故障次数

        Returns:
            int: 故障次数
        """
        with self.lock:
            return self.fault_count

    def record_fault(self):
        """
        手动记录故障

        用途：
        - 主控制器检测到RF意外关闭时调用
        - 不执行故障复位操作（因为RF已关闭）
        """
        with self.lock:
            self.fault_count += 1
            logger.warning(f"手动记录故障 (第{self.fault_count}次)")

            # 检查是否超过最大故障次数
            if self.fault_count >= self.config.loop['max_faults']:
                logger.error("故障次数超限")
                self.fault_exceeded = True

    def reset_fault_count(self):
        """
        重置故障计数

        用途：
        - Reset操作时清零计数
        - 重新开始老练流程
        """
        with self.lock:
            logger.info("重置故障计数")
            self.fault_count = 0
            self.fault_exceeded = False

    def cleanup(self):
        """清理资源，取消callback"""
        self.pv_arc.clear_callbacks()
        self.pv_interlock.clear_callbacks()
        self.pv_SSAComp.clear_callbacks()
        self.pv_ReflectedPowerComp.clear_callbacks()
        logger.info("故障监听器已停止")

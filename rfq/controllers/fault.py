#!/usr/bin/env python3
"""
故障处理模块 - 使用callback监听
负责故障检测和计数，复位由主控制器统一调度

故障PV（值为0表示故障，1表示正常）:
  - arc:          RFQ:LLRF:Con01:Arc_Status_Rd
  - VacInterlock: RFQ:LLRF:Con01:Interlock_Status_Rd
  - interlock2:   RFQ:LLRF:Con01:InterlockStatus2_Rd
  - di4:          RFQ:LLRF:Con01:di4

复位PV（每次故障均依次全部复位）:
  - VacReset:           RFQ:Reset
  - reset_interlock:    RFQ:LLRF:Con01:ResetInterlock
  - ResetPWFaultStat1:  RFQ:LLRF:Mon01:ResetPWFaultStat
  - ResetPWFaultStat2:  RFQ:LLRF:Mon02:ResetPWFaultStat

作者: Chengye Xu
日期: 2026-03
"""

import time
import logging
import threading
import epics
from ..utils.pv_manager import PVManager

logger = logging.getLogger('RFQ.FaultHandler')


class FaultHandler:
    """故障处理器 - 事件驱动版本（仅检测和计数，复位由主控制器调度）"""

    FAULT_PV_KEYS = ['fault.arc', 'fault.VacInterlock', 'fault.interlock2', 'fault.di4']
    FAULT_NAMES = ['Arc', 'VacInterlock', 'Interlock2', 'DI4']

    RESET_PV_KEYS = [
        ('VacReset',           'fault.VacReset',           2.0, 2.0),
        ('ResetInterlock',     'fault.reset_interlock',    1.0, 1.0),
        ('ResetPWFaultStat1',  'fault.ResetPWFaultStat1',  1.0, 1.0),
        ('ResetPWFaultStat2',  'fault.ResetPWFaultStat2',  1.0, 1.0),
    ]

    def __init__(self, config):
        """
        初始化故障处理器

        Args:
            config: 配置对象
        """
        self.config = config
        self.pv_manager = PVManager()

        self.fault_count = 0
        self.fault_exceeded = False
        self.lock = threading.Lock()
        self.last_fault_type = None

        self._pv_objects = []
        for pv_key in self.FAULT_PV_KEYS:
            pv_obj = epics.PV(self.config.get_pv(pv_key))
            pv_obj.add_callback(self._make_callback(pv_key))
            self._pv_objects.append(pv_obj)

        logger.info("故障监听器已启动 (arc / VacInterlock / interlock2 / di4)")

    def _make_callback(self, pv_key):
        """创建故障回调闭包"""
        name = pv_key.split('.')[-1]
        display_name = {
            'arc': 'Arc', 'VacInterlock': 'VacInterlock',
            'interlock2': 'Interlock2', 'di4': 'DI4',
        }.get(name, name)

        def callback(pvname=None, value=None, **kwargs):
            logger.debug(f"{display_name} PV变化: {pvname}={value}")
            if value == 0:
                with self.lock:
                    self.fault_count += 1
                    self.last_fault_type = display_name
                    logger.warning(
                        f"检测到{display_name}故障 (第{self.fault_count}次)"
                    )
                    if self.fault_count >= self.config.loop['max_faults']:
                        logger.error("故障次数超限")
                        self.fault_exceeded = True

        return callback

    def pulse_reset(self, pv_name, high_time=1.0, settle_time=1.0):
        """
        脉冲复位：置1 → 等待 → 置0 → 等待

        Args:
            pv_name: PV名称
            high_time: 高电平保持时间(秒)
            settle_time: 回落后等待时间(秒)
        """
        logger.info(f"  {pv_name} → 1")
        self.pv_manager.put(pv_name, 1)
        time.sleep(high_time)
        logger.info(f"  {pv_name} → 0")
        self.pv_manager.put(pv_name, 0)
        time.sleep(settle_time)

    def reset_all_faults(self):
        """
        依次复位所有故障PV（VacReset + Interlock + PWFaultStat1 + PWFaultStat2）

        供主控制器在故障恢复流程中调用
        """
        logger.info("开始执行全部故障复位...")
        for name, pv_key, high_t, settle_t in self.RESET_PV_KEYS:
            pv_name = self.config.get_pv(pv_key)
            logger.info(f"[{name}]")
            self.pulse_reset(pv_name, high_t, settle_t)
        logger.info("全部故障复位完成")

    def check_fault_status(self):
        """
        检查所有故障状态灯是否已恢复

        Returns:
            bool: True表示全部正常
        """
        all_ok = True
        for pv_key, name in zip(self.FAULT_PV_KEYS, self.FAULT_NAMES):
            val = self.pv_manager.get(self.config.get_pv(pv_key))
            if val == 1:
                logger.info(f"  {name}: 正常")
            elif val == 0:
                logger.warning(f"  {name}: 仍故障")
                all_ok = False
            else:
                logger.warning(f"  {name}: 无法读取(val={val})")
                all_ok = False
        if all_ok:
            logger.info("所有状态灯已恢复正常")
        else:
            logger.warning("复位后仍有未恢复的故障")
        return all_ok

    def is_fault_exceeded(self):
        """检查故障是否超限"""
        with self.lock:
            return self.fault_exceeded

    def get_fault_count(self):
        """获取故障次数"""
        with self.lock:
            return self.fault_count

    def get_last_fault_type(self):
        """获取最近一次故障类型"""
        with self.lock:
            return self.last_fault_type

    def reset_fault_count(self):
        """重置故障计数（用户手动Reset时调用）"""
        with self.lock:
            logger.info("重置故障计数")
            self.fault_count = 0
            self.fault_exceeded = False
            self.last_fault_type = None

    def cleanup(self):
        """清理资源，取消callback"""
        for pv_obj in self._pv_objects:
            pv_obj.clear_callbacks()
        self._pv_objects.clear()
        logger.info("故障监听器已停止")

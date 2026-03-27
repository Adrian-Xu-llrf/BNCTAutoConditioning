#!/usr/bin/env python3
"""
故障处理模块 - 使用callback监听
负责故障检测、计数和复位

故障PV（值为0表示故障，1表示正常）:
  - arc:          RFQ:LLRF:Con01:Arc_Status_Rd
  - VacInterlock: RFQ:LLRF:Con01:Interlock_Status_Rd  (故障时需先触发VacReset)
  - interlock2:   RFQ:LLRF:Con01:InterlockStatus2_Rd
  - di4:          RFQ:LLRF:Con01:di4

复位PV（所有故障均需依次复位）:
  - reset_interlock:  RFQ:LLRF:Con01:ResetInterlock
  - ResetPWFaultStat1: RFQ:LLRF:Mon01:ResetPWFaultStat
  - ResetPWFaultStat2: RFQ:LLRF:Mon02:ResetPWFaultStat

VacInterlock专有复位（需先于其他复位执行）:
  - VacReset: RFQ:Reset

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

        # 创建PV对象用于callback（所有故障PV值为0时表示故障，1表示正常）
        self.pv_arc = epics.PV(self.config.get_pv('fault.arc'))
        self.pv_vac_interlock = epics.PV(self.config.get_pv('fault.VacInterlock'))
        self.pv_interlock2 = epics.PV(self.config.get_pv('fault.interlock2'))
        self.pv_di4 = epics.PV(self.config.get_pv('fault.di4'))

        # 注册callback
        self.pv_arc.add_callback(self._on_arc_change)
        self.pv_vac_interlock.add_callback(self._on_vac_interlock_change)
        self.pv_interlock2.add_callback(self._on_interlock2_change)
        self.pv_di4.add_callback(self._on_di4_change)

        logger.info("故障监听器已启动 (arc / VacInterlock / interlock2 / di4)")

    # ==================== Callback函数 ====================

    def _on_arc_change(self, pvname=None, value=None, **kwargs):
        """Arc故障回调（value=0为故障）"""
        logger.debug(f"Arc PV变化: {pvname}={value}")
        if value == 0:
            threading.Thread(target=self._handle_fault, args=('Arc',), daemon=True).start()

    def _on_vac_interlock_change(self, pvname=None, value=None, **kwargs):
        """VacInterlock故障回调（value=0为故障）"""
        logger.debug(f"VacInterlock PV变化: {pvname}={value}")
        if value == 0:
            threading.Thread(target=self._handle_fault, args=('VacInterlock',), daemon=True).start()

    def _on_interlock2_change(self, pvname=None, value=None, **kwargs):
        """InterlockStatus2故障回调（value=0为故障）"""
        logger.debug(f"Interlock2 PV变化: {pvname}={value}")
        if value == 0:
            threading.Thread(target=self._handle_fault, args=('Interlock2',), daemon=True).start()

    def _on_di4_change(self, pvname=None, value=None, **kwargs):
        """DI4故障回调（value=0为故障）"""
        logger.debug(f"DI4 PV变化: {pvname}={value}")
        if value == 0:
            threading.Thread(target=self._handle_fault, args=('DI4',), daemon=True).start()

    # ==================== 故障处理 ====================

    def _handle_fault(self, fault_type):
        """
        处理故障事件：每次都执行完整复位（VacReset + 三步interlock复位）

        Args:
            fault_type: 故障类型名称（用于日志）
        """
        with self.lock:
            self.fault_count += 1
            logger.warning(f"检测到{fault_type}故障 (第{self.fault_count}次)")

            # 检查是否超过最大故障次数
            if self.fault_count >= self.config.loop['max_faults']:
                logger.error("故障次数超限")
                self.fault_exceeded = True
                return

            # 所有故障都先做VacReset，再做三步interlock复位
            self._reset_vac(fault_type)
            self._reset_all_faults(fault_type)

            # 复位后检查各状态灯是否恢复
            self._check_fault_status(fault_type)

            logger.info(f"{fault_type}故障处理完成，等待状态机重新初始化")

    def _reset_vac(self, fault_type):
        """
        触发真空复位（RFQ:Reset），仅VacInterlock故障时调用

        Args:
            fault_type: 故障类型名称（用于日志）
        """
        vac_reset_pv = self.config.get_pv('fault.VacReset')
        logger.info(f"[{fault_type}] VacReset ({vac_reset_pv}) → 1")
        self.pv_manager.put(vac_reset_pv, 1)
        time.sleep(4)   # 保持高电平1s后回弹
        logger.info(f"[{fault_type}] VacReset ({vac_reset_pv}) → 0")
        self.pv_manager.put(vac_reset_pv, 0)
        time.sleep(2)   # 等待复位生效
        logger.info(f"[{fault_type}] VacReset 完成")

    def _reset_all_faults(self, fault_type):
        """
        依次复位所有故障PV:
          1. ResetInterlock
          2. ResetPWFaultStat1
          3. ResetPWFaultStat2

        Args:
            fault_type: 故障类型名称（用于日志）
        """
        reset_pvs = [
            ('reset_interlock',  self.config.get_pv('fault.reset_interlock')),
            ('ResetPWFaultStat1', self.config.get_pv('fault.ResetPWFaultStat1')),
            ('ResetPWFaultStat2', self.config.get_pv('fault.ResetPWFaultStat2')),
        ]

        for name, pv in reset_pvs:
            logger.info(f"[{fault_type}] {name} ({pv}) → 1")
            self.pv_manager.put(pv, 1)
            time.sleep(1)
            logger.info(f"[{fault_type}] {name} ({pv}) → 0")
            self.pv_manager.put(pv, 0)
            time.sleep(1)

    def _check_fault_status(self, fault_type):
        """
        复位后检查除故障状态灯是否已恢复（1=正常, 0=仍故障）

        Args:
            fault_type: 故障类型名称（用于日志）
        """
        status_pvs = [
            ('Arc',          self.config.get_pv('fault.arc')),
            ('VacInterlock', self.config.get_pv('fault.VacInterlock')),
            ('Interlock2',   self.config.get_pv('fault.interlock2')),
            ('DI4',          self.config.get_pv('fault.di4')),
        ]
        all_ok = True
        for name, pv in status_pvs:
            val = self.pv_manager.get(pv)
            status_str = '✅ 正常' if val == 1 else ('❌ 仍故障' if val == 0 else f'⚠️ 无法读取(val={val})')
            logger.info(f"[{fault_type}] 状态检查 {name}: {status_str}")
            if val != 1:
                all_ok = False
        if all_ok:
            logger.info(f"[{fault_type}] 所有状态灯已恢复正常")
        else:
            logger.warning(f"[{fault_type}] 复位后仍有未恢复的故障！")

    # ==================== 供外部调用的接口 ====================

    def _reset_interlock_faults(self):
        """
        供控制器主动调用的复位入口（RF启动失败时使用）
        执行完整复位流程（不含VacReset）
        """
        logger.info("主动触发故障复位")
        self._reset_all_faults('Manual')

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
        self.pv_vac_interlock.clear_callbacks()
        self.pv_interlock2.clear_callbacks()
        self.pv_di4.clear_callbacks()
        logger.info("故障监听器已停止")

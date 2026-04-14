#!/usr/bin/env python3
"""
真空检测模块 - 使用callback监听
负责监测真空压力是否满足运行条件

作者: Chengye Xu
日期: 2026-03
"""

import logging
import threading

logger = logging.getLogger('RFQ.VacuumChecker')


class VacuumChecker:
    """真空检测器 - 事件驱动版本"""

    def __init__(self, config, pv_manager):
        """
        初始化真空检测器

        Args:
            config: 配置对象
            pv_manager: PVManager单例实例
        """
        self.config = config
        self.pv_manager = pv_manager
        self.lock = threading.Lock()

        self.vacuum_ok = False
        self.worst_vacuum = float('inf')
        self.worst_vacuum_pv = None
        self.vacuum_values = {}

        vacuum_pv_names = config.pv['vacuum']
        self._vacuum_keys = []
        for i, pv_name in enumerate(vacuum_pv_names):
            key = f'vacuum.{i}'
            self._vacuum_keys.append(key)
            self.vacuum_values[key] = float('inf')

            pv_obj = self.pv_manager.get_pv_object(key)
            if pv_obj:
                pv_obj.add_callback(self._on_vacuum_change, pv_key=key)

        for key in self._vacuum_keys:
            val = self.pv_manager.get(key)
            if val is not None:
                self._on_vacuum_change(value=float(val), pv_key=key)
            else:
                logger.warning(f"真空PV初始读取失败: {self.pv_manager.get_pv_name(key)}")

        logger.info(f"真空监听器已启动，监听{len(self._vacuum_keys)}个真空PV")

    def _on_vacuum_change(self, pvname=None, value=None, pv_key=None, **kwargs):
        """
        真空PV变化回调

        Args:
            value: PV值
            pv_key: PV逻辑键
        """
        if value is None:
            return

        with self.lock:
            self.vacuum_values[pv_key] = value
            pv_display = self.pv_manager.get_pv_name(pv_key) or pv_key
            logger.debug(f"真空PV更新: {pv_display}={value:.2e} Pa")

            self.worst_vacuum = 0.0
            self.worst_vacuum_pv = None

            for k, vac_val in self.vacuum_values.items():
                if vac_val > self.worst_vacuum:
                    self.worst_vacuum = vac_val
                    self.worst_vacuum_pv = self.pv_manager.get_pv_name(k) or k

            logger.debug(f"最差真空: {self.worst_vacuum:.2e} Pa @ {self.worst_vacuum_pv}")

            threshold = self.config.vacuum['threshold']
            recovery_ratio = self.config.vacuum.get('recovery_ratio', 0.8)
            recovery_threshold = threshold * recovery_ratio
            if self.worst_vacuum >= threshold:
                if self.vacuum_ok:
                    logger.warning(
                        f"真空超标: {self.worst_vacuum:.2e} Pa "
                        f"(阈值: {threshold:.2e} Pa) "
                        f"PV: {self.worst_vacuum_pv}"
                    )
                self.vacuum_ok = False
            elif self.worst_vacuum < recovery_threshold:
                if not self.vacuum_ok:
                    logger.info(
                        f"真空已恢复正常: {self.worst_vacuum:.2e} Pa "
                        f"(恢复阈值: {recovery_threshold:.2e} Pa)"
                    )
                self.vacuum_ok = True

    def is_vacuum_ok(self):
        """
        检查真空是否正常

        Returns:
            tuple: (bool, float, str)
                - 是否满足条件
                - 最差真空值
                - 最差真空PV名称
        """
        with self.lock:
            return self.vacuum_ok, self.worst_vacuum, self.worst_vacuum_pv

    def cleanup(self):
        """清理资源，取消callback"""
        for key in self._vacuum_keys:
            pv_obj = self.pv_manager.get_pv_object(key)
            if pv_obj:
                pv_obj.clear_callbacks()
        logger.info("真空监听器已停止")

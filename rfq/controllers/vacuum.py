#!/usr/bin/env python3
"""
真空检测模块 - 使用callback监听
负责监测真空压力是否满足运行条件

作者: Chengye Xu
日期: 2025-11
"""

import logging
import threading
import epics

logger = logging.getLogger('RFQ.VacuumChecker')


class VacuumChecker:
    """真空检测器 - 事件驱动版本"""

    def __init__(self, config):
        """
        初始化真空检测器

        Args:
            config: 配置对象
        """
        self.config = config
        self.lock = threading.Lock()

        # 真空状态（初始为False，等待首个callback确认后才可能变True）
        self.vacuum_ok = False
        self.worst_vacuum = float('inf')
        self.worst_vacuum_pv = None
        self.vacuum_values = {}  # 存储所有真空PV的当前值

        # 创建PV对象并注册callback
        # 初始值设为inf（保守fail-safe）：callback未到前视为真空超标，禁止启动
        self.pv_objects = []
        vacuum_pv_names = self.config.pv['vacuum']

        for pv_name in vacuum_pv_names:
            pv = epics.PV(pv_name)
            pv.add_callback(self._on_vacuum_change, pv_name=pv_name)
            self.pv_objects.append(pv)
            self.vacuum_values[pv_name] = float('inf')

        # 主动读取一次当前值，消除启动时callback未到的窗口
        for pv_name, pv in zip(vacuum_pv_names, self.pv_objects):
            val = pv.get()
            if val is not None:
                self._on_vacuum_change(pvname=pv_name, value=float(val), pv_name=pv_name)
            else:
                logger.warning(f"真空PV初始读取失败（未连接）: {pv_name}")

        logger.info(f"真空监听器已启动，监听{len(self.pv_objects)}个真空PV")

    def _on_vacuum_change(self, pvname=None, value=None, pv_name=None, **kwargs):
        """
        真空PV变化回调

        Args:
            pvname: PV名称（pyepics提供）
            value: PV值
            pv_name: 自定义PV名称参数
        """
        if value is None:
            return

        with self.lock:
            # 更新真空值
            actual_pv_name = pv_name if pv_name else pvname
            self.vacuum_values[actual_pv_name] = value
            logger.debug(f"真空PV更新: {actual_pv_name}={value:.2e} Pa")

            # 找出最差真空值
            self.worst_vacuum = 0.0
            self.worst_vacuum_pv = None

            for pv_n, vac_val in self.vacuum_values.items():
                if vac_val > self.worst_vacuum:
                    self.worst_vacuum = vac_val
                    self.worst_vacuum_pv = pv_n

            logger.debug(f"最差真空: {self.worst_vacuum:.2e} Pa @ {self.worst_vacuum_pv}")

            # 检查是否超标
            threshold = self.config.vacuum['threshold']
            if self.worst_vacuum >= threshold:
                if self.vacuum_ok:  # 从正常变为超标，记录日志
                    logger.warning(
                        f"真空超标: {self.worst_vacuum:.2e} Pa "
                        f"(阈值: {threshold:.2e} Pa) "
                        f"PV: {self.worst_vacuum_pv}"
                    )
                self.vacuum_ok = False
            else:
                if not self.vacuum_ok:  # 从超标恢复正常，记录日志
                    logger.info(f"真空已恢复正常: {self.worst_vacuum:.2e} Pa")
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
        for pv in self.pv_objects:
            pv.clear_callbacks()
        logger.info("真空监听器已停止")

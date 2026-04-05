#!/usr/bin/env python3
"""
PV管理模块
统一管理所有EPICS PV的注册、读写和连接状态

作者: Chengye Xu
日期: 2026-03
"""

import epics
import logging

logger = logging.getLogger('RFQ.PVManager')


class PVManager:
    """
    PV管理器 - 单例模式，长连接，key索引

    所有PV通过 register() 注册后，用 key（如 'rf.rf_on'）读写，
    内部维护 epics.PV 长连接对象，避免反复创建短连接。
    """

    _instance = None

    def __new__(cls, config=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config=None):
        if self._initialized:
            return
        self._initialized = True
        self.config = config
        self._pv_cache = {}
        self._pv_names = {}

    def register(self, pv_key, pv_name):
        """
        注册一个PV，建立长连接

        Args:
            pv_key: PV逻辑键，如 'rf.rf_on'
            pv_name: EPICS PV名称字符串
        """
        if pv_key in self._pv_cache:
            return
        self._pv_names[pv_key] = pv_name
        self._pv_cache[pv_key] = epics.PV(pv_name)
        logger.debug(f"PV注册: {pv_key} -> {pv_name}")

    def register_group(self, group_dict, prefix):
        """
        批量注册一组PV

        Args:
            group_dict: 字典 {key: pv_name}
            prefix: 前缀，如 'rf'
        """
        for key, pv_name in group_dict.items():
            full_key = f"{prefix}.{key}"
            self.register(full_key, pv_name)

    def register_list(self, pv_name_list, prefix):
        """
        批量注册列表形式的PV（如真空PV）

        Args:
            pv_name_list: PV名称字符串列表
            prefix: 前缀，如 'vacuum'
        """
        for i, pv_name in enumerate(pv_name_list):
            key = f"{prefix}.{i}"
            self.register(key, pv_name)

    def get(self, pv_key, timeout=3.0):
        """
        通过key读取PV值

        Args:
            pv_key: PV逻辑键
            timeout: 超时时间(秒)

        Returns:
            PV值，失败返回None
        """
        pv = self._pv_cache.get(pv_key)
        if pv is None:
            logger.error(f"PV未注册: {pv_key}")
            return None
        try:
            value = pv.get(timeout=timeout)
            if value is None:
                logger.error(f"读取PV失败: {pv_key} ({self._pv_names[pv_key]})")
            return value
        except Exception as e:
            logger.error(f"读取PV异常 {pv_key}: {e}")
            return None

    def put(self, pv_key, value, wait=False):
        """
        通过key写入PV值

        Args:
            pv_key: PV逻辑键
            value: 要写入的值
            wait: 是否等待写入完成

        Returns:
            bool: 成功返回True，失败返回False
        """
        pv = self._pv_cache.get(pv_key)
        if pv is None:
            logger.error(f"PV未注册: {pv_key}")
            return False
        try:
            pv.put(value, wait=wait)
            return True
        except Exception as e:
            logger.error(f"写入PV异常 {pv_key}: {e}")
            return False

    def get_pv_object(self, pv_key):
        """
        获取底层 epics.PV 对象（用于callback等高级操作）

        Args:
            pv_key: PV逻辑键

        Returns:
            epics.PV 对象，未注册返回None
        """
        return self._pv_cache.get(pv_key)

    def get_pv_name(self, pv_key):
        """
        获取PV的实际EPICS名称

        Args:
            pv_key: PV逻辑键

        Returns:
            str: PV名称，未注册返回None
        """
        return self._pv_names.get(pv_key)

    def is_connected(self, pv_key):
        """
        检查单个PV是否在线

        Args:
            pv_key: PV逻辑键

        Returns:
            bool
        """
        pv = self._pv_cache.get(pv_key)
        return pv is not None and pv.connected

    def check_all_connected(self):
        """
        校验所有已注册PV是否可达

        Returns:
            tuple: (bool, list)
                - bool: True=全部在线, False=存在不可达PV
                - list: [(pv_key, pv_name), ...] 不可达的PV列表
        """
        failed = []
        for pv_key, pv in self._pv_cache.items():
            if not pv.connected:
                failed.append((pv_key, self._pv_names[pv_key]))
        return (len(failed) == 0, failed)

    def get_registered_count(self):
        """获取已注册PV数量"""
        return len(self._pv_cache)

    @staticmethod
    def safe_status(text, max_chars=40, max_bytes=40):
        """
        将状态字符串限制在指定字符数与字节数以内

        Args:
            text: 原始文本
            max_chars: 最大字符数
            max_bytes: 最大字节数(UTF-8编码)

        Returns:
            str: 截断后的文本
        """
        s = str(text)
        if len(s) > max_chars:
            s = s[:max_chars - 1] + '…'

        enc = s.encode('utf-8', errors='replace')
        if len(enc) <= max_bytes:
            return s

        out = []
        used = 0
        for ch in s:
            b = ch.encode('utf-8', errors='replace')
            if used + len(b) > max_bytes:
                break
            out.append(ch)
            used += len(b)
        return ''.join(out)

    @classmethod
    def reset_instance(cls):
        """重置单例（仅用于测试）"""
        if cls._instance is not None:
            cls._instance._cleanup()
            cls._instance = None

    def _cleanup(self):
        """清理所有PV连接"""
        for pv_key, pv in self._pv_cache.items():
            try:
                pv.clear_callbacks()
                pv.disconnect()
            except Exception:
                pass
        self._pv_cache.clear()
        self._pv_names.clear()
        self._initialized = False

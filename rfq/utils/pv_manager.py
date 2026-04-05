#!/usr/bin/env python3
"""
PV管理模块
负责EPICS PV的读写操作

作者: Chengye Xu
日期: 2026-03
"""

import epics
import logging

logger = logging.getLogger('RFQ.PVManager')


class PVManager:
    """PV管理器"""

    @staticmethod
    def get(pv_name, timeout=3.0):
        """
        读取PV值（对应caget）

        Args:
            pv_name: PV名称
            timeout: 超时时间(秒)

        Returns:
            PV值，失败返回None
        """
        try:
            value = epics.caget(pv_name, timeout=timeout)
            if value is None:
                logger.error(f"读取PV失败: {pv_name}")
            return value
        except Exception as e:
            logger.error(f"读取PV异常 {pv_name}: {e}")
            return None

    @staticmethod
    def put(pv_name, value, wait=False):
        """
        写入PV值（对应caput）

        Args:
            pv_name: PV名称
            value: 要写入的值
            wait: 是否等待写入完成

        Returns:
            bool: 成功返回True，失败返回False
        """
        try:
            epics.caput(pv_name, value, wait=wait)
            return True
        except Exception as e:
            logger.error(f"写入PV异常 {pv_name}: {e}")
            return False

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
        # 先按字符数限制
        if len(s) > max_chars:
            s = s[:max_chars - 1] + '…'

        # 再按字节数限制
        enc = s.encode('utf-8', errors='replace')
        if len(enc) <= max_bytes:
            return s

        # 逐字符累计，确保UTF-8字节数不超过max_bytes
        out = []
        used = 0
        for ch in s:
            b = ch.encode('utf-8', errors='replace')
            if used + len(b) > max_bytes:
                break
            out.append(ch)
            used += len(b)
        return ''.join(out)

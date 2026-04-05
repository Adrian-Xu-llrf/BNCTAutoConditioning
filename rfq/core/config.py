#!/usr/bin/env python3
"""
配置加载模块
负责从yaml文件加载配置参数

作者: Chengye Xu
日期: 2026-03
"""

import yaml
import os


class Config:
    """配置管理类 - 简化版"""

    def __init__(self, config_file='config.yaml'):
        """
        初始化配置

        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"配置文件不存在: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            self._cfg = yaml.safe_load(f)

    def reload(self):
        """重新从文件加载配置（用于运行中热更新）"""
        with open(self.config_file, 'r', encoding='utf-8') as f:
            self._cfg = yaml.safe_load(f)

    def get(self, *keys, default=None):
        """
        获取配置值

        Args:
            *keys: 配置键路径，例如 get('power', 'target')
            default: 默认值

        Returns:
            配置值
        """
        value = self._cfg
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_pv(self, path):
        """
        获取PV名称（简化访问方式）

        Args:
            path: 点号分隔的路径，如 'rf.on' 或 'control.pulse_start'

        Returns:
            PV名称字符串

        Examples:
            config.get_pv('rf.on')              # 'iLinac_RFQ:LLRF_MC01:RFOn'
            config.get_pv('control.pulse_start') # 'iLinac_RFQ:LLRF:AutoC_PulseStart'
        """
        keys = ['pv'] + path.split('.')
        return self.get(*keys)

    # 简单的快捷访问属性
    @property
    def pv(self):
        """PV配置字典"""
        return self._cfg.get('pv', {})

    @property
    def power(self):
        """功率配置字典"""
        return self._cfg.get('power', {})

    @property
    def vacuum(self):
        """真空配置字典"""
        return self._cfg.get('vacuum', {})

    @property
    def loop(self):
        """循环配置字典"""
        return self._cfg.get('loop', {})

    @property
    def logging(self):
        """日志配置字典"""
        return self._cfg.get('logging', {})


# 全局配置实例
_config = None


def get_config(config_file='config.yaml'):
    """
    获取全局配置实例

    Args:
        config_file: 配置文件路径

    Returns:
        Config: 配置实例
    """
    global _config
    if _config is None:
        _config = Config(config_file)
    return _config

if __name__ == '__main__':
    config = get_config()
    # print(config.get_pv('vacuum'))
    # print(config.get_pv('control.pulse_start'))
    # print(config.loop)
    # print(config.logging)
"""
RFQ自动老练系统
采用状态机架构，模块化设计

子模块：
- core: 核心功能（状态、控制器、配置）
- controllers: 各种控制器（功率、脉冲、故障、真空）
- utils: 工具类（PV管理）

作者: Chengye Xu
日期: 2026-03
"""

# 导入核心模块
from .core import (
    RFQState,
    StateTransitionError,
    Config,
    get_config,
    RFQController,
)

# 导入控制器
from .controllers import (
    PowerController,
    PulseController,
    FaultHandler,
    VacuumChecker,
)

# 导入工具
from .utils import PVManager

__version__ = '3.0.0'

__all__ = [
    # 核心
    'RFQState',
    'StateTransitionError',
    'Config',
    'get_config',
    'RFQController',
    # 控制器
    'PowerController',
    'PulseController',
    'FaultHandler',
    'VacuumChecker',
    # 工具
    'PVManager',
]

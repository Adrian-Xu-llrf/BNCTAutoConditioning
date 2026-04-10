#!/usr/bin/env python3
"""
状态处理接口定义
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from ..core.state import RFQState

if TYPE_CHECKING:
    from ..core.controller import RFQController


class StateHandler(ABC):
    """统一状态处理接口"""

    def __init__(self, controller: 'RFQController'):
        self.controller = controller

    @abstractmethod
    def handle(self) -> Optional[RFQState]:
        """
        执行一个状态处理周期

        Returns:
            RFQState or None:
            - 返回目标状态：由 controller 执行状态迁移
            - 返回 None：保持当前状态不变
        """
        raise NotImplementedError

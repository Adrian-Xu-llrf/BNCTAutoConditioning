#!/usr/bin/env python3
"""
RFQ控制器状态定义
使用状态机模式管理系统状态

状态编号规则：
- 0-99: 正常运行状态
- 100+: 异常/终止状态

作者: Chengye Xu
日期: 2026-03
"""

from enum import Enum


class RFQState(Enum):
    """
    RFQ系统状态枚举

    使用有意义的编号便于：
    - EPICS PV显示和监控
    - 日志分析和问题定位
    - 与硬件系统对接
    - 预留扩展空间
    """

    # 正常流程状态 (0-99)
    IDLE = 0               # 空闲等待启动信号
    INITIALIZING = 10      # 初始化RF系统
    PAUSED = 15            # 已暂停
    ADJUSTING_POWER = 20   # 调节功率
    WAITING_VACUUM = 25    # 等待真空恢复
    EXPANDING_PULSE = 30   # 展宽脉冲
    COMPLETED = 90         # 老练完成

    # 异常状态 (100+)
    ERROR = 100            # 错误状态
    STOPPED = 101          # 用户停止

    def __str__(self):
        """返回状态的中文描述"""
        state_names = {
            RFQState.IDLE: "空闲等待",
            RFQState.INITIALIZING: "初始化中",
            RFQState.PAUSED: "已暂停",
            RFQState.ADJUSTING_POWER: "调节功率",
            RFQState.WAITING_VACUUM: "等待真空恢复",
            RFQState.EXPANDING_PULSE: "展宽脉冲",
            RFQState.COMPLETED: "老练完成",
            RFQState.ERROR: "错误",
            RFQState.STOPPED: "已停止",
        }
        return state_names.get(self, "未知状态")

    def get_code(self):
        """
        返回状态编号

        用途：
        - 写入EPICS状态码PV
        - 日志记录
        - 状态监控

        Returns:
            int: 状态编号
        """
        return self.value

    @classmethod
    def from_code(cls, code):
        """
        从编号获取状态

        Args:
            code: 状态编号

        Returns:
            RFQState: 对应的状态枚举

        Raises:
            ValueError: 编号无效
        """
        for state in cls:
            if state.value == code:
                return state
        raise ValueError(f"无效的状态编号: {code}")


class StateTransitionError(Exception):
    """非法状态转换异常"""
    pass


# 合法状态转换表：定义每个状态可以转换到哪些目标状态
# 用于 set_state() 中校验状态跳转合法性，防止非法跳转
# 注意：IDLE 可从任何状态到达（通过 reset()），各活动状态也可直接转到 ERROR/STOPPED（通过异常处理）
LEGAL_TRANSITIONS = {
    RFQState.IDLE: {RFQState.INITIALIZING, RFQState.STOPPED},
    RFQState.INITIALIZING: {RFQState.ADJUSTING_POWER, RFQState.WAITING_VACUUM, RFQState.ERROR, RFQState.PAUSED, RFQState.STOPPED, RFQState.IDLE},
    RFQState.ADJUSTING_POWER: {RFQState.EXPANDING_PULSE, RFQState.WAITING_VACUUM, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.COMPLETED, RFQState.IDLE},
    RFQState.WAITING_VACUUM: {RFQState.ADJUSTING_POWER, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.IDLE},
    RFQState.EXPANDING_PULSE: {RFQState.ADJUSTING_POWER, RFQState.WAITING_VACUUM, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.COMPLETED, RFQState.IDLE},
    RFQState.PAUSED: {RFQState.IDLE, RFQState.ADJUSTING_POWER, RFQState.EXPANDING_PULSE, RFQState.WAITING_VACUUM, RFQState.STOPPED},
    RFQState.ERROR: {RFQState.IDLE},
    RFQState.STOPPED: {RFQState.IDLE},
    RFQState.COMPLETED: {RFQState.IDLE},
}

# 状态机改进文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块一 (#2, #10)

---

## 改进概览

| 编号 | 问题 | 改进内容 | 涉及文件 |
|------|------|----------|----------|
| #2 | 状态转换无约束 + 主循环永不退出 | 添加合法转换表校验、重写主循环语义 | `state.py`, `controller.py` |
| #10 | `state_enter_time` 双重语义 | 新增 `_pulse_step_start_time` 独立计时 | `controller.py` |

---

## #2 — 状态转换校验与主循环语义

### 改进前

```python
# state.py — StateTransitionError 定义但从未使用
class StateTransitionError(Exception):
    pass

# controller.py — set_state() 无任何校验
def set_state(self, new_state):
    if self.current_state != new_state:
        self.current_state = new_state
        self.state_enter_time = time.time()

# terminal_states 为空集，while 条件恒为 True
self.terminal_states = frozenset()
while self.current_state not in self.terminal_states:
    handler()
```

### 改进后

#### 1. 合法转换表 (`state.py`)

新增 `LEGAL_TRANSITIONS` 字典，明确每个状态允许跳转到的目标状态集合：

```python
LEGAL_TRANSITIONS = {
    RFQState.IDLE: {RFQState.INITIALIZING, RFQState.STOPPED},
    RFQState.INITIALIZING: {RFQState.ADJUSTING_POWER, RFQState.ERROR, RFQState.PAUSED, RFQState.STOPPED, RFQState.IDLE},
    RFQState.ADJUSTING_POWER: {RFQState.EXPANDING_PULSE, RFQState.WAITING_VACUUM, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.COMPLETED, RFQState.IDLE},
    RFQState.WAITING_VACUUM: {RFQState.ADJUSTING_POWER, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.IDLE},
    RFQState.EXPANDING_PULSE: {RFQState.ADJUSTING_POWER, RFQState.WAITING_VACUUM, RFQState.PAUSED, RFQState.ERROR, RFQState.STOPPED, RFQState.COMPLETED, RFQState.IDLE},
    RFQState.PAUSED: {RFQState.IDLE, RFQState.ADJUSTING_POWER, RFQState.EXPANDING_PULSE, RFQState.WAITING_VACUUM, RFQState.STOPPED},
    RFQState.ERROR: {RFQState.IDLE},
    RFQState.STOPPED: {RFQState.IDLE},
    RFQState.COMPLETED: {RFQState.IDLE},
}
```

**设计说明**:
- 活动状态（ADJUSTING_POWER, WAITING_VACUUM, EXPANDING_PULSE）均允许直接跳转到 IDLE，因为 `reset()` 可从任何状态调用
- 终止状态（ERROR, STOPPED, COMPLETED）只能通过 reset 回到 IDLE

#### 2. set_state() 转换校验 (`controller.py`)

```python
def set_state(self, new_state):
    if self.current_state == new_state:
        return

    allowed = LEGAL_TRANSITIONS.get(self.current_state, set())
    if new_state not in allowed:
        raise StateTransitionError(
            f"非法状态转换: {self.current_state} -> {new_state}，"
            f"允许的目标状态: {[s.name for s in allowed]}"
        )

    old_state = self.current_state
    self.current_state = new_state
    self.state_enter_time = time.time()
    self._pulse_step_start_time = 0
    logger.info(f"状态转换: {old_state} -> {new_state}")
    self.update_status(new_state.name)
```

#### 3. 主循环双层结构 (`controller.py`)

```python
self.terminal_states = frozenset({
    RFQState.COMPLETED, RFQState.ERROR, RFQState.STOPPED,
})

def run(self):
    while True:
        # 内层循环：运行到到达终止状态
        while self.current_state not in self.terminal_states:
            handler = self.state_handlers.get(self.current_state)
            handler()

        # 执行终止状态的最后一次清理
        handler = self.state_handlers.get(self.current_state)
        if handler:
            handler()

        # 等待 reset 信号恢复
        while self.current_state in self.terminal_states:
            self._sleep(1)
            if self._get_pv('control.reset') == 1:
                self._put_pv('control.reset', 0)
                self.reset()
```

**语义对比**:

| | 改进前 | 改进后 |
|---|--------|--------|
| terminal_states | 空集 | {COMPLETED, ERROR, STOPPED} |
| 主循环条件 | 恒为 True（误导性） | 到达终止状态时退出内层循环 |
| 终止后行为 | 依赖 handler 内部轮询 | 显式的 reset 监听循环 |
| 状态转换保护 | 无 | LEGAL_TRANSITIONS 校验 + StateTransitionError |

#### 4. 异常处理增强

```python
except KeyboardInterrupt:
    self._shutdown_rf()          # 显式关闭 RF
    self.set_state(RFQState.STOPPED)
    self._handle_stopped()

except StateTransitionError as e:
    self._shutdown_rf()
    self.error_message = str(e)
    self.set_state(RFQState.ERROR)
```

---

## #10 — 展脉宽计时器语义分离

### 改进前

`state_enter_time` 承载两种语义：
1. 进入当前状态的时间（由 `set_state` 设置）
2. 展脉宽步骤的开始时间（由 `_handle_expanding_pulse` 重置）

这导致 `state_enter_time` 的值不稳定，无法用于需要"进入状态时间"语义的场景。

### 改进后

新增 `_pulse_step_start_time` 字段，专门用于展脉宽步骤计时：

```python
# __init__ 中
self.state_enter_time = 0           # 进入当前状态的时间（set_state 管理）
self._pulse_step_start_time = 0     # 展脉宽步骤计时（EXPANDING_PULSE 内部管理）

# set_state() 中重置
self._pulse_step_start_time = 0

# _handle_expanding_pulse() 中
# 首次进入时用 state_enter_time 初始化
if self._pulse_step_start_time == 0:
    self._pulse_step_start_time = self.state_enter_time

elapsed = time.time() - self._pulse_step_start_time  # 替代 time.time() - self.state_enter_time

# 每次展脉宽步骤完成后重置
self._pulse_step_start_time = time.time()  # 替代 self.state_enter_time = time.time()
```

---

## 状态转换图

```
                    ┌──────────────────────────────────┐
                    │         IDLE (0)                  │
                    └──────────┬───────────────────────┘
                               │ start=1
                    ┌──────────▼───────────────────────┐
               ┌───►│     INITIALIZING (10)             │
               │    └──────────┬───────────────────────┘
               │               │ init完成
               │    ┌──────────▼───────────────────────┐
        reset  │    │   ADJUSTING_POWER (20) ◄─────────┤─ 真空恢复
               │    └──┬──────┬──────────┬─────────────┘
               │       │      │ 功率达标  │ 真空不达标
               │       │      ▼          ▼
               │       │  EXPANDING    WAITING_VACUUM (25)
               │       │  PULSE (30)      │
               │       │      │          │
               │       │      ▼ 展脉宽完成
               │       │  [下一目标 / COMPLETED]
               │       │
               │    ┌──▼───────────────────────────────┐
               │    │     PAUSED (15)                   │
               │    └──────────────────────────────────┘
               │
        ┌──────▼───────────────────────────────────────┐
        │  ERROR (100) / STOPPED (101) / COMPLETED (90) │
        └───────────────────────────────────────────────┘
                          │ reset
                          └──► IDLE
```

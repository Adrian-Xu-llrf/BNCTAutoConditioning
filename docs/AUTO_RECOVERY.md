# 自动恢复与安全改进文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块三 (#3, #6, #7, #20)

---

## 改进概览

| 编号 | 问题 | 风险等级 | 改进内容 | 涉及文件 |
|------|------|----------|----------|----------|
| #3A | 跨状态协调标志被意外清除 | 高 | 自动恢复不清除 `_wait_before_power`/`_need_reset_pulse` | `controller.py` |
| #3B | start=0 竞态导致卡死 | 中 | RF掉线恢复前校验 start 信号 | `controller.py` |
| #6 | 降功率循环阻塞无法停止 | 高 | 添加 `should_stop` 回调和迭代上限 | `pulse.py`, `controller.py` |
| #7 | original_pulse_start 刷新策略不明 | 中 | 手动 reset 时刷新 | `controller.py` |
| #20 | KeyboardInterrupt 处理不完整 | 低 | 显式调用 `rf_manager.shutdown()` | `controller.py` |

---

## #3A — 跨状态协调标志保护

### 问题

RF Trip 自动恢复时，`reset(clear_faults=False)` 会清除 `_wait_before_power` 和 `_need_reset_pulse` 标志。如果 Trip 发生在 EXPANDING_PULSE → ADJUSTING_POWER 转换期间（此时 `_wait_before_power=True`），恢复后这些标志丢失，导致 RF 刚恢复就立即提升功率。

### 修复

将协调标志的清除逻辑从公共 `reset()` 移入 `_reset_manual()` 中：

```python
def reset(self, clear_faults=True):
    # 公共清理...
    self.power_controller.reset_iteration_count()
    # 不再在此处清除协调标志

    if clear_faults:
        self._reset_manual()    # 手动复位会清除协调标志
    else:
        self._reset_auto_recovery()  # 自动恢复保留协调标志

def _reset_manual(self):
    self._wait_before_power = False   # 仅手动复位清除
    self._need_reset_pulse = False
    # ...

def _reset_auto_recovery(self):
    # 不清除 _wait_before_power / _need_reset_pulse
    # ...
```

---

## #3B — start=0 竞态条件保护

### 问题

在 `_check_common_conditions` 中，如果 `start` 从 1 变为 0（刚好在暂停检查之后、RF 检查之前），自动恢复会将状态设为 IDLE，但此时 `start` 已经是 0，系统会卡在 IDLE 无限等待。

### 修复

在 `_check_rf_status()` 的自动恢复路径中，确认 start 信号仍为 1：

```python
def _check_rf_status(self):
    if rf_on != 1 and not self.fault_handler.is_fault_exceeded():
        # 新增：确认 start 信号仍为1
        if self._get_pv('control.start') != 1:
            logger.warning("RF掉线且start信号已清除，转为ERROR状态")
            self.error_message = "RF掉线且start信号已清除"
            return RFQState.ERROR

        # 正常自动恢复路径
        self.fault_handler.reset_all_faults()
        self.fault_handler.check_fault_status()
        self.reset(clear_faults=False)
        return RFQState.IDLE
```

---

## #6 — 展脉宽降功率循环安全

### 问题

`PulseController.expand()` 中，`reduce_power_before_expand=True` 时的 while 循环可能执行很久，期间无法响应停止信号。

### 修复

1. 添加 `should_stop` 回调参数
2. 每次迭代检查回调
3. 添加最大迭代次数保护

```python
def expand(self, ..., should_stop=None):
    max_iterations = int((current - target) / step) + 10  # 安全上限
    iteration = 0
    while current - step > target:
        if should_stop and should_stop():
            return False, "用户停止（降功率中断）"
        iteration += 1
        if iteration > max_iterations:
            logger.warning(f"降功率循环超过安全上限({max_iterations}次)，强制退出")
            break
        current -= step
        self.pv_manager.put(current_drive_key, current)
        time.sleep(1.0)
```

**调用方传入回调**:
```python
pulse_ok, pulse_msg = self.pulse_controller.expand(
    ...,
    should_stop=lambda: self._get_pv('control.start') == 0,
)
```

---

## #7 — original_pulse_start 刷新策略

### 策略

- **手动 reset**: 始终从 PV 重新读取并刷新 `original_pulse_start`
- **自动恢复**: 不刷新，保持 Trip 前的值作为脉宽回退下限

这在 `_reset_manual()` 中已实现：
```python
pulse_start_from_pv = self._get_pv('control.pulse_start')
if pulse_start_from_pv is not None:
    p.pulse_start = pulse_start_from_pv
    p.original_pulse_start = pulse_start_from_pv  # 刷新
```

---

## #20 — KeyboardInterrupt 处理

### 修复

在 `run()` 的 `KeyboardInterrupt` 处理中，显式调用 `rf_manager.shutdown()` 确保 RF 关闭：

```python
except KeyboardInterrupt:
    logger.warning("用户中断 (Ctrl+C)")
    self.rf_manager.shutdown()       # 显式关闭RF，不依赖 terminal_cleaned 判断
    self.error_message = "用户中断"
    self.set_state(RFQState.STOPPED)
    self._handle_stopped()
```

同样在 `StateTransitionError` 和通用 `Exception` 处理中也显式调用 `shutdown()`。

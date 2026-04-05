# 子控制器改进文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块五 (#5, #9, #14)

---

## 改进概览

| 编号 | 问题 | 改进内容 | 涉及文件 |
|------|------|----------|----------|
| #5 | 子控制器硬编码 `time.sleep()` | 构造函数接受 `sleep_func` 参数 | `power.py`, `pulse.py` |
| #9 | 日志重复打印 | 统一策略：子控制器打印 info，主控制器降为 debug | `power.py`, `controller.py` |
| #14 | 异常捕获过于宽泛 | 区分 EPICS 通信异常和逻辑异常 | `controller.py` |

---

## #5 — sleep 函数注入

### 问题

主控制器有 `_sleep()` 方法用于测试替换，但子控制器直接使用 `time.sleep()`，导致：
- 单元测试中无法跳过等待
- 测试运行缓慢

### 修复

`PowerController` 和 `PulseController` 构造函数新增 `sleep_func` 参数：

```python
class PowerController:
    def __init__(self, config, pv_manager, sleep_func=None):
        self._sleep = sleep_func or time.sleep
        # ...

class PulseController:
    def __init__(self, config, pv_manager, sleep_func=None):
        self._sleep = sleep_func or time.sleep
        # ...
```

所有 `time.sleep()` 调用替换为 `self._sleep()`：

```python
# power.py
self._sleep(2)  # 替代 time.sleep(2)

# pulse.py
self._sleep(1.0)  # 替代 time.sleep(1.0)
self._sleep(2)    # 替代 time.sleep(2)
```

**测试中的使用**:
```python
# 测试时注入零延迟函数
controller = PowerController(config, pv_manager, sleep_func=lambda x: None)
```

---

## #9 — 日志去重

### 问题

`PowerController.adjust()` 中同一条消息先 `logger.debug(msg)` 再 `logger.info(msg)`，实际效果是消息在两个层级各打了一次。主控制器中 `logger.debug(power_msg)` 注释说"sub-controller 内部已打印，此处降为 debug 避免重复"。

### 修复

**统一策略**：
- **子控制器**：打印 `logger.info(msg)` — 包含完整的调节信息
- **主控制器**：`logger.debug(msg)` — 避免重复，仅在 DEBUG 级别可见

移除 `PowerController` 中的冗余 `logger.debug(msg)`，只保留一条 `logger.info(msg)`。

---

## #14 — 异常处理细化

### 问题

`_handle_initializing` 中 `except Exception as e` 捕获所有异常，可能隐藏需要关注的 bug。

### 修复

区分 EPICS 通信异常和逻辑异常：

```python
except Exception as e:
    import epics.ca
    if isinstance(e, (epics.ca.ChannelAccessException, TimeoutError, OSError)):
        logger.error(f"EPICS通信异常: {e}")
    else:
        logger.error(f"初始化逻辑异常: {e}", exc_info=True)
    self.error_message = f"初始化异常: {e}"
    self.set_state(RFQState.ERROR)
```

**行为差异**：
- EPICS 通信异常：只打印错误消息（不需要完整堆栈）
- 逻辑异常：打印完整堆栈（`exc_info=True`），便于调试定位代码问题

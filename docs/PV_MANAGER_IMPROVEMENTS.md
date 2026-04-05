# PV管理器改进文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块四 (#4, #17)

---

## 改进概览

| 编号 | 问题 | 改进内容 | 涉及文件 |
|------|------|----------|----------|
| #4 | 单例线程不安全 | `__new__` 和 `reset_instance()` 加锁 | `pv_manager.py` |
| #17 | safe_status 双重截断 | 移除字符数截断，仅按字节截断 | `pv_manager.py` |

---

## #4 — 单例线程安全

### 问题

`PVManager` 单例通过 `__new__` + `_initialized` 实现，但 `reset_instance()` 没有加锁。`FaultHandler` 和 `VacuumChecker` 的回调在 epics 线程中运行，如果在回调触发期间调用 `reset_instance()`，可能导致竞态条件。

### 修复

引入 `threading.Lock` 保护 `__new__` 和 `reset_instance()`：

```python
import threading

class PVManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            if cls._instance is not None:
                cls._instance._cleanup()
                cls._instance = None
```

---

## #17 — safe_status 截断修复

### 问题

原实现先按字符截到 40，再按字节截到 40。对于中文文本（每字 3 字节），40 字符可能对应 120 字节，最终会被截到约 13 个中文字，造成信息丢失。

### 修复

移除字符数限制，仅按字节截断：

```python
@staticmethod
def safe_status(text, max_bytes=40):
    s = str(text)
    enc = s.encode('utf-8', errors='replace')
    if len(enc) <= max_bytes:
        return s

    # 只按字节截断
    out = []
    used = 0
    for ch in s:
        b = ch.encode('utf-8', errors='replace')
        if used + len(b) > max_bytes:
            break
        out.append(ch)
        used += len(b)
    return ''.join(out)
```

**效果对比**:

| 输入 | 改进前 | 改进后 |
|------|--------|--------|
| `"EXPANDING_PULSE"` (16字符) | `"EXPANDING_PULSE"` | `"EXPANDING_PULSE"` |
| `"展宽脉冲进行中，当前100ms"` (12中文字+数字) | 被双重截断到约5字 | `"展宽脉冲进行中，"` (约40字节) |

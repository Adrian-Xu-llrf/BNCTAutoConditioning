# 配置与基础设施改进文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块六 (#11, #12, #15, #18, #19)

---

## 改进概览

| 编号 | 问题 | 改进内容 | 涉及文件 |
|------|------|----------|----------|
| #11 | `Config.get()` 对 None 值处理有隐患 | 改用 `key in value` 检查 | `config.py` |
| #12 | PV key 魔法字符串散落 | 新增 `PVKeys` 常量类 | 新增 `pv_keys.py` |
| #15 | `config.reload()` 频繁磁盘 IO | 新增 `reload_if_changed()` | `config.py`, `controller.py` |
| #18 | 缺少类型注解 | 逐步添加到公共 API | 多文件 |
| #19 | 缺少依赖声明文件 | 新增 `requirements.txt` | 新增 |

---

## #11 — Config.get() None 值处理

### 问题

原实现使用 `value.get(key)` 返回 None 时视为"未找到"，但 YAML 中显式设为 `null` 的值也会返回 None，导致配置意图被静默忽略。

### 修复

改为 `key in value` 检查，区分"键不存在"和"值为 null"：

```python
# 改进前
for key in keys:
    if isinstance(value, dict):
        value = value.get(key)
        if value is None:       # null 值也被当作"未找到"
            return default

# 改进后
for key in keys:
    if isinstance(value, dict) and key in value:
        value = value[key]
    else:
        return default          # 仅键不存在时返回默认值
```

---

## #12 — PVKeys 常量类

### 新文件: `rfq/core/pv_keys.py`

集中定义所有 PV 逻辑键常量，替代散落在各文件中的魔法字符串：

```python
class PVKeys:
    # RF 控制
    RF_ON = 'rf.rf_on'
    RF_POWER = 'rf.power'
    PULSE_DRIVE = 'rf.pulse_drive'
    CW_DRIVE = 'rf.cw_drive'
    PULSE_CW = 'rf.pulse_cw'
    PULSE_TIME = 'rf.pulse_time'
    SWEEP = 'rf.sweep'
    TRACKING = 'rf.tracking'

    # 故障 PV
    FAULT_ARC = 'fault.arc'
    FAULT_VAC_INTERLOCK = 'fault.VacInterlock'
    # ...

    # 控制 PV
    CONTROL_START = 'control.start'
    CONTROL_RESET = 'control.reset'
    CONTROL_STATUS = 'control.status'
    CONTROL_POWER_TARGETS = 'control.power_targets'
    CONTROL_INIT_DRIVE = 'control.init_drive'
    CONTROL_PULSE_START = 'control.pulse_start'
    CONTROL_PULSE_END = 'control.pulse_end'
    # ...
```

**使用方式**（渐进式迁移，不强制一次性替换）:
```python
# 旧
self._get_pv('rf.rf_on')
# 新（可选）
self._get_pv(PVKeys.RF_ON)
```

---

## #15 — 按需重载配置

### 问题

每次调用 `_load_parameters()` 都执行 `config.reload()`，每次都有磁盘 IO。暂停恢复时尤其频繁。

### 修复

新增 `Config.reload_if_changed()` 方法，仅当文件修改时间变化时才重新加载：

```python
class Config:
    def __init__(self, config_file='config.yaml'):
        self._last_mtime = 0
        # ...
        self._last_mtime = os.path.getmtime(config_file)

    def reload_if_changed(self):
        """仅在配置文件修改后重新加载"""
        current_mtime = os.path.getmtime(self.config_file)
        if current_mtime != self._last_mtime:
            self.reload()
            return True
        return False
```

控制器中的调用已从 `config.reload()` 更新为 `config.reload_if_changed()`。

---

## #18 — 类型注解（渐进式添加）

在新增和修改的公共 API 上添加了类型注解：

**params.py** — `ConditioningParams` 使用 `@dataclass`，自带类型注解：
```python
@dataclass
class ConditioningParams:
    target_power: float = 0.0
    pulse_start: float = 1.0
    power_targets: List[float] = field(default_factory=list)
    original_pulse_start: Optional[float] = None
```

**rf_manager.py** — 公共方法添加返回值注解：
```python
def setup_mode(self, pulse_start: float) -> bool:
def startup(self, init_drive: float) -> bool:
def shutdown(self) -> None:
```

---

## #19 — 依赖声明

### 新文件: `requirements.txt`

```
pyepics>=3.4
pyyaml>=6.0
```

安装方式:
```bash
pip install -r requirements.txt
```

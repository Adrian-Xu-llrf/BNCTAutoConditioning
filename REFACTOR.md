# RFQ AutoConditioning 重构计划

> **目标：** 纯重构，不改变任何行为。提升可读性和模块化，让每个文件职责单一、行数合理（< 350行）。

---

## 问题诊断

`rfq/core/controller.py`（820行）是整个项目最大的问题，它同时承担：

- 参数从 PV 加载（`_load_parameters`）
- RF 硬件操作（`_setup_rf_mode` / `_startup_rf` / `_shutdown_rf`）
- 状态机编排（`run` / `set_state`）
- 9 个状态处理函数（`_handle_idle` 等）
- Trip 后脉宽下降逻辑（`reset`）

此外还有若干小问题散布在各文件中。

---

## 改动概览

### 新增文件

| 文件 | 职责 |
|------|------|
| `rfq/core/rf_operator.py` | RF 硬件操作：startup / shutdown / mode setup |
| `rfq/core/handlers.py` | 9 个状态处理函数（Mixin 类） |

### 修改文件

| 文件 | 改动内容 | 行数变化 |
|------|---------|---------|
| `rfq/core/controller.py` | 提取 RF 操作和状态处理后的精简版 | 820 → ~350 |
| `rfq/controllers/fault.py` | 4 个重复回调 → 回调工厂函数 | 249 → ~235 |
| `rfq/utils/pv_manager.py` | 提升为模块级函数 + 向后兼容 shim | 92 → ~100 |
| `rfq/controllers/power.py` | magic sleep 数字 → 命名常量 | +4 行 |
| `rfq/controllers/pulse.py` | magic sleep 数字 → 命名常量 | +3 行 |

### 不改动文件

`main.py`、`config.yaml`、`rfq/core/state.py`、`rfq/core/config.py`、
`rfq/controllers/vacuum.py`、`tests/sim_ioc.py`

---

## 重构后的文件结构

```
rfq/
├── core/
│   ├── state.py          (92 行)   ← 不变
│   ├── config.py         (125 行)  ← 不变
│   ├── rf_operator.py    (~100 行) ← 新增：RF 硬件操作
│   ├── handlers.py       (~250 行) ← 新增：9 个状态处理函数
│   └── controller.py     (~350 行) ← 精简：只含状态机骨架
├── controllers/
│   ├── power.py          (~124 行) ← 小改：sleep 常量
│   ├── pulse.py          (~100 行) ← 小改：sleep 常量
│   ├── fault.py          (~235 行) ← 中改：回调工厂
│   └── vacuum.py         (118 行)  ← 不变
└── utils/
    └── pv_manager.py     (~100 行) ← 小改：模块级函数
```

---

## 分步执行计划

执行顺序按风险从低到高排列，每步独立可验证。  
**约束：Phase 5/6 仅在 Phase 0~4 全部回归通过后执行。**

---

### Phase 0 — 基线固化（重构前，必须先做）

**目的：** 为“行为不变”提供可比对基线，避免只靠主观判断。

1. 保存一轮基线日志（至少 INFO 级），覆盖：
   - 正常流程（IDLE → COMPLETED）
   - arc 故障恢复
   - VacInterlock 故障恢复
2. 记录关键状态序列与关键 PV 写入序列（`rf_on` / `pulse_time` / `current_target_power` / `status`）。
3. 固化一份“通过标准”：重构后状态序列一致、关键分支结果一致（允许日志时间戳不同）。

---

### Phase 1 — 零风险语法修复（3 处独立改动）

#### 1A：PVManager — 提取模块级函数，保留向后兼容 shim

**文件：** `rfq/utils/pv_manager.py`

`get`、`put`、`safe_status` 三个 `@staticmethod` 提升为模块级函数，
`PVManager` 类保留为向后兼容别名，**所有调用方无需任何改动**：

```python
def get(pv_name, timeout=3.0): ...
def put(pv_name, value, wait=False): ...
def safe_status(text, max_chars=40, max_bytes=40): ...

class PVManager:
    """向后兼容别名"""
    get = staticmethod(get)
    put = staticmethod(put)
    safe_status = staticmethod(safe_status)
```

---

#### 1B：`_load_parameters()` 中的临时变量去 `self` 污染

**文件：** `rfq/core/controller.py`

以下 6 个变量只在 `_load_parameters()` 内部使用，但被错误地挂在 `self` 上，
污染实例的 `__dict__`，在调试器里会造成误导。改为局部变量：

| 改前 | 改后 |
|------|------|
| `self.pulse_step_pv` | `pulse_step_pv` |
| `self.pulse_step_val` | `pulse_step_val` |
| `self.wait_time_pv` | `wait_time_pv` |
| `self.wait_time_val` | `wait_time_val` |
| `self.wait_before_expand_pv` | `wait_before_expand_pv` |
| `self.wait_before_expand_val` | `wait_before_expand_val` |

---

#### 1C：消除重复定义，但保留语义别名

**文件：** `rfq/core/controller.py` `__init__`

`active_states` 和 `states_need_rf` 内容完全相同：

```python
# 当前（重复）
self.active_states  = frozenset({ADJUSTING_POWER, WAITING_VACUUM, EXPANDING_PULSE})
self.states_need_rf = frozenset({ADJUSTING_POWER, WAITING_VACUUM, EXPANDING_PULSE})

# 改后（单一来源 + 语义保留）
self.active_states = frozenset({ADJUSTING_POWER, WAITING_VACUUM, EXPANDING_PULSE})
self.states_need_rf = self.active_states  # 语义别名：当前一致，未来可独立扩展
```

> 不建议直接删除 `states_need_rf` 名称；它在语义上表达“需要 RF on 检查”的状态集合。

---

### Phase 2 — 提取 PV 读取 fallback 公共方法

**文件：** `rfq/core/controller.py`

`_load_parameters()` 中有 3 处完全相同的"读 PV → 类型转换 → 异常 fallback"模式，
提取为私有方法（放在 `_load_parameters()` 前面）：

```python
def _load_pv_with_fallback(self, pv_key, config_keys, hardcoded_default, param_name):
    """读取 PV 值，失败时回退到 config 默认值或硬编码默认值"""
    raw = self._get_pv(pv_key)
    default = float(self.config.get(*config_keys, default=hardcoded_default))
    try:
        return float(raw) if raw is not None else default
    except (ValueError, TypeError):
        logger.warning(f"{param_name} PV读取失败，使用默认值 {default}")
        return default
```

`_load_parameters()` 中三处重复代码替换为：

```python
self.pulse_step = self._load_pv_with_fallback(
    'control.pulse_step', ('loop', 'pulse_step'), 0.5, 'pulse_step')

self.wait_time = self._load_pv_with_fallback(
    'control.pulse_wait', ('loop', 'wait_time_default'), 10.0, 'pulse_wait')

self.wait_before_expand = self._load_pv_with_fallback(
    'control.wait_before_expand', ('loop', 'wait_after_expand'), 10.0, 'wait_before_expand')
```

> 说明：`config.yaml` 当前使用 `wait_after_expand`，这里一并对齐，修复“PV 读取失败时默认值来源错误”的预存问题。

---

### Phase 3 — 简化 FaultHandler 回调（孤立文件，风险低）

**文件：** `rfq/controllers/fault.py`

4 个几乎相同的回调方法替换为回调工厂，删除原来 4 个 `_on_*_change` 方法：

```python
# 删除：_on_arc_change / _on_vac_interlock_change / _on_interlock2_change / _on_di4_change

def _make_fault_callback(self, fault_name):
    """为指定故障类型创建回调函数"""
    def _callback(pvname=None, value=None, **kwargs):
        logger.debug(f"{fault_name} PV变化: {pvname}={value}")
        if value == 0:
            threading.Thread(
                target=self._handle_fault, args=(fault_name,), daemon=True
            ).start()
    _callback.__name__ = f'_on_{fault_name.lower()}_change'  # 保留可调试性
    return _callback
```

`__init__` 中的注册改为：

```python
self.pv_arc.add_callback(self._make_fault_callback('Arc'))
self.pv_vac_interlock.add_callback(self._make_fault_callback('VacInterlock'))
self.pv_interlock2.add_callback(self._make_fault_callback('Interlock2'))
self.pv_di4.add_callback(self._make_fault_callback('DI4'))
```

> `cleanup()` 使用 `clear_callbacks()` 按 PV 对象清理，不依赖方法名，安全。

---

### Phase 4 — magic sleep 数字 → 命名常量

在各文件 import 后、class 定义前添加模块级常量，替换 `time.sleep(N)` 字面量：

**`rfq/controllers/fault.py`**
```python
_VAC_RESET_HOLD_S        = 4.0  # VacReset 高电平保持时间
_VAC_RESET_SETTLE_S      = 2.0  # VacReset 释放后等待时间
_INTERLOCK_RESET_HOLD_S  = 1.0  # 复位 PV 高电平保持时间
_INTERLOCK_RESET_SETTLE_S = 1.0 # 复位后等待下一步时间
```

**`rfq/controllers/power.py`**
```python
_DRIVE_RESPONSE_S = 2.0  # 等待 RF 驱动响应设定值变化
```

**`rfq/controllers/pulse.py`**
```python
_DRIVE_RAMP_STEP_S = 1.0  # 每步 Drive 缓降等待时间
_PULSE_SETTLE_S    = 2.0  # 脉宽变化后稳定等待时间
```

**`rfq/core/rf_operator.py`**（新文件，Phase 5 创建时一并加入）
```python
_RF_ON_SETTLE_S      = 1.0  # RF 开启后硬件稳定时间
_DRIVE_SETTLE_S      = 1.0  # Drive 写入后响应时间
_SWEEP_SETTLE_S      = 0.5  # Sweep/Tracking 使能后稳定时间
_DRIVE_ZERO_SETTLE_S = 0.5  # Drive 清零后关 RF 前等待时间
```

---

### Phase 5 — 新建 `rfq/core/rf_operator.py`

> **前置条件：** Phase 0~4 完成并通过回归。

将以下方法从 `controller.py` 移入 `RFOperator` 类：

| `controller.py` 原方法 | `RFOperator` 新方法 |
|----------------------|-------------------|
| `_setup_rf_mode(self)` | `setup_mode(self, pulse_start)` |
| `_startup_rf(self)` | `startup(self)` |
| `_shutdown_rf(self)` | `shutdown(self)` |

**`RFOperator.__init__` 接收：** `config, pv_manager, fault_handler`

**先处理跨模块私有调用：**

在 `rfq/controllers/fault.py` 新增公共接口（保留兼容 shim）：
```python
def reset_interlock_faults(self):
    """公共故障复位接口，供 controller/rf_operator 调用"""
    self._reset_all_faults('Manual')

def _reset_interlock_faults(self):  # backward compatibility
    return self.reset_interlock_faults()
```

**持有的状态（从 controller 迁移过来）：**
- `self.is_pulse_mode = False`
- `self.current_drive_pv = None`
- `self.max_retries`、`self.retry_interval`、`self.retry_count`

**内部辅助（与 controller 一致）：**
```python
def _get(self, pv_key):
    return self.pv_manager.get(self.config.get_pv(pv_key))

def _put(self, pv_key, value):
    self.pv_manager.put(self.config.get_pv(pv_key), value)
```

**`controller.py` 相应修改：**
- `__init__` 新增：`self.rf_operator = RFOperator(config, self.pv_manager, self.fault_handler)`
- 删除：`self.is_pulse_mode`、`self.current_drive_pv`、`self.max_rf_startup_retries`、
  `self.retry_interval`、`self.rf_startup_retry_count`
- 属性引用替换：`self.is_pulse_mode` → `self.rf_operator.is_pulse_mode`，
  `self.current_drive_pv` → `self.rf_operator.current_drive_pv`
- `_handle_initializing()` 中三处调用：
  - `self._setup_rf_mode()` → `self.rf_operator.setup_mode(self.pulse_start)`
  - `self._startup_rf()` → `self.rf_operator.startup()`
  - `self._shutdown_rf()` → `self.rf_operator.shutdown()`（error/stopped handler 中）
- `RFOperator.startup()` 中复位调用统一走公共接口：
  - `self.fault_handler._reset_interlock_faults()` → `self.fault_handler.reset_interlock_faults()`

---

### Phase 6 — 新建 `rfq/core/handlers.py` Mixin

> **前置条件：** Phase 0~5 完成并通过回归。

将 `controller.py` 中的 9 个 `_handle_*` 方法全部移入 `StateHandlersMixin`：

```python
# rfq/core/handlers.py
import time
import logging
from .state import RFQState

logger = logging.getLogger('RFQ.Controller')  # 与 controller.py 使用同一 logger 名


class StateHandlersMixin:
    """
    RFQController 的状态处理函数 Mixin。
    本 Mixin 不独立使用，依赖 RFQController 的全部实例属性。
    关键依赖（至少）：config, pv_manager, fault_handler, vacuum_checker,
    power_controller, pulse_controller, state_handlers, terminal_states。
    """

    def _handle_idle(self): ...
    def _handle_initializing(self): ...
    def _handle_adjusting_power(self): ...
    def _handle_waiting_vacuum(self): ...
    def _handle_expanding_pulse(self): ...
    def _handle_paused(self): ...
    def _handle_completed(self): ...
    def _handle_error(self): ...
    def _handle_stopped(self): ...
```

**`controller.py` 修改：**
```python
from .handlers import StateHandlersMixin

class RFQController(StateHandlersMixin):
    ...
```

删除 `controller.py` 中的 9 个 `_handle_*` 方法。

**`controller.py` 最终只包含：**
`__init__`、`set_state`、`update_status`、`_get_pv`、`_put_pv`、
`_sleep`、`_sleep_loop`、`_check_reset_signal`、`_cleanup_terminal_state`、
`reset`、`_load_pv_with_fallback`、`_load_parameters`、`_check_common_conditions`、`run`

---

## 注意事项

| 依赖关系 | 风险 | 处理方式 |
|---------|------|---------|
| `reset()` 直接写 `fault_handler.fault_count/fault_exceeded` | 中 | 保持现状，加注释说明原子性需求 |
| `startup()` 调用 `fault_handler._reset_interlock_faults()`（私有） | 中 | 新增 `reset_interlock_faults()` 公共接口；私有方法保留为兼容 shim |
| `handlers.py` 隐式依赖 `RFQController` 全部属性 | 中 | Mixin docstring 明确列出关键依赖；类定义旁补充依赖清单注释 |
| `config.loop['wait_before_expand']` 与 yaml 中 `wait_after_expand` 命名不一致 | 中 | 本次一并修复为 `wait_after_expand`；如需兼容旧配置可做双 key fallback |

---

## 验证方法

### 每个 Phase 完成后（最小检查）

```bash
python -c "from rfq import RFQController; print('import ok')"
python -m py_compile rfq/core/controller.py rfq/controllers/fault.py rfq/utils/pv_manager.py
```

### Phase 5/6 前置回归门槛

必须先通过以下 4 项，再进入大规模拆分：

1. 正常流程：`IDLE → INITIALIZING → ADJUSTING_POWER/EXPANDING_PULSE ... → COMPLETED`
2. arc 故障：触发后能自动复位并回到可继续老练状态（故障计数累加逻辑不变）
3. VacInterlock 故障：复位顺序与结果不变
4. 暂停/恢复：`start=0` 进入 `PAUSED`，`start=1` 按原逻辑恢复

### 全部完成后的验收（行为不变）

用 `tests/sim_ioc.py` 启动模拟 IOC，至少执行以下回归矩阵并与 Phase 0 基线对比：

1. 正常路径：状态序列与最终状态一致（COMPLETED）
2. 故障路径：arc / VacInterlock 两条路径的恢复结果一致
3. 边界路径：`max_faults` 超限后进入 ERROR 的判定一致
4. 关键 PV 写入：`rf_on`、`pulse_time`、`current_target_power`、`status` 的写入时机一致

> 允许差异：日志时间戳、线程调度导致的同秒级日志顺序轻微波动。  
> 不允许差异：状态转换结果、故障计数语义、故障恢复是否成功。

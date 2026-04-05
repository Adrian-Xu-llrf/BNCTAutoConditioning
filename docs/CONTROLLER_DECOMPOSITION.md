# 控制器拆分文档

改进日期: 2026-04-05
对应审查项: CODE_REVIEW.md 模块二 (#1, #8, #13)

---

## 改进概览

| 编号 | 问题 | 改进内容 | 涉及文件 |
|------|------|----------|----------|
| #1 | RFQController 上帝类（889行） | 提取 RFManager、ParameterLoader | 新增 `rf_manager.py`、`params.py` |
| #8 | 20+ 实例属性散落 | ConditioningParams 数据类 | 新增 `params.py` |
| #13 | _check_common_conditions 职责过重 | 拆分为 3 个独立检查方法 | `controller.py` |

---

## 架构对比

### 改进前

```
RFQController (889行, 20+属性)
    ├── _startup_rf()          # RF启停逻辑
    ├── _shutdown_rf()
    ├── _setup_rf_mode()
    ├── _load_parameters()     # 参数加载逻辑
    ├── reset()                # 复位逻辑（做两件不同的事）
    ├── _check_common_conditions()  # 同时检查5种条件
    ├── target_power           # 散落的运行参数
    ├── init_drive
    ├── pulse_start / pulse_end / pulse_step
    ├── wait_time / wait_before_expand
    ├── power_targets / target_index
    └── 各种状态处理方法
```

### 改进后

```
RFQController (状态机调度，约300行核心逻辑)
    ├── RFManager (rf_manager.py)        ← RF启停管理
    │     ├── startup(init_drive)
    │     ├── shutdown()
    │     └── setup_mode(pulse_start)
    ├── ParameterLoader (params.py)      ← 参数加载
    │     └── load(params, is_auto_recovery)
    ├── ConditioningParams (params.py)   ← 运行参数数据类
    │     ├── target_power / init_drive
    │     ├── pulse_start / pulse_end / pulse_step
    │     ├── power_targets / target_index
    │     └── wait_time / wait_before_expand
    ├── reset()
    │     ├── _reset_manual()           ← 手动复位
    │     └── _reset_auto_recovery()    ← 自动恢复
    ├── _check_common_conditions()
    │     ├── _check_pause_signal()     ← 暂停信号检查
    │     ├── _check_rf_status()        ← RF在线检查
    │     └── _check_limits()           ← 计数限制检查
    └── 各种状态处理方法
```

---

## #1 — RFManager 提取

### 新文件: `rfq/core/rf_manager.py`

将 RF 启停和模式配置逻辑从 RFQController 中提取为独立的 `RFManager` 类。

**RFManager 职责**:
- 识别并配置 RF 模式（脉冲/连续波）
- RF 启动（含重试逻辑）
- RF 关闭

```python
class RFManager:
    def __init__(self, pv_manager, fault_handler, sleep_func=None):
        self.pv_manager = pv_manager
        self.fault_handler = fault_handler
        self.is_pulse_mode = False
        self.current_drive_pv = None

    def configure_startup(self, max_retries, retry_interval):
        """配置启动重试参数"""

    def setup_mode(self, pulse_start) -> bool:
        """识别RF模式（脉冲/CW），配置Drive PV"""

    def startup(self, init_drive) -> bool:
        """启动RF（含故障复位重试）"""

    def shutdown(self):
        """关闭RF（不操作sweep/tracking）"""
```

**控制器中的使用**:
```python
# 旧: self._startup_rf()  /  self._shutdown_rf()  /  self._setup_rf_mode()
# 新:
self.rf_manager.startup(self.params.init_drive)
self.rf_manager.shutdown()
self.rf_manager.setup_mode(self.params.pulse_start)

# 旧: self.is_pulse_mode / self.current_drive_pv
# 新:
self.rf_manager.is_pulse_mode
self.rf_manager.current_drive_pv
```

---

## #8 — ConditioningParams 数据类

### 新文件: `rfq/core/params.py`

将散落在 `RFQController.__init__` 中的 20+ 个运行参数整合为 `ConditioningParams` 数据类。

```python
@dataclass
class ConditioningParams:
    # 功率参数
    target_power: float = 0.0
    init_drive: float = 0.0
    power_targets: List[float] = field(default_factory=list)
    target_index: int = 0

    # 脉冲参数
    pulse_start: float = 1.0
    pulse_end: float = 500.0
    pulse_step: float = 0.5
    original_pulse_start: Optional[float] = None

    # 等待时间
    wait_time: float = 1.0
    wait_before_expand: float = 10.0
```

**控制器中的使用**:
```python
# 旧: self.target_power  /  self.pulse_start  /  self.power_targets  ...
# 新:
self.params.target_power
self.params.pulse_start
self.params.power_targets
```

**ParameterLoader** 封装了从 PV 读取参数到 `ConditioningParams` 的完整流程：

```python
class ParameterLoader:
    def load(self, params, is_auto_recovery=False) -> bool:
        """从PV加载参数到ConditioningParams"""
```

---

## #13 — _check_common_conditions 拆分

### 拆分方案

原来的 `_check_common_conditions()` 方法（约60行）同时处理5种条件检查，现在拆分为3个独立方法：

```python
def _check_pause_signal(self):
    """检查用户暂停/停止信号 (start=0)"""

def _check_rf_status(self):
    """检查RF在线状态（仅在 states_need_rf 中检查）"""

def _check_limits(self):
    """检查故障和迭代次数限制"""

def _check_common_conditions(self):
    """组合检查：暂停 → RF状态 → 计数限制"""
    return (self._check_pause_signal()
            or self._check_rf_status()
            or self._check_limits())
```

**优势**:
- 每个方法职责单一，可独立测试
- 便于调整检查顺序或跳过某些检查
- 新增检查条件时只需修改 `_check_common_conditions` 的组合

---

## reset() 方法拆分

将 `reset()` 中 `clear_faults=True/False` 的两个分支拆分为两个独立的内部方法：

```python
def reset(self, clear_faults=True):
    """公共接口不变"""
    # ... 公共清理逻辑 ...
    if clear_faults:
        self._reset_manual()
    else:
        self._reset_auto_recovery()
    self.set_state(RFQState.IDLE)

def _reset_manual(self):
    """手动复位：清零故障计数，回到第一个功率目标，恢复初始脉宽"""

def _reset_auto_recovery(self):
    """自动恢复：保留故障计数和功率目标，脉宽下降 pulse_drop"""
```

---

## 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `rfq/core/rf_manager.py` | 新增 | RF启停管理器 |
| `rfq/core/params.py` | 新增 | ConditioningParams 数据类 + ParameterLoader |
| `rfq/core/controller.py` | 修改 | 使用新组件，拆分 reset/check 方法 |
| `rfq/core/__init__.py` | 修改 | 导出新类 |

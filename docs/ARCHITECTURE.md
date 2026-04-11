# 系统架构文档

面向开发者的技术参考，描述各模块职责、核心设计决策和数据流。

---

## 一、模块职责

| 文件 | 职责 | 不做什么 |
|------|------|---------|
| `main.py` | 日志初始化、配置加载、启动 controller | 不含业务逻辑 |
| `core/controller.py` | 状态机调度：驱动主循环、状态转换、通用条件检查、重置 | 不直接读写 EPICS PV（通过 `pv_manager`） |
| `core/state.py` | 状态枚举定义、合法转换表 `LEGAL_TRANSITIONS` | 不含任何运行逻辑 |
| `core/config.py` | 加载 `config.yaml`，支持运行时热更新 | 不校验配置合法性 |
| `core/params.py` | `ConditioningParams` 数据类（运行参数）+ `ParameterLoader`（从 PV 加载） | 不持久化参数 |
| `core/rf_manager.py` | RF 启动（含重试）、关闭、模式识别（脉冲/CW） | 不监控 RF 状态（由 controller 检查 `rf_on`） |
| `core/pv_keys.py` | PV 逻辑键字符串常量集中定义 | — |
| `controllers/power.py` | 单次功率调节动作（大步/小步 Drive 调整） | 不管调节频率（由 controller 的 `_sleep_loop` 控制） |
| `controllers/pulse.py` | 单次脉宽展宽动作（含可选的降功率前处理） | 不管展宽时序（由 controller 控制） |
| `controllers/vacuum.py` | 注册真空 PV callback，缓存最差真空值，提供线程安全的查询接口 | 不触发状态转换 |
| `controllers/fault.py` | 注册故障 PV callback，滑动窗口计数，提供复位操作 | 不触发状态转换（状态转换由 controller 根据计数决定） |
| `utils/pv_manager.py` | PV 长连接管理（注册、读、写、连接检查） | 不缓存 PV 值（值由 `epics.PV` 对象管理） |

---

## 二、状态机设计

### 2.1 状态转换合法性

`state.py` 中的 `LEGAL_TRANSITIONS` 定义每个状态允许跳转到哪些目标状态。`controller.set_state()` 在执行转换前校验合法性，非法跳转抛出 `StateTransitionError`。

设计意图：在开发阶段尽早暴露逻辑错误（如忘记处理某个边界条件导致状态乱跳），而不是让程序在不一致状态下继续运行。

### 2.2 通用条件检查链路

每个活动状态的 `_handle_xxx()` 方法开头都调用 `_check_common_conditions()`，执行顺序固定：

```
_check_pause_signal()     # 1. 用户暂停/停止信号
    ↓ (None时继续)
_check_vacuum_status()    # 2. 真空联锁
    ↓ (None时继续)
_check_rf_status()        # 3. RF在线状态
    ↓ (None时继续)
_check_limits()           # 4. 故障次数/迭代次数超限
```

**顺序设计原因**：
- 用户信号优先级最高，确保操作员能随时介入
- 真空联锁在 RF 检查之前：真空超标时 RF 往往已经自动关闭，先处理真空可以避免触发 RF 恢复流程
- 计数检查放最后：属于软件层面的保护，优先级低于硬件联锁

### 2.3 主循环结构

`run()` 是单一 `while True` 循环，每次迭代：
1. 从 `state_handlers` 字典取出当前状态对应的 `_handle_xxx()` 方法
2. 调用该方法（方法内部负责 sleep）
3. 方法内部调用 `set_state()` 触发状态转换

终止状态（`ERROR`/`STOPPED`/`COMPLETED`）的 `_handle_xxx()` 内部处理 reset 信号检查和等待，不需要外层特殊处理。

---

## 三、关键设计决策

### 3.1 callback 驱动 vs 轮询（vacuum / fault）

`VacuumChecker` 和 `FaultHandler` 使用 EPICS CA callback 而非在主循环中轮询读取 PV。

**原因**：
- 故障 PV 变化是**事件性**的（0→1→0），轮询间隔（0.5s）可能错过短暂的故障脉冲
- callback 在 CA 线程中立即响应，计时精度高于主循环间隔
- 主循环只需查询缓存结果（`is_vacuum_ok()`、`get_fault_count()`），不阻塞

**代价**：引入多线程访问，需要用 `threading.Lock` 保护共享数据（见 3.4）。

### 3.2 自动恢复 vs 手动复位

`reset()` 有两种模式，通过 `clear_faults` 参数区分：

| | 自动恢复（`clear_faults=False`） | 手动复位（`clear_faults=True`） |
|--|--------------------------------|-------------------------------|
| **触发** | RF 掉线，故障未超限，由 `_check_rf_status()` 调用 | 操作员写 `AutoC_Reset=1` |
| **故障计数** | 保留（累计计数） | 清零 |
| **功率目标** | 保留当前目标索引 | 回到第一个目标 |
| **脉宽** | 下降 `pulse_drop` ms（保护性回退） | 从 PV 重新读取初始值 |
| **`start` PV** | 不清零（保持为1，以便重启） | 清零 |

自动恢复路径：RF 掉线 → 复位故障 → `reset(clear_faults=False)` → IDLE → start=1 → INITIALIZING（`_is_auto_recovery=True`，跳过脉宽重载）。

### 3.3 跨状态协调标志

以下布尔标志用于在状态转换时传递上下文，生命周期需要特别关注：

| 标志 | 含义 | 置 True | 清 False |
|------|------|---------|---------|
| `_wait_before_power` | 展脉宽完成后，进入 ADJUSTING_POWER 前需等待 | `EXPANDING_PULSE` 切到下一目标时 | 等待时间到达后，或手动复位 |
| `_need_reset_pulse` | 等待结束后需要恢复脉宽到初始值 | 与 `_wait_before_power` 同步置 True | 脉宽恢复后，或手动复位 |
| `_is_auto_recovery` | 本次 INITIALIZING 是自动恢复，跳过脉宽重载 | `_reset_auto_recovery()` 时 | INITIALIZING 成功完成后 |

注意：自动恢复时 `_wait_before_power` 和 `_need_reset_pulse` **不清零**，避免跳过已经设置的展脉宽保护等待。

### 3.4 config 热更新

`config.reload_if_changed()` 在两处被调用：
- `_handle_initializing()`：每次启动前检查配置是否更新
- `_handle_paused()`：恢复运行前检查配置是否更新

这意味着操作员可以在系统运行中修改 `config.yaml`，在下次启动或从暂停恢复时生效，无需重启程序。

---

## 四、数据流

### 4.1 参数加载

```
操作员写入 EPICS PV
    ↓
INITIALIZING 阶段调用 ParameterLoader.load(params)
    ↓
从 PV 读取所有运行参数 → 填入 ConditioningParams 实例
    ↓
controller 持有 self.params，各 _handle_xxx 方法从中读取
```

`ConditioningParams` 是一个简单的 `dataclass`，字段在运行中会被修改（如 `target_index` 递增、`pulse_start` 更新）。

### 4.2 状态写回 EPICS

状态转换发生时，`set_state()` 调用 `update_status(new_state.name)`，将状态名写入 `control.status` PV（`AutoC_Status`），字节数截断至 40 字节以兼容 EPICS 字符串 PV。

此外各 `_handle_xxx` 方法会在关键节点更新 `control.current_target_power`（`AutoC_CurrentTargetPower`）和 `control.current_pulse`（`AutoC_CurrentPulse`），供操作员监控进度。

---

## 五、线程安全

程序运行时存在两类线程：

| 线程 | 内容 |
|------|------|
| 主线程 | `run()` 主循环，所有状态处理逻辑 |
| EPICS CA 线程 | `VacuumChecker._on_vacuum_change()` 和 `FaultHandler._make_callback()` 中的 callback |

**共享数据保护**：
- `VacuumChecker`：`vacuum_values`、`worst_vacuum`、`vacuum_ok` 由 `self.lock`（`threading.Lock`）保护
- `FaultHandler`：`fault_timestamps`、`fault_exceeded`、`last_fault_type` 由 `self.lock` 保护

主线程通过 `is_vacuum_ok()` / `get_fault_count()` 等方法访问，方法内部持锁，对主线程透明。

**注意**：`_cleanup_terminal_state()` 调用 `cleanup()` 清除 callback 后，若系统 reset 重新运行，callback 不会自动重新注册（已记录为已知 bug，见 `PROJECT_OPTIMIZATION_PLAN.md` 三.1）。

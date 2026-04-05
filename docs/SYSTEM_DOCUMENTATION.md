# RFQ 自动老练系统 — 详细技术说明文档

版本: 3.0.0
作者: Chengye Xu
日期: 2026-04

---

## 目录

1. [系统概述](#1-系统概述)
2. [工程结构](#2-工程结构)
3. [启动流程](#3-启动流程)
4. [EPICS PV 通信层](#4-epics-pv-通信层)
5. [配置系统](#5-配置系统)
6. [状态机核心](#6-状态机核心)
7. [RF 管理器](#7-rf-管理器)
8. [参数加载器](#8-参数加载器)
9. [功率控制器](#9-功率控制器)
10. [脉冲控制器](#10-脉冲控制器)
11. [故障处理器](#11-故障处理器)
12. [真空检测器](#12-真空检测器)
13. [完整老练流程](#13-完整老练流程)
14. [多目标功率模式](#14-多目标功率模式)
15. [故障恢复机制](#15-故障恢复机制)
16. [PV 键映射总表](#16-pv-键映射总表)

---

## 1. 系统概述

RFQ（Radio Frequency Quadrupole）自动老练系统用于控制粒子加速器中 RFQ 腔体的 RF 老练过程。老练的本质是**逐步提升 RF 功率并扩展脉冲宽度**，使腔体在高功率下稳定运行而不产生打火（ARC）、真空恶化等故障。

系统通过 EPICS（Experimental Physics and Industrial Control System）PV（Process Variable）与硬件通信，实现：

- **RF 功率自动调节**：通过调整 Drive 值逐步逼近目标功率
- **脉冲宽度自动扩展**：在保持功率稳定的前提下逐步增大脉宽
- **故障自动检测与恢复**：ARC 打火、真空联锁等故障的自动处理
- **真空联锁保护**：实时监测 8 路真空计，超阈值时暂停老练
- **多目标功率支持**：支持按功率阶梯列表依次完成多个功率目标

### 系统运行模式

- **脉冲模式**（`pulse_cw=1`）：RF 以脉冲方式输出，需要展宽脉宽，这是主要的老练模式
- **连续波模式**（`pulse_cw≠1`）：RF 以连续波输出，功率达标即完成

---

## 2. 工程结构

```
AutoConditioning/
├── main.py                         # 程序入口
├── config.yaml                     # 配置文件（PV名称、阈值、重试参数）
├── requirements.txt                # 依赖声明
│
├── rfq/                            # 主 Python 包
│   ├── __init__.py                 # 包入口，版本号，公共 API 导出
│   │
│   ├── core/                       # 核心模块
│   │   ├── __init__.py             # 核心模块导出
│   │   ├── state.py                # RFQState 枚举 + 状态转换表
│   │   ├── config.py               # Config 配置加载器
│   │   ├── pv_keys.py              # PV 逻辑键常量定义
│   │   ├── params.py               # ConditioningParams 数据类 + ParameterLoader
│   │   ├── rf_manager.py           # RFManager RF 启停管理
│   │   └── controller.py           # RFQController 状态机主控制器
│   │
│   ├── controllers/                # 子控制器
│   │   ├── __init__.py
│   │   ├── power.py                # PowerController 功率调节
│   │   ├── pulse.py                # PulseController 脉冲扩展
│   │   ├── fault.py                # FaultHandler 故障检测与复位
│   │   └── vacuum.py               # VacuumChecker 真空监测
│   │
│   └── utils/                      # 工具
│       ├── __init__.py
│       └── pv_manager.py           # PVManager 单例 EPICS PV 管理器
│
└── docs/                           # 文档
```

### 模块依赖关系

```
main.py
  └── RFQController (core/controller.py)
        ├── Config (core/config.py) ──── config.yaml
        ├── PVManager (utils/pv_manager.py) ──── EPICS
        ├── RFManager (core/rf_manager.py)
        │     └── FaultHandler (controllers/fault.py)
        ├── ParameterLoader (core/params.py)
        │     └── ConditioningParams
        ├── PowerController (controllers/power.py)
        ├── PulseController (controllers/pulse.py)
        ├── FaultHandler (controllers/fault.py)
        └── VacuumChecker (controllers/vacuum.py)
```

---

## 3. 启动流程

### 3.1 程序入口 (`main.py`)

程序启动经过以下步骤：

```
1. get_config('config.yaml')          # 加载 YAML 配置
2. setup_logging(config)              # 配置日志（文件 + 控制台）
3. print_welcome(config)              # 打印欢迎信息
4. input("按Enter键开始运行...")       # 等待用户确认
5. controller = RFQController(config) # 创建控制器
6. controller.run()                   # 进入状态机主循环
```

### 3.2 RFQController 初始化 (`controller.py`)

`__init__` 方法完成以下工作：

**第一步 — 建立 EPICS 通信**

```python
PVManager.reset_instance()                    # 清除旧单例
self.pv_manager = PVManager(config)            # 创建 PVManager 单例
self._register_all_pvs()                       # 批量注册 30+ 个 PV
```

`_register_all_pvs()` 从 `config.yaml` 的 `pv` 节读取 PV 名称，按四组注册：
- `rf.*` — RF 控制 PV（rf_on, pulse_drive, cw_drive 等）
- `fault.*` — 故障检测 PV（arc, VacInterlock 等）
- `control.*` — 老练控制 PV（start, reset, power_targets 等）
- `vacuum.*` — 真空 PV（Vac1-Vac8，列表形式，编号 0-7）

**第二步 — 创建子控制器**

```python
self.fault_handler = FaultHandler(config, self.pv_manager)    # 注册故障回调
self.vacuum_checker = VacuumChecker(config, self.pv_manager)  # 注册真空回调
self.power_controller = PowerController(config, self.pv_manager)
self.pulse_controller = PulseController(config, self.pv_manager)
```

注意：`FaultHandler` 和 `VacuumChecker` 在构造时就会向 PV 注册 EPICS 回调函数，开始异步监听硬件状态变化。

**第三步 — 创建 RF 管理器和参数加载器**

```python
self.rf_manager = RFManager(self.pv_manager, self.fault_handler)
self.params = ConditioningParams()
self.param_loader = ParameterLoader(self.pv_manager, self.config)
```

**第四步 — 初始化状态机**

```python
self.current_state = RFQState.IDLE    # 初始状态
# 状态处理函数映射表
self.state_handlers = {
    RFQState.IDLE: self._handle_idle,
    RFQState.INITIALIZING: self._handle_initializing,
    # ... 9 个状态对应 9 个处理函数
}
```

---

## 4. EPICS PV 通信层

### 4.1 PVManager 单例 (`pv_manager.py`)

`PVManager` 是整个系统与 EPICS 通信的唯一通道，采用单例模式，通过 `threading.Lock` 保证线程安全。

**核心设计**：

```
EPICS PV 名称（硬件地址）
    "RFQ:LLRF:Con01:Opr_RFOn"     ←── 实际的 EPICS PV 名称
           ↕
    逻辑键（代码中使用）
    "rf.rf_on"                     ←── 代码中引用的简短名称
           ↕
    epics.PV 对象（长连接）
    pv.get() / pv.put()            ←── 底层通信
```

**注册过程**：

```python
# config.yaml 中定义：
rf:
  rf_on: 'RFQ:LLRF:Con01:Opr_RFOn'

# 代码中注册：
pv_manager.register('rf.rf_on', 'RFQ:LLRF:Con01:Opr_RFOn')

# 之后用逻辑键读写：
pv_manager.put('rf.rf_on', 1)        # 打开 RF
value = pv_manager.get('rf.rf_on')   # 读取 RF 状态
```

**关键方法**：

| 方法 | 功能 |
|------|------|
| `register(key, name)` | 注册 PV，创建 `epics.PV` 长连接 |
| `register_group(dict, prefix)` | 批量注册一组 PV（加前缀） |
| `register_list(list, prefix)` | 批量注册列表 PV（加编号） |
| `get(key, timeout=3.0)` | 读取 PV 值，超时返回 None |
| `put(key, value)` | 写入 PV 值 |
| `get_pv_object(key)` | 获取底层 `epics.PV` 对象（用于回调） |
| `check_all_connected()` | 检查所有 PV 是否在线 |
| `safe_status(text, max_bytes=40)` | 截断字符串到 40 字节（EPICS PV 字符串限制） |

**线程安全**：`__new__` 和 `reset_instance()` 都通过 `threading.Lock` 保护，防止 EPICS 回调线程与主线程的竞态条件。

---

## 5. 配置系统

### 5.1 Config 类 (`config.py`)

从 YAML 文件加载配置，提供多种访问方式：

```python
config = Config('config.yaml')

# 多层键路径访问
config.get('loop', 'rf_startup', 'max_retry')    # → 5

# PV 名称查找
config.get_pv('rf.on')                            # → 'RFQ:LLRF:Con01:Opr_RFOn'

# 快捷属性
config.vacuum     # → {'threshold': 5.0e-5}
config.loop       # → {'interval': 0.5, 'max_faults': 20, ...}
config.pv         # → {'rf': {...}, 'fault': {...}, ...}
```

**热更新机制**：

```python
config.reload_if_changed()   # 仅当文件修改时间变化时才重新读取磁盘
config.reload()               # 强制重新读取
```

### 5.2 config.yaml 结构

```yaml
vacuum:
  threshold: 5.0e-5        # 真空保护阈值 (Pa)

loop:
  interval: 0.5            # 主循环间隔 (秒)
  max_faults: 20           # 最大故障次数（超限进入 ERROR）
  max_iterations: 1000     # 最大迭代次数（超限进入 ERROR）
  reduce_power_before_expand: false  # 展脉宽前是否先降功率
  rf_startup:
    max_retry: 5           # RF 启动最大重试次数
    retry_interval: 2      # 重试间隔 (秒)

pv:
  rf: {...}                # RF 控制 PV 名称
  fault: {...}             # 故障 PV 名称
  vacuum: [...]            # 真空 PV 名称列表
  control: {...}           # 老练控制 PV 名称

logging:
  level: 'INFO'
  file: 'rfq_auto_conditioning.log'
```

### 5.3 PVKeys 常量 (`pv_keys.py`)

集中定义所有 PV 逻辑键的字符串常量，防止拼写错误：

```python
class PVKeys:
    RF_ON = 'rf.rf_on'
    CONTROL_START = 'control.start'
    # ... 共 33 个常量
```

### 5.4 ConditioningParams 数据类 (`params.py`)

将所有运行参数整合到一个 `@dataclass` 中：

```python
@dataclass
class ConditioningParams:
    target_power: float = 0.0           # 当前目标功率 (kW)
    init_drive: float = 0.0             # 初始 Drive 值
    power_targets: List[float] = []     # 多目标功率列表
    target_index: int = 0               # 当前目标索引
    pulse_start: float = 1.0            # 当前脉宽起始值 (ms)
    pulse_end: float = 500.0            # 目标脉宽 (ms)
    pulse_step: float = 0.5             # 脉宽步长 (ms)
    original_pulse_start: float = None  # 原始初始脉宽（不可低于此值）
    wait_time: float = 1.0              # 每次展脉宽前等待时间 (s)
    wait_before_expand: float = 10.0    # 切换目标后等待时间 (s)
```

---

## 6. 状态机核心

### 6.1 状态定义 (`state.py`)

系统有 9 个状态，分为三类：

**正常运行状态（0-99）**：

| 状态 | 编号 | 含义 |
|------|------|------|
| `IDLE` | 0 | 空闲，等待用户按 Start |
| `INITIALIZING` | 10 | 初始化：加载参数、配置 RF 模式、启动 RF |
| `PAUSED` | 15 | 暂停，等待用户恢复 |
| `ADJUSTING_POWER` | 20 | 调节功率：通过 Drive 逼近目标功率 |
| `WAITING_VACUUM` | 25 | 等待真空恢复到安全值以下 |
| `EXPANDING_PULSE` | 30 | 展宽脉冲：逐步增大脉冲宽度 |
| `COMPLETED` | 90 | 老练完成 |

**异常状态（100+）**：

| 状态 | 编号 | 含义 |
|------|------|------|
| `ERROR` | 100 | 错误（故障超限等） |
| `STOPPED` | 101 | 用户停止 |

### 6.2 状态转换规则

每个状态只能跳转到预定义的合法目标状态。`LEGAL_TRANSITIONS` 定义了完整的转换表：

```
IDLE ──────────────────→ INITIALIZING     （用户按 Start）
INITIALIZING ──────────→ ADJUSTING_POWER  （初始化成功）
ADJUSTING_POWER ───────→ EXPANDING_PULSE  （功率达标，脉冲模式）
ADJUSTING_POWER ───────→ COMPLETED        （功率达标，CW 模式）
EXPANDING_PULSE ───────→ ADJUSTING_POWER  （下一功率目标 / 功率偏离）
EXPANDING_PULSE ───────→ COMPLETED        （所有目标完成）
任意活动状态 ──────────→ PAUSED           （start=0）
任意状态 ──────────────→ ERROR / STOPPED  （故障/用户操作）
ERROR / STOPPED / COMPLETED → IDLE        （用户按 Reset）
```

`set_state()` 方法在每次状态转换时校验合法性，非法转换抛出 `StateTransitionError`。

### 6.3 主循环结构

```python
def run(self):
    while True:
        # 内层循环：运行活动状态
        while current_state not in terminal_states:
            handler = state_handlers[current_state]
            handler()

        # 执行终止状态的最后一次清理
        handler()

        # 外层循环：等待 reset 信号
        while current_state in terminal_states:
            sleep(1)
            if reset_signal == 1:
                reset()
```

**双层循环的语义**：
- **内层循环**：状态机在活动状态间转换，到达终止状态（COMPLETED/ERROR/STOPPED）时退出
- **外层循环**：到达终止状态后，持续监听 reset 信号，收到后重置到 IDLE，重新进入内层循环

这样系统可以**长期运行**，完成一次老练后等待 reset，支持多次运行而不需要重启程序。

### 6.4 通用条件检查

每个活动状态的 handler 开头都调用 `_check_common_conditions()`，它按优先级依次检查三类条件：

```
_check_pause_signal()    → start=0 时暂停或停止
    ↓（通过）
_check_rf_status()       → RF 掉线时自动恢复或进入 ERROR
    ↓（通过）
_check_limits()          → 故障次数 / 迭代次数超限时进入 ERROR
    ↓（全部通过）
    返回 None → 继续当前状态的正常逻辑
```

---

## 7. RF 管理器

### 7.1 RFManager (`rf_manager.py`)

封装 RF 系统的启停和模式配置，从主控制器中独立出来。

**模式配置 `setup_mode(pulse_start)`**：

```
读取 rf.pulse_cw PV
  ├─ =1 → 脉冲模式
  │     is_pulse_mode = True
  │     current_drive_pv = 'rf.pulse_drive'
  │     设置 rf.cw_drive = 0
  │     设置 rf.pulse_time = pulse_start/1000 (s)
  │
  └─ ≠1 → 连续波模式
        is_pulse_mode = False
        current_drive_pv = 'rf.cw_drive'
        设置 rf.pulse_drive = 0
```

**RF 启动 `startup(init_drive)`**：

```
for attempt in 1..max_retries:
    1. 写 rf.rf_on = 1           → 打开 RF
    2. 写 Drive = init_drive     → 设置初始 Drive
    3. 写 rf.sweep = 1           → 打开频率扫描
       写 rf.tracking = 1        → 打开频率跟踪
    4. 读 rf.rf_on 验证          → 确认 RF 真的打开了

    if rf_on == 1:
        return True              → 启动成功

    # 失败：可能是 ARC 故障导致自动保护
    fault_handler.reset_all_faults()  → 复位所有故障
    sleep(retry_interval)             → 等待后重试

return False  → 所有重试都失败
```

**RF 关闭 `shutdown()`**：

```
1. 写 Drive = 0       → 先将 Drive 降为零
2. 写 rf.rf_on = 0    → 关闭 RF
注意：不操作 sweep 和 tracking
```

---

## 8. 参数加载器

### 8.1 ParameterLoader (`params.py`)

从 EPICS PV 读取运行参数到 `ConditioningParams` 数据类。

**`load(params, is_auto_recovery)` 流程**：

```
1. 读 control.power_targets (waveform PV) → params.power_targets
   过滤掉零值，空列表则报错

2. 根据 target_index 取当前目标 → params.target_power
   写入 control.current_target_power PV

3. 读 control.init_drive → params.init_drive

4. 读脉冲参数：
   - 自动恢复模式：保留当前 pulse_start，不从 PV 重读
   - 正常模式：读 control.pulse_start → params.pulse_start
   - 读 control.pulse_end → params.pulse_end
   - 读 control.pulse_step → params.pulse_step（失败时用 config 默认值 0.5ms）

5. 首次加载时保存 params.original_pulse_start（后续不覆盖）

6. 读等待时间：
   - control.pulse_wait → params.wait_time
   - control.wait_before_expand（分钟→秒）→ params.wait_before_expand
```

所有参数读取都有容错机制：PV 读取失败时回退到 `config.yaml` 中的默认值。

---

## 9. 功率控制器

### 9.1 PowerController (`power.py`)

通过调整 Drive 值使 RF 输出功率逼近目标值。采用**双步长策略**：

```
计算功率误差 = |当前功率 - 目标功率|

if 误差 < margin_small:
    → 功率达标，返回 True

elif 误差 ≥ margin_large:
    → 大步调节（drive_step1），快速接近目标

else:  # margin_small ≤ 误差 < margin_large
    → 小步调节（drive_step2），精细逼近

 Drive 调节方向：
    功率偏低 (误差<0) → 增加 Drive
    功率偏高 (误差>0) → 减少 Drive
```

**每次调节后**：
- 等待 2 秒（可注入替换）
- 迭代计数 +1
- 返回 `(False, 调节信息)` 表示未达标

**迭代计数器**：累计 Drive 调节次数，超过 `max_iterations` 时由主控制器判定超限。

---

## 10. 脉冲控制器

### 10.1 PulseController (`pulse.py`)

每次调用 `expand()` 将脉宽增加一个步长 `pulse_step` ms。

**核心流程**：

```
1. 读当前脉宽 rf.pulse_time (s → ms)
   if 已达目标 pulse_end:
       return (True, "脉宽已达目标")

2. 计算新脉宽: current_ms + pulse_step（不超过 pulse_end）

3. 可选：降功率模式（reduce_power_before_expand=True）
   if 需要降功率:
       缓慢降低 Drive 到 init_drive（每步等1秒）
       支持 should_stop 回调中断
       有最大迭代次数保护

4. 写 rf.pulse_time = 新脉宽/1000
5. 等待 2 秒
6. return (False, "展脉宽: X→Yms")
```

**降功率模式详解**：

当 `reduce_power_before_expand=True` 时，展脉宽前先将 Drive 缓慢降到 `init_drive`，然后再展脉宽。这是为了在展脉宽过程中避免功率突变导致打火。降功率过程中：
- 每步检查 `should_stop()` 回调，用户可随时中断
- 有 `max_iterations` 上限防止无限循环
- 降完后恢复到 `init_drive`

---

## 11. 故障处理器

### 11.1 FaultHandler (`fault.py`)

采用**事件驱动**模式：通过 EPICS PV 回调自动检测故障，不需要主循环轮询。

**故障检测（4 个 PV）**：

| PV 逻辑键 | 硬件名称 | 含义 |
|-----------|---------|------|
| `fault.arc` | ArcStatus_Rd | ARC 打火检测 |
| `fault.VacInterlock` | InterlockStatus_Rd | 真空联锁 |
| `fault.interlock2` | InterlockStatus2_Rd | 联锁 2 |
| `fault.di4` | di4 | 数字输入 4 |

**PV 值语义**：`0 = 故障`，`1 = 正常`

**回调机制**：

```python
def callback(value):
    if value == 0:               # 值变为 0 表示发生故障
        fault_count += 1
        last_fault_type = "Arc"  # 记录故障类型
        if fault_count >= max_faults:
            fault_exceeded = True  # 标记超限
```

回调在 EPICS 线程中执行，通过 `threading.Lock` 保护 `fault_count` 和 `fault_exceeded` 的读写。

**故障复位 `reset_all_faults()`**：

依次对 4 个复位 PV 执行脉冲复位（置 1 → 等待 → 置 0 → 等待）：

| 复位 PV | 高电平时间 | 回落等待 |
|---------|-----------|---------|
| VacReset | 2.0s | 2.0s |
| ResetInterlock | 1.0s | 1.0s |
| ResetPWFaultStat1 | 1.0s | 1.0s |
| ResetPWFaultStat2 | 1.0s | 1.0s |

总计一次完整复位需要约 10 秒。

---

## 12. 真空检测器

### 12.1 VacuumChecker (`vacuum.py`)

同样采用事件驱动模式，监听 8 路真空计。

**工作原理**：

```
8 路真空 PV (vacuum.0 ~ vacuum.7)
    ↓ EPICS 回调（任意 PV 值变化时触发）
_on_vacuum_change(value, pv_key)
    ↓ 更新 vacuum_values 字典
    ↓ 计算最差真空值（8 路中最大值）
    ↓ 与阈值比较
    ↓ 设置 vacuum_ok 标志
```

**判定逻辑**：

```
worst_vacuum = max(8路真空值)

if worst_vacuum >= threshold (5.0e-5 Pa):
    vacuum_ok = False   → 真空不达标
else:
    vacuum_ok = True    → 真空达标
```

**`is_vacuum_ok()` 返回三元组**：`(是否达标, 最差真空值, 最差真空PV名称)`

线程安全：通过 `threading.Lock` 保护所有共享状态的读写。

---

## 13. 完整老练流程

### 13.1 状态处理详解

以下是脉冲模式下，单目标功率的完整老练流程：

#### IDLE（空闲等待）

```
每 1 秒检查一次 control.start PV
  start == 1 → 转到 INITIALIZING
  start == 0 → 继续等待
```

#### INITIALIZING（初始化）

```
1. 通用条件检查（暂停/停止/故障）
2. PV 健康检查（所有 PV 是否在线）
3. 加载参数（从 PV 读取目标功率、Drive、脉宽参数等）
4. 配置 RF 模式（脉冲 or CW）
5. 启动 RF（含故障复位重试，最多 5 次）
   成功 → ADJUSTING_POWER
   失败 → ERROR
```

#### ADJUSTING_POWER（调节功率）

```
每 0.5 秒循环一次：

1. 通用条件检查
2. 如果有"展脉宽后等待"标志：
   - 等待 wait_before_expand 秒（非阻塞，每轮检查条件）
   - 等待结束后恢复初始脉宽
3. 真空检查 → 不达标则转 WAITING_VACUUM
4. 调用 PowerController.adjust() 调节 Drive
5. 功率达标后：
   - 脉冲模式 → EXPANDING_PULSE
   - CW 模式 → COMPLETED
```

#### EXPANDING_PULSE（展宽脉冲）

```
每 0.5 秒循环一次：

1. 通用条件检查
2. 等待 wait_time 秒（非阻塞，等待期间检查真空）
3. 真空检查
4. 调用 PulseController.expand() 增加脉宽
5. 展脉宽后检查功率是否偏离 → 偏离则回 ADJUSTING_POWER
6. 脉宽达标后：
   - 还有下一功率目标 → 切换目标，回 ADJUSTING_POWER
   - 所有目标完成 → COMPLETED
7. 脉宽未达标 → 更新 _pulse_step_start_time，继续等待下一轮展宽
```

#### PAUSED（暂停）

```
优先检查 reset 信号 → 收到则 reset 到 IDLE
检查 start 信号：
  start == 1 → 重新加载参数，恢复到暂停前的状态
  start == 0 → 继续等待
```

#### COMPLETED / ERROR / STOPPED（终止状态）

```
首次进入时执行清理（只执行一次）：
  - COMPLETED: 打印统计信息，设 start=0
  - ERROR: 关闭 RF，设 start=0
  - STOPPED: 关闭 RF

之后持续监听 reset 信号：
  reset == 1 → 执行手动 reset，回到 IDLE
```

---

## 14. 多目标功率模式

系统支持**功率阶梯列表**：用户通过 `AutoC_PowerTargets` waveform PV 设置多个功率目标（如 `[5, 10, 15, 20]` kW）。

### 多目标流程

```
目标列表: [5, 10, 15, 20] kW

第1轮: target_index=0, 目标=5kW
  ADJUSTING_POWER → 5kW达标 → EXPANDING_PULSE → 脉宽达标
  → 切换到下一目标

第2轮: target_index=1, 目标=10kW
  等待 wait_before_expand 秒
  恢复初始脉宽
  ADJUSTING_POWER → 10kW达标 → EXPANDING_PULSE → 脉宽达标
  → 切换到下一目标

...依此类推...

第4轮: target_index=3, 目标=20kW
  ADJUSTING_POWER → 20kW达标 → EXPANDING_PULSE → 脉宽达标
  → 没有更多目标 → COMPLETED
```

### 目标切换时的关键操作

1. `target_index += 1`
2. 更新 `target_power` 和 `control.current_target_power` PV
3. 重置功率迭代计数器
4. 设置 `_wait_before_power = True`（切换后先等待再调功率）
5. 设置 `_need_reset_pulse = True`（等待结束后恢复初始脉宽）
6. 转到 ADJUSTING_POWER（先等待 `wait_before_expand` 秒）

---

## 15. 故障恢复机制

### 15.1 自动恢复（RF Trip）

当 RF 在运行中因故障自动关闭（Trip）时：

```
_check_rf_status() 检测到 rf_on != 1
  ↓
故障是否超限？
  ├─ 是 → ERROR（需要手动 reset）
  └─ 否 → 自动恢复流程：
        1. 检查 start==1（防止竞态卡死）
        2. 复位所有故障 PV（reset_all_faults）
        3. 检查故障状态
        4. reset(clear_faults=False)：
           - 保留故障计数
           - 保留当前功率目标
           - 脉宽回退 pulse_drop ms（不低于原始初始值）
           - 保留跨状态协调标志（_wait_before_power 等）
        5. 回到 IDLE
        6. IDLE 检测到 start==1 → 自动进入 INITIALIZING
        7. INITIALIZING 重新启动 RF → ADJUSTING_POWER
```

### 15.2 手动复位（用户按 Reset）

用户在 COMPLETED/ERROR/STOPPED/PAUSED 状态按 Reset 按钮：

```
reset(clear_faults=True):
  1. 清除 start 信号（设为 0）
  2. 功率目标索引归零（回到第一个目标）
  3. 重置故障计数
  4. 从 PV 重新读取初始脉宽
  5. 清除所有状态标志
  6. 回到 IDLE
```

### 15.3 两种复位的区别

| | 手动复位 | 自动恢复 |
|---|---------|---------|
| 触发方式 | 用户按 Reset | RF Trip 自动触发 |
| 故障计数 | 清零 | 保留 |
| 功率目标 | 回到第一个 | 保持当前 |
| 脉宽 | 恢复到 PV 初始值 | 回退 pulse_drop ms |
| start 信号 | 清除（设为 0） | 保留（保持 1） |
| 协调标志 | 清除 | 保留 |

---

## 16. PV 键映射总表

### RF 控制 PV（8 个）

| 逻辑键 | EPICS PV 名称 | 用途 |
|--------|--------------|------|
| `rf.rf_on` | RFQ:LLRF:Con01:Opr_RFOn | RF 开关（1=开/0=关） |
| `rf.pulse_drive` | RFQ:LLRF:Con01:AmpPulseDrive_Set | 脉冲模式 Drive 值 |
| `rf.cw_drive` | RFQ:LLRF:Con01:AmpCWDrive_Set | CW 模式 Drive 值 |
| `rf.pulse_cw` | RFQ:LLRF:Con01:pulsecw | 模式选择（1=脉冲） |
| `rf.pulse_time` | RFQ:LLRF:Con01:RFPulseOnTime_Set | 脉冲宽度（秒） |
| `rf.sweep` | RFQ:LLRF:Con01_DAC:FreqSweep_Set | 频率扫描开关 |
| `rf.tracking` | RFQ:LLRF:Con01:frequency_tracking | 频率跟踪开关 |
| `rf.power` | RFQ:LLRF:Con01_RFIn03:Power | 实际 RF 功率读数（kW） |

### 故障 PV（4 检测 + 4 复位 = 8 个）

| 逻辑键 | 用途 |
|--------|------|
| `fault.arc` | ARC 打火状态（1=正常/0=故障） |
| `fault.VacInterlock` | 真空联锁状态 |
| `fault.interlock2` | 联锁 2 状态 |
| `fault.di4` | 数字输入 4 状态 |
| `fault.VacReset` | 真空复位（脉冲 1→0） |
| `fault.reset_interlock` | 联锁复位 |
| `fault.ResetPWFaultStat1` | 脉宽故障状态 1 复位 |
| `fault.ResetPWFaultStat2` | 脉宽故障状态 2 复位 |

### 真空 PV（8 个）

| 逻辑键 | EPICS PV 名称 |
|--------|--------------|
| `vacuum.0` | RFQ:Vac1 |
| `vacuum.1` | RFQ:Vac2 |
| ... | ... |
| `vacuum.7` | RFQ:Vac8 |

### 老练控制 PV（17 个）

| 逻辑键 | 用途 |
|--------|------|
| `control.start` | 启动/暂停信号（1=运行/0=暂停） |
| `control.reset` | 复位信号（脉冲 1→0） |
| `control.status` | 状态字符串显示 |
| `control.power_targets` | 功率目标列表（waveform PV） |
| `control.init_drive` | 初始 Drive 值 |
| `control.pulse_start` | 起始脉宽（ms） |
| `control.pulse_end` | 目标脉宽（ms） |
| `control.pulse_step` | 脉宽步长（ms） |
| `control.pulse_wait` | 每次展脉宽前等待时间（s） |
| `control.pulse_drop` | Trip 后脉宽回退量（ms） |
| `control.drive_step1` | Drive 大步调节步长 |
| `control.drive_step2` | Drive 小步调节步长 |
| `control.margin_large` | 大步调节功率偏差阈值（kW） |
| `control.margin_small` | 功率达标偏差阈值（kW） |
| `control.wait_before_expand` | 目标切换后等待时间（分钟） |
| `control.current_target_power` | 当前目标功率显示 |
| `control.current_pulse` | 当前脉宽显示（ms） |

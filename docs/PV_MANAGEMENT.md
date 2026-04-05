# RFQ 自动老练系统 — PV 管理文档

> 作者: Chengye Xu | 日期: 2026-04 | 版本: 3.0

---

## 1. 概述

本系统所有与 EPICS IOC 的交互均通过 `PVManager` 统一管理。PVManager 基于 **单例模式** 和 **长连接（epics.PV）**，提供 key → PV name 的映射，使得业务代码只需关心逻辑键（如 `'rf.rf_on'`），无需直接操作 EPICS PV 名称字符串。

### 设计原则

| 原则 | 说明 |
|------|------|
| **单一入口** | 所有 PV 的注册、读写、连接检查由 PVManager 唯一实例负责 |
| **key 索引** | 业务代码通过逻辑键（如 `'rf.power'`）访问，不直接使用 EPICS 名称 |
| **长连接** | 使用 `epics.PV()` 对象保持持久连接，避免反复创建短连接的开销 |
| **依赖注入** | PVManager 在 controller 中创建后注入所有子控制器，子控制器不自行创建连接 |
| **集中注册** | 所有 PV 在 `RFQController._register_all_pvs()` 中一次性从 config.yaml 批量注册 |

---

## 2. 架构

```
config.yaml                    RFQController
┌──────────────┐              ┌──────────────────────────────┐
│ pv:          │              │ _register_all_pvs()          │
│   rf: {...}  │──读取──→     │   register_group(rf, 'rf')   │
│   fault:{..} │              │   register_group(fault,'fault')│
│   control:{..}              │   register_group(control,...) │
│   vacuum:[…] │              │   register_list(vacuum, ...)  │
└──────────────┘              └──────────┬───────────────────┘
                                         │ 创建并注入
                                         ▼
                              ┌─────────────────────┐
                              │    PVManager (单例)   │
                              │                     │
                              │ _pv_cache: {key:PV} │
                              │ _pv_names: {key:name}│
                              │                     │
                              │ get(key) / put(key) │
                              │ get_pv_object(key)  │
                              │ check_all_connected()│
                              └──┬───┬───┬───┬──────┘
                                 │   │   │   │
                    ┌────────────┘   │   │   └────────────┐
                    ▼                ▼   ▼                ▼
              FaultHandler   VacuumChecker  PowerController  PulseController
              (callback监听)  (callback监听)  (读写PV)         (读写PV)
```

---

## 3. PVManager API 参考

> 源码: `rfq/utils/pv_manager.py`

### 3.1 实例化

```python
from rfq.utils.pv_manager import PVManager

pv_mgr = PVManager(config)    # 首次调用创建单例
pv_mgr2 = PVManager(config)   # 后续调用返回同一实例

PVManager.reset_instance()    # 重置单例（仅用于测试）
```

### 3.2 注册

| 方法 | 签名 | 说明 |
|------|------|------|
| `register` | `register(pv_key, pv_name)` | 注册单个 PV，建立长连接 |
| `register_group` | `register_group(group_dict, prefix)` | 批量注册字典，key 自动加前缀 |
| `register_list` | `register_list(pv_name_list, prefix)` | 批量注册列表，key 为 `prefix.0`, `prefix.1`, ... |

**注册示例**（在 `RFQController._register_all_pvs()` 中）:

```python
pv_cfg = self.config.pv

self.pv_manager.register_group(pv_cfg.get('rf', {}), 'rf')
self.pv_manager.register_group(pv_cfg.get('fault', {}), 'fault')
self.pv_manager.register_group(pv_cfg.get('control', {}), 'control')
self.pv_manager.register_list(pv_cfg.get('vacuum', []), 'vacuum')
```

### 3.3 读写

| 方法 | 签名 | 返回值 |
|------|------|--------|
| `get` | `get(pv_key, timeout=3.0)` | PV 值，失败返回 `None` |
| `put` | `put(pv_key, value, wait=False)` | `True` 成功 / `False` 失败 |

```python
power = pv_manager.get('rf.power')          # 读取功率
pv_manager.put('rf.pulse_drive', 50.0)      # 写入 Drive
```

### 3.4 高级操作

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_pv_object` | `get_pv_object(pv_key)` | 获取底层 `epics.PV` 对象（用于 callback） |
| `get_pv_name` | `get_pv_name(pv_key)` | 获取 key 对应的 EPICS 名称字符串 |
| `is_connected` | `is_connected(pv_key)` | 检查单个 PV 是否在线 |
| `check_all_connected` | `check_all_connected()` | 返回 `(bool, list)` — `(True, [])` 全部在线，`(False, [(key,name)...])` 存在不可达 |
| `get_registered_count` | `get_registered_count()` | 已注册 PV 总数 |

### 3.5 工具方法

| 方法 | 说明 |
|------|------|
| `safe_status(text, max_chars=40, max_bytes=40)` | 将字符串截断到指定字符/字节限制，用于 status PV |

---

## 4. PV Key 完整映射表

所有 PV 在 `config.yaml` 的 `pv` 节定义，通过 `register_group` / `register_list` 自动生成 key。

### 4.1 RF 控制 PV（前缀 `rf`）

| Key | EPICS PV 名称 | 方向 | 说明 |
|-----|---------------|------|------|
| `rf.rf_on` | `RFQ:LLRF:Con01:Opr_RFOn` | R/W | RF 开关 (1=开, 0=关) |
| `rf.pulse_drive` | `RFQ:LLRF:Con01:AmpPulseDrive_Set` | R/W | 脉冲模式 Drive |
| `rf.cw_drive` | `RFQ:LLRF:Con01:AmpCWDrive_Set` | R/W | CW 模式 Drive |
| `rf.pulse_cw` | `RFQ:LLRF:Con01:pulsecw` | R | 模式选择 (0=CW, 1=脉冲) |
| `rf.pulse_time` | `RFQ:LLRF:Con01:RFPulseOnTime_Set` | R/W | 脉冲宽度 (秒) |
| `rf.sweep` | `RFQ:LLRF:Con01_DAC:FreqSweep_Set` | R/W | 频率扫描 |
| `rf.tracking` | `RFQ:LLRF:Con01:frequency_tracking` | R/W | 频率跟踪 |
| `rf.power` | `RFQ:LLRF:Con01_RFIn03:Power` | R | 当前腔体功率 (kW) |

### 4.2 故障 PV（前缀 `fault`）

| Key | EPICS PV 名称 | 方向 | 说明 |
|-----|---------------|------|------|
| `fault.arc` | `RFQ:LLRF:Con01:ArcStatus_Rd` | R | Arc 故障 (0=故障, 1=正常) |
| `fault.VacInterlock` | `RFQ:LLRF:Con01:InterlockStatus_Rd` | R | 真空连锁 |
| `fault.interlock2` | `RFQ:LLRF:Con01:InterlockStatus2_Rd` | R | 连锁 2 |
| `fault.di4` | `RFQ:LLRF:Con01:di4` | R | DI4 |
| `fault.SSAComp` | `RFQ:LLRF:Mon02:ForwardPowerComp` | R | SSA 保护 |
| `fault.ReflectedPowerComp` | `RFQ:LLRF:Mon02:ReflectedPowerComp` | R | 反射功率保护 |
| `fault.reset_interlock` | `RFQ:LLRF:Con01:ResetInterlock` | W | 连锁复位 |
| `fault.ResetPWFaultStat1` | `RFQ:LLRF:Mon01:ResetPWFaultStat` | W | 功率故障复位 (Mon01) |
| `fault.ResetPWFaultStat2` | `RFQ:LLRF:Mon02:ResetPWFaultStat` | W | 功率故障复位 (Mon02) |
| `fault.VacReset` | `RFQ:Reset` | W | 真空复位 |

### 4.3 老练控制 PV（前缀 `control`）

| Key | EPICS PV 名称 | 方向 | 说明 |
|-----|---------------|------|------|
| `control.start` | `RFQ:LLRF:Con01:AutoC_Start` | R/W | 启动信号 (1=启动, 0=停止) |
| `control.reset` | `RFQ:LLRF:Con01:AutoC_Reset` | R/W | 复位信号 (1=复位) |
| `control.status` | `RFQ:LLRF:Con01:AutoC_Status` | W | 状态字符串输出 |
| `control.power_targets` | `RFQ:LLRF:Con01:AutoC_PowerTargets` | R | 功率目标列表 (waveform) |
| `control.init_drive` | `RFQ:LLRF:Con01:AutoC_InitDrive` | R | 初始 Drive 值 |
| `control.pulse_start` | `RFQ:LLRF:Con01:AutoC_PulseStart` | R | 初始脉宽 (ms) |
| `control.pulse_end` | `RFQ:LLRF:Con01:AutoC_PulseEnd` | R | 目标脉宽 (ms) |
| `control.pulse_step` | `RFQ:LLRF:Con01:AutoC_PulseStep` | R | 脉宽步长 (ms) |
| `control.drive_step1` | `RFQ:LLRF:Con01:AutoC_DriveStep1` | R | Drive 大步进 |
| `control.drive_step2` | `RFQ:LLRF:Con01:AutoC_DriveStep2` | R | Drive 小步进 |
| `control.margin_large` | `RFQ:LLRF:Con01:AutoC_MarginLarge` | R | 大误差阈值 (kW) |
| `control.margin_small` | `RFQ:LLRF:Con01:AutoC_MarginSmall` | R | 小误差阈值 (kW) |
| `control.pulse_wait` | `RFQ:LLRF:Con01:AutoC_PulseWaitTime` | R | 展脉宽等待时间 (s) |
| `control.wait_before_expand` | `RFQ:LLRF:Con01:AutoC_PowerWaitTime` | R | 展脉宽前等待时间 (min) |
| `control.pulse_drop` | `RFQ:LLRF:Con01:AutoC_PulseDrop` | R | Trip 后脉宽回退量 (ms) |
| `control.current_target_power` | `RFQ:LLRF:Con01:AutoC_CurrentTargetPower` | R/W | 当前目标功率 (kW) |
| `control.current_pulse` | `RFQ:LLRF:Con01:AutoC_CurrentPulse` | W | 当前脉宽显示 (ms) |

### 4.4 真空 PV（前缀 `vacuum`）

列表形式注册，key 为 `vacuum.{index}`：

| Key | EPICS PV 名称 | 说明 |
|-----|---------------|------|
| `vacuum.0` | `RFQ:Vac1` | 真空计 1 |
| `vacuum.1` | `RFQ:Vac2` | 真空计 2 |
| `vacuum.2` | `RFQ:Vac3` | 真空计 3 |
| `vacuum.3` | `RFQ:Vac4` | 真空计 4 |
| `vacuum.4` | `RFQ:Vac5` | 真空计 5 |
| `vacuum.5` | `RFQ:Vac6` | 真空计 6 |
| `vacuum.6` | `RFQ:Vac7` | 真空计 7 |
| `vacuum.7` | `RFQ:Vac8` | 真空计 8 |

---

## 5. 各模块 PV 使用方式

### 5.1 RFQController（主控制器）

> 源码: `rfq/core/controller.py`

主控制器是 PV 管理的核心，负责：

1. **创建 PVManager 单例** — `__init__` 中调用 `PVManager(config)` 并注册所有 PV
2. **创建子控制器并注入** — 将 `pv_manager` 传入所有子控制器构造函数
3. **初始化健康检查** — `_handle_initializing` 中调用 `check_all_connected()` 验证所有 PV 连通
4. **参数加载与 RF 控制** — 通过 `_get_pv(key)` / `_put_pv(key, value)` 封装读写

```python
class RFQController:
    def __init__(self, config, pv_manager=None):
        if pv_manager is not None:
            self.pv_manager = pv_manager       # 测试注入
        else:
            PVManager.reset_instance()
            self.pv_manager = PVManager(config)
            self._register_all_pvs()

        self.fault_handler = FaultHandler(config, self.pv_manager)
        self.vacuum_checker = VacuumChecker(config, self.pv_manager)
        self.power_controller = PowerController(config, self.pv_manager)
        self.pulse_controller = PulseController(config, self.pv_manager)
```

### 5.2 FaultHandler（故障处理器）

> 源码: `rfq/controllers/fault.py`

- **注册依赖**: PV 已由主控制器注册，FaultHandler 通过 `get_pv_object(key)` 获取 PV 对象并添加 callback
- **监听 PV**: `fault.arc`, `fault.VacInterlock`, `fault.interlock2`, `fault.di4`
- **复位 PV**: `fault.VacReset`, `fault.reset_interlock`, `fault.ResetPWFaultStat1`, `fault.ResetPWFaultStat2`
- **无直接 import epics**: 所有 EPICS 交互通过 `pv_manager` 完成

```python
class FaultHandler:
    FAULT_PV_KEYS = ['fault.arc', 'fault.VacInterlock', 'fault.interlock2', 'fault.di4']

    def __init__(self, config, pv_manager):
        self.pv_manager = pv_manager
        for pv_key in self.FAULT_PV_KEYS:
            pv_obj = self.pv_manager.get_pv_object(pv_key)
            if pv_obj:
                pv_obj.add_callback(self._make_callback(pv_key))
```

### 5.3 VacuumChecker（真空检测器）

> 源码: `rfq/controllers/vacuum.py`

- **监听 PV**: `vacuum.0` ~ `vacuum.7`
- **callback**: 通过 `get_pv_object(key)` 添加 callback，实时追踪最差真空值
- **判定**: 与 `config.vacuum['threshold']` 比较，更新 `vacuum_ok` 状态

```python
class VacuumChecker:
    def __init__(self, config, pv_manager):
        self.pv_manager = pv_manager
        for i, pv_name in enumerate(vacuum_pv_names):
            key = f'vacuum.{i}'
            pv_obj = self.pv_manager.get_pv_object(key)
            if pv_obj:
                pv_obj.add_callback(self._on_vacuum_change, pv_key=key)
```

### 5.4 PowerController（功率控制器）

> 源码: `rfq/controllers/power.py`

- **读取**: `rf.power`, `rf.pulse_drive`(或 `rf.cw_drive`), `control.drive_step1`, `control.drive_step2`, `control.margin_large`, `control.margin_small`
- **写入**: `rf.pulse_drive`(或 `rf.cw_drive`)

```python
def adjust(self, current_drive_key, target_power):
    current_power = self.pv_manager.get('rf.power')
    current_drive = self.pv_manager.get(current_drive_key)
    drive_step1 = self.pv_manager.get('control.drive_step1')
    self.pv_manager.put(current_drive_key, new_drive)
```

### 5.5 PulseController（脉冲控制器）

> 源码: `rfq/controllers/pulse.py`

- **读取**: `rf.pulse_time`, `rf.pulse_drive`(或 `rf.cw_drive`), `control.drive_step1`
- **写入**: `rf.pulse_time`, `rf.pulse_drive`(降功率模式时)

```python
def expand(self, current_drive_key, init_drive, pulse_end, pulse_step):
    current_pulse = self.pv_manager.get('rf.pulse_time')
    self.pv_manager.put('rf.pulse_time', new_s)
```

---

## 6. PV 生命周期

```
程序启动
   │
   ▼
RFQController.__init__()
   │
   ├── PVManager(config)              ← 创建单例
   ├── _register_all_pvs()            ← 从 config.yaml 批量注册
   │     ├── register_group(rf, 'rf')
   │     ├── register_group(fault, 'fault')
   │     ├── register_group(control, 'control')
   │     └── register_list(vacuum, 'vacuum')
   │
   ├── FaultHandler(config, pv_manager)    ← 注入，注册 callback
   ├── VacuumChecker(config, pv_manager)   ← 注入，注册 callback
   ├── PowerController(config, pv_manager) ← 注入
   └── PulseController(config, pv_manager) ← 注入
         │
         ▼
   _handle_initializing()
         │
         └── check_all_connected()     ← 健康检查，验证所有 PV 连通
               │
               ▼
            主循环运行 (get/put 读写)
               │
               ▼
   程序退出 / PVManager.reset_instance()
         │
         └── _cleanup()               ← 清理所有 callback 和连接
```

---

## 7. 测试中的 PV 管理

单元测试通过 **FakePVManager** 替代真实 EPICS 连接：

```python
class FakePVManager:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.put_calls = []

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.put_calls.append((key, value))
        self.values[key] = value
        return True

    def get_pv_object(self, key):
        return None

    def get_pv_name(self, key):
        return key

    def check_all_connected(self):
        return (True, [])
```

**测试注入方式**:

```python
pv_mgr = FakePVManager({"rf.power": 5.0, "rf.pulse_drive": 100.0})
ctl = RFQController(DummyConfig(), pv_manager=pv_mgr)
```

---

## 8. 故障复位 PV 操作时序

故障复位由 `FaultHandler.pulse_reset_all()` 按以下顺序执行：

| 步骤 | Key | EPICS 名称 | 操作 |
|------|-----|-----------|------|
| 1 | `fault.VacReset` | `RFQ:Reset` | 置 1 → 等 2s → 置 0 → 等 2s |
| 2 | `fault.reset_interlock` | `RFQ:LLRF:Con01:ResetInterlock` | 置 1 → 等 1s → 置 0 → 等 1s |
| 3 | `fault.ResetPWFaultStat1` | `RFQ:LLRF:Mon01:ResetPWFaultStat` | 置 1 → 等 1s → 置 0 → 等 1s |
| 4 | `fault.ResetPWFaultStat2` | `RFQ:LLRF:Mon02:ResetPWFaultStat` | 置 1 → 等 1s → 置 0 → 等 1s |

---

## 9. 新增 PV 的操作指南

如需新增一个 EPICS PV，按以下步骤操作：

### 步骤 1: 在 config.yaml 中定义

在 `pv` 节下的对应分组中添加 PV 名称：

```yaml
pv:
  rf:
    new_signal: 'RFQ:LLRF:Con01:NewSignal'
```

### 步骤 2: 自动注册

由于 `_register_all_pvs()` 使用 `register_group` 批量注册，新 PV 会自动获得 key `rf.new_signal`，**无需修改注册代码**。

### 步骤 3: 在业务代码中使用

```python
value = self.pv_manager.get('rf.new_signal')
self.pv_manager.put('rf.new_signal', 1)
```

### 步骤 4: 更新测试

在 FakePVManager 的 values 中添加对应的 key-value 即可。

---

## 10. 注意事项

1. **不要在子控制器中直接 import epics** — 所有 EPICS 交互必须通过 `pv_manager` 完成
2. **不要使用 `epics.caget` / `epics.caput`** — 这些是短连接，会反复创建/销毁连接
3. **不要在子控制器中自行创建 PVManager 实例** — 由主控制器创建并注入
4. **config.yaml 中的 PV 分组名即为 key 前缀** — `pv.rf.xxx` → key 为 `rf.xxx`
5. **真空 PV 使用列表形式** — key 自动编号为 `vacuum.0`, `vacuum.1`, ...
6. **测试时使用 FakePVManager 注入** — 通过 `RFQController(config, pv_manager=fake)` 传入

# RFQ softIOC 仿真测试环境设计文档

作者：Adrian Xu
日期：2025-11

---

## 1. 背景与目标

RFQ 自动老练程序（`AutoConditioning`）通过 EPICS Channel Access 与硬件通信。
在没有生产硬件的情况下，使用 `caproto`（纯 Python EPICS 实现）在本地模拟所有 PV，
使老练程序可以完整运行并验证控制逻辑。

**目标**：
- 提供与真实硬件相同的 PV 接口，老练程序**不需要修改任何代码**
- 内置功率物理仿真，使控制算法可以真实运转
- 支持故障场景注入，验证故障处理和自动复位逻辑

---

## 2. 要创建的文件

```
AutoConditioning/
└── tests/
    └── sim_ioc.py    ← 新建
```

---

## 3. PV 清单

### 3.1 RF 控制 PV

| PV 名称 | 类型 | 初始值 | 说明 |
|---------|------|--------|------|
| `RFQ:LLRF:Con01:Opr_RFOn` | int | 0 | RF 开/关 |
| `RFQ:LLRF:Con01:AmpPulseDrive_Set` | float | 0.0 | 脉冲模式 Drive |
| `RFQ:LLRF:Con01:AmpCWDrive_Set` | float | 0.0 | CW 模式 Drive |
| `RFQ:LLRF:Con01:pulsecw` | int | 0 | 模式选择（0=脉冲，1=CW） |
| `RFQ:LLRF:Con01:RFPulseOnTime_Set` | float | 100.0 | 脉冲宽度（μs） |
| `RFQ:LLRF:Con01_DAC:FreqSweep_Set` | int | 0 | 频率扫描 |
| `RFQ:LLRF:Con01:frequency_tracking` | int | 0 | 频率跟踪 |
| `RFQ:LLRF:Con01_RFIn03:Power` | float | 0.0 | 当前腔体功率（kW）**[仿真输出]** |
| `RFQ:LLRF:Con01:WaitTime_Set` | float | 0.5 | 等待时间 |

### 3.2 故障 PV

| PV 名称 | 类型 | 初始值 | 说明 |
|---------|------|--------|------|
| `RFQ:LLRF:Con01:Arc_Status` | int | 1 | 弧光状态（1=正常，0=故障） |
| `RFQ:LLRF:Con01:Interlock_Status` | int | 1 | 联锁状态（1=正常，0=故障） |
| `RFQ:LLRF:Con01:ResetInterlock` | int | 0 | 复位联锁 |
| `RFQ:LLRF:Mon02:ForwardPowerComp` | int | 1 | SSA 前向功率补偿状态 |
| `RFQ:LLRF:Mon02:ReflectedPowerComp` | int | 1 | 反射功率补偿状态 |
| `RFQ:LLRF:Mon02:ResetPWFaultStat` | int | 0 | 复位功率故障 |

### 3.3 真空 PV

| PV 名称 | 类型 | 初始值 | 说明 |
|---------|------|--------|------|
| `RFQ:Vac4` | float | 1e-6 | 真空计1（Pa）**[手动赋值]** |
| `IA-RFQ-CR:VG01_CH02_CavE:Pres` | float | 1e-6 | 真空计2（Pa）**[手动赋值]** |

### 3.4 老练控制 PV

| PV 名称 | 类型 | 初始值 | 说明 |
|---------|------|--------|------|
| `RFQ:LLRF:Con01:AutoC_Start` | int | 0 | 启动老练 |
| `RFQ:LLRF:Con01:AutoC_Reset` | int | 0 | 复位 |
| `RFQ:LLRF:Con01:AutoC_Status` | str | 'IDLE' | 当前状态文本 |
| `RFQ:LLRF:Con01:AutoC_TargetPower` | float | 50.0 | 目标功率（kW） |
| `RFQ:LLRF:Con01:AutoC_InitDrive` | float | 100.0 | 初始 Drive |
| `RFQ:LLRF:Con01:AutoC_PulseStart` | float | 100.0 | 脉冲起始宽度（μs） |
| `RFQ:LLRF:Con01:AutoC_PulseEnd` | float | 1000.0 | 脉冲目标宽度（μs） |
| `RFQ:LLRF:Con01:AutoC_PulseStep` | float | 50.0 | 展宽步长（μs） |
| `RFQ:LLRF:Con01:AutoC_DriveStep1` | float | 10.0 | 功率调节大步长 |
| `RFQ:LLRF:Con01:AutoC_DriveStep2` | float | 2.0 | 功率调节小步长 |
| `RFQ:LLRF:Con01:AutoC_MarginLarge` | float | 5.0 | 大裕度阈值（kW） |
| `RFQ:LLRF:Con01:AutoC_MarginSmall` | float | 1.0 | 小裕度阈值（kW） |

### 3.5 测试辅助 PV

> 非真实硬件 PV，仅用于在测试中手动注入故障场景。

| PV 名称 | 类型 | 说明 |
|---------|------|------|
| `RFQ:SIM:TriggerArc` | int | 写 1 → 触发弧光故障（自动清零） |
| `RFQ:SIM:TriggerInterlock` | int | 写 1 → 触发联锁故障（自动清零） |

---

## 4. 仿真模型

### 4.1 功率仿真（每 0.1 秒更新）

```
稳态功率 = drive × 0.1  (kW)

  drive = 500  →  power = 50 kW
  drive = 100  →  power = 10 kW

实时功率（一阶低通滤波，模拟响应延迟）：
  power_new = power_old × 0.7 + 稳态功率 × 0.3



RF 关闭时（rf_on = 0）：
  power 指数衰减（× 0.3 每步）直至归零。
```

控制器的双步长算法可以完整运转：调大 drive → power 上升 → 收敛到目标功率。

### 4.2 真空 PV（手动赋值）

真空 PV 为静态值，IOC 不自动更新，由用户直接 `caput` 写入：

```bash
# 模拟真空超标（超过阈值 5e-5 Pa）
caproto-put RFQ:Vac4 1e-4
caproto-put "IA-RFQ-CR:VG01_CH02_CavE:Pres" 1e-4

# 真空恢复正常
caproto-put RFQ:Vac4 1e-6
caproto-put "IA-RFQ-CR:VG01_CH02_CavE:Pres" 1e-6
```

### 4.3 故障复位仿真

| 触发条件 | IOC 响应 |
|---------|---------|
| `ResetInterlock = 1` | 延迟 1 秒后 arc_status / interlock_status → 1 |
| `ResetPWFaultStat = 1` | 延迟 1 秒后 SSAComp / ReflectedPowerComp → 1 |
| `TriggerArc = 1` | arc_status→0，rf_on→0，power→0，触发 PV 自动清零 |
| `TriggerInterlock = 1` | interlock_status→0，rf_on→0，power→0，触发 PV 自动清零 |

---


## 6. 安装与运行

```bash
# 1. 安装 caproto
pip install caproto

# 2. 终端 A：启动仿真 IOC
cd AutoConditioning
python tests/sim_ioc.py

# 3. 终端 B：启动老练程序（无需修改任何代码）
python main.py

# 4. 终端 C：手动操作与观测（caproto 自带命令行工具，无需安装 EPICS base）
caproto-put RFQ:LLRF:Con01:AutoC_TargetPower 50.0   # 设置目标功率
caproto-put RFQ:LLRF:Con01:AutoC_InitDrive   100.0  # 设置初始 Drive
caproto-put RFQ:LLRF:Con01:AutoC_Start       1      # 启动老练
caproto-get RFQ:LLRF:Con01_RFIn03:Power             # 查看当前功率
caproto-get RFQ:Vac4                                # 查看真空
caproto-monitor RFQ:LLRF:Con01_RFIn03:Power         # 持续监测功率变化

# 5. 注入测试场景
caproto-put RFQ:SIM:TriggerArc       1     # 触发弧光故障
caproto-put RFQ:SIM:TriggerInterlock 1     # 触发联锁故障
caproto-put RFQ:Vac4                 1e-4  # 手动设置真空超标
caproto-put RFQ:Vac4                 1e-6  # 手动恢复真空
```

---

## 7. 可验证的测试场景

| 场景 | 操作 | 预期结果 |
|------|------|---------|
| 正常启动 | `AutoC_Start=1` | IDLE → INITIALIZING → ADJUSTING_POWER |
| 功率收敛 | 观察 power 和 drive 变化 | drive 逐步增大，power 收敛至目标值 |
| 脉冲展宽 | 脉冲模式下功率达标后 | 进入 EXPANDING_PULSE，pulse_time 逐步增大 |
| 弧光故障恢复 | `TriggerArc=1` | 故障计数 +1，自动复位，重新初始化 |
| 故障超限 | 连续触发 20 次故障 | 进入 ERROR 状态 |
| 真空超标暂停 | `caproto-put RFQ:Vac4 1e-4` | 进入 WAITING_VACUUM，手动恢复后自动继续 |
| 用户停止 | `AutoC_Reset=1` | 进入 STOPPED，状态机停止 |

---

## 8. 注意事项

**1. FaultHandler 不支持依赖注入**

`fault.py:38–41` 直接调用 `epics.PV()` 注册 callback，绕过了 PVManager 的依赖注入。
因此必须由 caproto IOC 提供真实的 EPICS PV，纯 Mock 方式无法触发故障回调逻辑。

**2. 网络要求**

caproto（服务端）和 PyEPICS（客户端）需在同一网络广播域内通信。
本机运行默认满足；若有防火墙，需开放 UDP 5064/5065 端口。


# RFQ 自动老练系统

基于状态机的 RFQ（射频四极子加速器）自动老练控制程序，通过 EPICS CA 协议与硬件交互，自动完成 RF 功率爬坡、稳定建场、脉宽展宽等老练流程。

作者: Chengye Xu

---

## 目录结构

```
AutoConditioning/
├── main.py                  # 主程序入口
├── config.yaml              # 配置文件（PV名称、阈值、循环参数）
├── requirements.txt
├── rfq/
│   ├── core/
│   │   ├── controller.py    # 主控制器（状态机调度）
│   │   ├── state.py         # 状态枚举与合法转换表
│   │   ├── config.py        # YAML配置加载（支持热更新）
│   │   ├── params.py        # 运行参数数据类与PV加载器
│   │   ├── rf_manager.py    # RF启停与模式配置
│   │   └── pv_keys.py       # PV逻辑键常量
│   ├── controllers/
│   │   ├── power.py         # 功率调节控制器
│   │   ├── pulse.py         # 脉宽展宽控制器
│   │   ├── vacuum.py        # 真空监测（callback驱动）
│   │   └── fault.py         # 故障检测与复位（callback驱动）
│   └── utils/
│       └── pv_manager.py    # PV长连接管理
├── tests/
│   ├── sim_ioc.py           # caproto 仿真 IOC
│   └── test_scenarios.py    # 集成测试脚本
├── docs/
│   ├── STABLE_BUILDING_LOGIC.md     # 稳定建场逻辑设计文档
│   └── PROJECT_OPTIMIZATION_PLAN.md # 优化计划
└── logs/                    # 运行日志（自动创建，按天轮转，保留30天）
```

---

## 状态机

### 状态列表

| 状态 | 编号 | 说明 |
|------|------|------|
| `IDLE` | 0 | 等待启动信号 |
| `INITIALIZING` | 10 | PV连接检查、参数加载、RF启动 |
| `PAUSED` | 15 | 暂停，等待恢复信号 |
| `STABLE_BUILDING` | 18 | 稳定建场（detuning 判据递增 Drive） |
| `ADJUSTING_POWER` | 20 | 调节 Drive 使功率达到目标值 |
| `WAITING_VACUUM` | 25 | 等待真空压力恢复到阈值以下 |
| `EXPANDING_PULSE` | 30 | 按步长展宽脉冲宽度 |
| `COMPLETED` | 90 | 老练完成 |
| `ERROR` | 100 | 错误，等待手动 reset |
| `STOPPED` | 101 | 用户停止，等待手动 reset |

### 正常流程

```
IDLE ──(start=1)──▶ INITIALIZING ──▶ STABLE_BUILDING ──▶ ADJUSTING_POWER
                                                                │
                                          ◀──(真空超标)──────────┤
                                          WAITING_VACUUM         │
                                          ──(恢复)──────────────▶│
                                                                 │
                                                    ──(功率达标，脉冲模式)──▶ EXPANDING_PULSE
                                                    │                               │
                                                    │◀──(有下一功率目标)────────────┘
                                                    │
                                                    ──(功率达标，CW模式 / 所有目标完成)──▶ COMPLETED
```

### 异常处理

- 任意活动状态 + `start=0` → `PAUSED`（可恢复）
- `PAUSED` + `start=1` → 恢复到暂停前的状态
- RF 掉线且故障未超限 → 自动复位后回到 `IDLE` 重启
- RF 掉线且故障超限 → `ERROR`
- 用户在非活动状态写 `start=0` → `STOPPED`

---

## 快速开始

### 安装依赖

```bash
pip install pyepics pyyaml
# 仿真IOC（可选）
pip install caproto
```

### 修改配置

编辑 `config.yaml`，主要关注：

- `vacuum.threshold`：真空阈值（Pa），超过此值触发等待
- `loop.max_faults`：滑动窗口内最大故障次数
- `loop.fault_window_minutes`：故障计数滑动窗口（分钟）
- `loop.max_iterations`：最大功率调节迭代次数
- `pv.*`：所有 EPICS PV 名称

### 连接真实硬件运行

```bash
python main.py
# 按 Enter 确认后开始运行，通过 EPICS 设置参数，然后：
caput RFQ:LLRF:Con01:AutoC_Start 1
```

### 使用仿真 IOC 开发调试

```bash
# 终端 A：启动仿真 IOC
python tests/sim_ioc.py

# 终端 B：启动主程序
python main.py

# 终端 C：验证 PV 可达后启动
caput RFQ:LLRF:Con01:AutoC_Start 1
```

---

## 关键 EPICS PV

### 操作员控制 PV

| 逻辑键 | EPICS PV | 说明 |
|--------|----------|------|
| `control.start` | `AutoC_Start` | 1=启动/恢复，0=暂停/停止 |
| `control.reset` | `AutoC_Reset` | 写1复位到IDLE |
| `control.power_targets` | `AutoC_PowerTargets` | 目标功率列表（waveform，kW，零值无效） |
| `control.init_drive` | `AutoC_InitDrive` | 初始 Drive 值 |
| `control.pulse_start` | `AutoC_PulseStart` | 脉冲起始宽度（ms） |
| `control.pulse_end` | `AutoC_PulseEnd` | 脉冲目标宽度（ms） |
| `control.pulse_step` | `AutoC_PulseStep` | 展宽步长（ms） |
| `control.drive_step1` | `AutoC_DriveStep1` | 功率调节大步长 |
| `control.drive_step2` | `AutoC_DriveStep2` | 功率调节小步长 |
| `control.margin_large` | `AutoC_MarginLarge` | 功率大裕度阈值（kW） |
| `control.margin_small` | `AutoC_MarginSmall` | 功率小裕度阈值（kW） |
| `control.pulse_wait` | `AutoC_PulseWaitTime` | 每次展脉宽前等待时间（s） |
| `control.wait_before_expand` | `AutoC_PowerWaitTime` | 展脉宽后加功率前等待时间（min） |
| `control.pulse_drop` | `AutoC_PulseDrop` | 故障后脉宽下降量（ms） |

### 程序写入 PV（只读监控）

| 逻辑键 | EPICS PV | 说明 |
|--------|----------|------|
| `control.status` | `AutoC_Status` | 当前状态文本 |
| `control.current_target_power` | `AutoC_CurrentTargetPower` | 当前目标功率（kW） |
| `control.current_pulse` | `AutoC_CurrentPulse` | 当前脉冲宽度（ms） |

---

## 故障处理

### 故障检测

以下 PV 通过 callback 实时监听（值为 0 表示故障）：

| 故障类型 | 说明 |
|----------|------|
| `fault.arc` | 打火故障 |
| `fault.VacInterlock` | 真空联锁 |
| `fault.interlock2` | 联锁2 |
| `fault.di4` | 数字输入4 |

故障采用**滑动窗口计数**（默认：30分钟内20次）。

### 故障复位顺序

| 步骤 | PV | 高电平时间 | 等待时间 |
|------|----|-----------|---------|
| 1 | `VacReset` | 2s | 2s |
| 2 | `ResetPWFaultStat1` | 1s | 1s |
| 3 | `ResetPWFaultStat2` | 1s | 1s |
| 4 | `ResetInterlock` | 1s | 1s |

### 自动恢复 vs 手动复位

| 类型 | 触发 | 行为 |
|------|------|------|
| 自动恢复 | RF掉线，故障未超限 | 保留功率目标，脉宽下降 `pulse_drop` ms，重启老练 |
| 手动复位 | 操作员写 `AutoC_Reset=1` | 故障计数清零，回到第一个功率目标，脉宽恢复初始值 |

---

## 仿真 IOC

`tests/sim_ioc.py` 提供完整硬件仿真，支持故障注入和真空控制：

**功率仿真**：`power = drive × 0.1 kW`，一阶低通滤波（0.1s 更新周期）

```bash
# 故障注入
caput RFQ:SIM:TriggerArc 1           # 触发打火
caput RFQ:SIM:TriggerInterlock 1     # 触发联锁
caput RFQ:SIM:BlockRFOn 1            # 阻止RF打开
caput RFQ:SIM:BlockPower 1           # 强制功率为0

# 真空控制
caput RFQ:SIM:VacAll 1e-4            # 所有真空计同时超标
caput RFQ:SIM:VacTarget 2            # 指定真空计编号（0-5）
caput RFQ:SIM:VacSingle 1e-4         # 设置指定真空计
```

---

## 集成测试

需先启动仿真 IOC 和主程序：

```bash
python tests/test_scenarios.py           # 全部测试
python tests/test_scenarios.py --fault   # 只测故障处理
python tests/test_scenarios.py --vacuum  # 只测真空联锁
python tests/test_scenarios.py --skip-init  # 跳过初始化检查
```

---

## 日志

日志存放在 `logs/` 目录（自动创建），按天轮转，保留30天：

```
logs/rfq_conditioning.log              # 当天
logs/rfq_conditioning_2026-04-11.log  # 历史
```

日志级别在 `config.yaml` 的 `logging.level` 中配置，默认 `INFO`，调试时改为 `DEBUG`。

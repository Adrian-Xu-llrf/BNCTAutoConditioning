# RFQ 自动老练控制系统

基于状态机的 RFQ（射频四极加速器）自动老练控制系统，用于 RF 加速器的自动化调试和运行。

作者: Chengye Xu  
日期: 2026-03

---

## 系统概述

本系统采用状态机模式管理 RFQ 的老练流程，支持：
- 多功率目标自动切换
- 脉冲宽度自动展宽
- 故障自动检测与恢复
- 真空连锁保护
- EPICS PV 参数配置

---

## 系统架构

```
rfq/
├── core/                    # 核心控制器
│   ├── controller.py        # 主状态机控制器
│   ├── state.py            # 状态定义
│   └── config.py           # 配置管理
├── controllers/            # 子控制器
│   ├── fault.py            # 故障处理
│   ├── vacuum.py           # 真空监测
│   ├── power.py            # 功率调节
│   └── pulse.py            # 脉冲控制
└── utils/
    └── pv_manager.py       # EPICS PV 管理
```

---

## 状态机

### 状态列表

| 状态 | 说明 |
|------|------|
| IDLE | 空闲/待机状态 |
| INITIALIZING | 初始化中（启动RF） |
| ADJUSTING_POWER | 调节功率 |
| WAITING_VACUUM | 等待真空达标 |
| EXPANDING_PULSE | 展宽脉冲 |
| PAUSED | 暂停 |
| COMPLETED | 完成 |
| ERROR | 错误 |
| STOPPED | 停止 |

### 状态转换图

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    ▼                                             │
┌──────┐     ┌──────────────┐     ┌──────────────────┐           │
│ IDLE │────▶│INITIALIZING │────▶│ ADJUSTING_POWER  │◀──────────┤
└──────┘     └──────────────┘     └────────┬─────────┘           │
     ▲                                       │                      │
     │                                       ▼                      │
     │                              ┌──────────────────┐           │
     │                              │WAITING_VACUUM    │           │
     │                              └──────────────────┘           │
     │                                       │                      │
     │                                       ▼                      │
     │                              ┌──────────────────┐           │
     │                              │ EXPANDING_PULSE  │───────────┤
     │                              └──────────────────┘           │
     │                                       │                      │
     │                                       ▼                      │
     │                              ┌──────────────────┐           │
     └──────────────────────────────│    COMPLETED     │           │
                                    └──────────────────┘           │
                                                                  │
     ┌──────┐     ┌──────────┐                                      │
     │ERROR │◀────│(any)     │──────────────────────────────────────┘
     └──────┘     └──────────┘
```

---

## 工作流程

### 1. 初始化 (IDLE → INITIALIZING)

- 读取配置参数
- 识别 RF 模式（脉冲/CW）
- 启动 RF 系统

### 2. 功率调节 (ADJUSTING_POWER)

- 监控当前功率
- 自动调节 Drive 使功率达到目标
- 等待稳定后进入下一阶段

### 3. 真空监测 (WAITING_VACUUM)

- 持续监测真空度
- 真空达标后返回功率调节

### 4. 脉冲展宽 (EXPANDING_PULSE)

- 按步长逐步展宽脉冲
- **每次展宽后检查功率偏离**
- 功率偏离时返回调功率
- 到达目标脉宽后切换下一功率目标或完成

### 5. 故障恢复

- 记录故障次数
- 故障未超限时自动复位并恢复
- 故障超限后进入 ERROR 状态

---

## 配置文件

所有参数通过 `config.yaml` 配置：

### 真空参数

```yaml
vacuum:
  threshold: 5.0e-5      # 真空阈值 (Pa)
```

### 循环参数

```yaml
loop:
  interval: 0.5           # 主循环间隔 (秒)
  max_faults: 20         # 最大故障次数
  max_iterations: 1000   # 最大迭代次数
  wait_time_default: 1.0 # 每次展脉宽等待时间 (秒)
  pulse_step: 0.5        # 脉宽步长 (ms)
```

### RF 启动配置

```yaml
rf_startup:
  max_retry: 5      # 最大重试次数
  retry_interval: 2 # 重试间隔 (秒)
```

### PV 定义

```yaml
pv:
  rf:
    rf_on: 'RFQ:LLRF:Con01:Opr_RFOn'
    pulse_drive: 'RFQ:LLRF:Con01:AmpPulseDrive_Set'
    power: 'RFQ:LLRF:Con01_RFIn03:Power'
  fault:
    arc: 'RFQ:LLRF:Con01:ArcStatus_Rd'
    VacInterlock: 'RFQ:LLRF:Con01:InterlockStatus_Rd'
  control:
    start: 'RFQ:LLRF:Con01:AutoC_Start'
    reset: 'RFQ:LLRF:Con01:AutoC_Reset'
```

---

## 故障复位

系统按顺序执行以下 PV 复位：

| 步骤 | PV | 说明 |
|------|-----|------|
| 1 | VacReset | 高电平保持4s，再等2s |
| 2 | reset_interlock | 高1s → 低1s |
| 3 | ResetPWFaultStat1 | 高1s → 低1s |
| 4 | ResetPWFaultStat2 | 高1s → 低1s |

---

## 使用方法

### 启动

```bash
python main.py
```

### EPICS PV 控制

| PV | 功能 |
|-----|------|
| AutoC_Start | 启动信号 (1=启动, 0=暂停) |
| AutoC_Reset | 复位信号 (1=复位) |
| AutoC_PowerTargets | 功率目标列表 (waveform) |
| AutoC_PulseStart | 初始脉宽 (ms) |
| AutoC_PulseEnd | 目标脉宽 (ms) |

### 手动复位

- **清除故障计数**: `reset(clear_faults=True)` — 回到初始状态
- **保留故障计数**: `reset(clear_faults=False)` — 自动恢复，脉宽下降

---

## 测试

```bash
# 单元测试
pytest tests/unit_2_1_2_6/

# 集成测试
pytest tests/integration/
```

---

## 注意事项

1. 所有可调参数均通过 EPICS PV 配置，便于运行时调整
2. 故障复位包含 VacReset，确保真空连锁故障能正确清除
3. 每次脉冲展宽后检查功率偏离，保证功率稳定性
4. 支持多功率目标连续老练

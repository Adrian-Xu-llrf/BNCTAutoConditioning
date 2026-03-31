# RFQ自动老练系统流程说明

## 一、系统架构

系统采用**状态机模式**管理整个老练流程，核心状态包括：

| 状态代码 | 状态名称 | 说明 |
|---------|---------|------|
| 0 | IDLE | 空闲等待 |
| 10 | INITIALIZING | 初始化RF系统 |
| 15 | PAUSED | 已暂停 |
| 20 | ADJUSTING_POWER | 调节功率 |
| 25 | WAITING_VACUUM | 等待真空恢复 |
| 30 | EXPANDING_PULSE | 展宽脉冲 |
| 90 | COMPLETED | 老练完成 |
| 100 | ERROR | 错误状态 |
| 101 | STOPPED | 用户停止 |

---

## 二、完整老练流程

### 阶段1：启动与初始化 (IDLE → INITIALIZING)

1. **启动条件**：通过EPICS设置 `AutoC_Start=1` 触发启动
2. **参数加载**：
   - 从PV读取**多目标功率列表** (`AutoC_PowerTargets`)
   - 读取初始Drive值 (`AutoC_InitDrive`)
   - 读取脉冲参数：起始脉宽、终止脉宽、步长、等待时间等
   - 读取功率调节参数：Drive大步长、小步长、大容差、小容差

### 阶段2：RF模式配置

系统自动检测RF工作模式：
- **脉冲模式** (`pulse_cw=1`)：使用脉冲Drive PV，控制脉冲宽度
- **连续波模式** (`pulse_cw=0`)：使用CW Drive PV

### 阶段3：RF启动

RF系统启动步骤：
1. 打开RF (`RFOn=1`)
2. 设置初始Drive值
3. 启动频率扫描和跟踪 (`sweep=1`, `tracking=1`)
4. 验证RF状态（最多重试3次）
5. 若启动失败，自动复位Interlock故障后重试

### 阶段4：功率调节 (ADJUSTING_POWER)

这是核心循环状态，持续调节功率直到达标：

**功率调节逻辑**（源码：`rfq/controllers/power.py`）：
1. 读取当前功率和Drive值
2. 计算误差 = 当前功率 - 目标功率
3. 根据误差大小选择步长：
   - 误差 ≥ 大容差：使用大步长 (`drive_step1`)
   - 误差 < 大容差：使用小步长 (`drive_step2`)
4. 调整Drive值（功率低了增加Drive，高了减少Drive）
5. 等待2秒让Drive响应
6. 功率达标条件：`|误差| < 小容差`

### 阶段5：真空监测 (WAITING_VACUUM)

在功率调节和展脉宽过程中持续监测真空：
- 监听8个真空PV (`RFQ:Vac1` ~ `RFQ:Vac8`)
- 真空阈值：5.0×10⁻⁵ Pa
- 真空超标时暂停老练，等待恢复
- 恢复后自动返回功率调节状态

### 阶段6：脉冲展宽 (EXPANDING_PULSE)

当功率达标且为脉冲模式时，进入展脉宽流程：

**展宽逻辑**（源码：`rfq/controllers/pulse.py`）：
1. 等待 `pulse_wait` 秒（每次展宽前的稳定时间）
2. 将脉宽增加 `pulse_step` ms
3. 脉宽达标条件：`当前脉宽 ≥ 终止脉宽`
4. 展宽完成后，等待 `AutoC_PowerWaitTime` 秒，然后进入调功率

**可选模式**：
- **降功率模式**：展脉宽前先将Drive降至初始值（缓降保护）
- **直接展宽模式**：不降功率，直接展宽

### 阶段7：多目标功率切换

系统支持多目标功率列表逐个完成：
1. 当前目标功率达标 + 脉宽达标后
2. 若还有下一个目标 → 切换到下一个功率目标
3. 恢复初始脉宽，重新展脉宽
4. 所有目标都完成后 → 老练完成

---

## 三、故障处理机制

### 故障类型（源码：`rfq/controllers/fault.py`）

| 故障类型 | PV名称 | 说明 |
|---------|--------|------|
| Arc | `ArcStatus_Rd` | 打火故障 |
| VacInterlock | `InterlockStatus_Rd` | 真空联锁 |
| Interlock2 | `InterlockStatus2_Rd` | 二级联锁 |
| DI4 | `di4` | 数字输入4 |

### 故障处理流程

1. **故障检测**：通过EPICS callback实时监听故障PV
2. **故障计数**：每次故障累加计数
3. **故障复位**（所有故障均执行）：
   - 先执行VacReset（真空复位）
   - 依次复位：ResetInterlock → ResetPWFaultStat1 → ResetPWFaultStat2
   - 每个复位脉冲保持1秒后回弹
4. **状态恢复**：
   - 故障复位在后台线程完成后，主循环检测到 `RFOn=0` 自动触发 Reset，回到IDLE重启RF
   - 故障次数 ≥ 最大限制(20次) → 停止复位，进入ERROR状态

### Trip后处理 (Reset触发)

Trip（突发故障）后，Reset操作会：
1. 将脉宽降低 `pulse_drop` 值（默认20ms）
2. 最低降至原始初始脉宽
3. 重新初始化监听器
4. 返回IDLE状态

---

## 四、主循环流程图

```
开始
  ↓
[IDLE] 等待 start=1
  ↓
[INITIALIZING]
  ├→ 加载参数 ✓
  ├→ 配置RF模式 ✓
  └→ 启动RF ✓
  ↓ (成功)
[ADJUSTING_POWER]
  ├→ 检查真空 ─┐
  │  ↓ 不OK   │ OK
  │ [WAITING_VACUUM] ─→ 返回
  ↓
  ├→ 调节功率 ─→ 达标？
  │   ↓ 否
  │  继续调节 (loop)
  │   ↓ 是
  └→ 功率达标？
      ↓ 脉冲模式
    [EXPANDING_PULSE]
      ├→ 等待稳定时间
      ├→ 检查真空
      ├→ 展宽脉宽
      └→ 脉宽达标？
          ├─ 否 → 等待后 → [ADJUSTING_POWER]（继续调功率，再展下一步）
          └─ 是 → 还有下一目标？
                    ├─ 是 → 切换目标，恢复初始脉宽 → [ADJUSTING_POWER]
                    └─ 否 → [COMPLETED]

故障/RF关闭 → Reset到IDLE
故障超限 → [ERROR]
用户停止 → [STOPPED]
Reset信号 → 重置到IDLE
```

---

## 五、关键配置参数

所有参数通过EPICS PV实时读取，支持热修改：

| 参数 | PV名称 | 说明 |
|------|--------|------|
| 目标功率列表 | `AutoC_PowerTargets` | Waveform，多个功率目标 |
| 初始Drive | `AutoC_InitDrive` | RF启动Drive值 |
| 起始脉宽 | `AutoC_PulseStart` | 初始脉冲宽度 (ms) |
| 终止脉宽 | `AutoC_PulseEnd` | 目标脉冲宽度 (ms) |
| 脉宽步长 | `AutoC_PulseStep` | 每次展宽增量 (ms) |
| 稳定等待 | `AutoC_PulseWaitTime` | 功率达标后、展脉宽前的等待时间 (s) |
| 功率等待 | `AutoC_PowerWaitTime` | 展脉宽后、重新调功率前的等待时间 (s) |
| Drive大步 | `AutoC_DriveStep1` | 大误差时调节步长 |
| Drive小步 | `AutoC_DriveStep2` | 小误差时调节步长 |
| 大容差 | `AutoC_MarginLarge` | 大步长阈值 |
| 小容差 | `AutoC_MarginSmall` | 功率达标阈值 |
| 脉宽下降 | `AutoC_PulseDrop` | Trip后脉宽降幅 |

---

## 六、状态转换规则

| 触发条件 | 转换行为 |
|---------|---------|
| `start=0` 且在活动状态 | 保存当前状态 → PAUSED |
| `start=1` 从PAUSED恢复 | 重新加载参数 → 恢复保存的状态 |
| `reset=1` | 执行Reset，复位到IDLE |
| RF关闭 + 故障未超限 | 记录故障 → Reset到IDLE |
| RF关闭 + 故障超限 | → ERROR |
| 故障次数≥20 | → ERROR |
| 迭代次数≥1000 | → ERROR |
| 所有目标完成 | → COMPLETED |

---

## 七、系统特点

1. **状态机模式**：清晰的状态定义和转换逻辑
2. **事件驱动**：真空和故障使用EPICS callback实时监听
3. **多目标支持**：可一次配置多个功率目标自动切换
4. **容错机制**：故障自动复位 + Trip后脉宽缓降
5. **热修改**：所有控制参数通过PV实时读取，支持运行中调整
6. **日志完善**：详细的状态转换和参数变化记录

---

## 八、源码结构

```
AutoConditioning/
├── main.py                      # 主程序入口
├── config.yaml                  # 配置文件
├── rfq/
│   ├── core/
│   │   ├── controller.py       # 主控制器（状态机）
│   │   ├── state.py            # 状态定义
│   │   └── config.py           # 配置加载
│   ├── controllers/
│   │   ├── power.py            # 功率控制器
│   │   ├── pulse.py            # 脉冲控制器
│   │   ├── fault.py            # 故障处理器
│   │   └── vacuum.py           # 真空检测器
│   └── utils/
│       └── pv_manager.py        # PV管理器
└── tests/                       # 测试文件（不含老练流程）
```

---

## 九、使用方法

1. 通过EPICS PV设置目标功率、初始Drive、脉宽参数等（绝大多数控制参数均通过PV实时读取，`config.yaml` 仅定义PV名称和极少数默认值）
2. 运行：`python main.py`
3. 执行：`caput RFQ:LLRF:Con01:AutoC_Start 1` 启动老练
4. 按 `Ctrl+C` 可随时停止

---

*文档生成时间：2025-11*

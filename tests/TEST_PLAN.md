# RFQ 自动老练系统测试计划

**文档版本：** v1.0  
**日期：** 2026-03-31  
**适用版本：** AutoConditioning (branch: PV_mode)

---

## 目录

1. [测试环境说明](#1-测试环境说明)
2. [单元测试](#2-单元测试)
3. [集成测试（基于 sim_ioc）](#3-集成测试基于-sim_ioc)
4. [边界条件与异常测试](#4-边界条件与异常测试)
5. [上线前稳定性测试](#5-上线前稳定性测试)
6. [sim_ioc 局限与扩展需求](#6-sim_ioc-局限与扩展需求)
7. [测试执行检查清单](#7-测试执行检查清单)

---

## 1. 测试环境说明

### 1.1 依赖

| 组件 | 说明 |
|------|------|
| `caproto` | 运行 sim_ioc 的纯 Python EPICS IOC 框架 |
| `pyepics` | 控制器与 PV 通信 |
| `pytest` | 单元测试框架 |
| `pytest-asyncio` | 异步测试支持（用于 sim_ioc 相关测试） |

### 1.2 仿真 IOC 的功率模型

sim_ioc 采用简化的线性功率模型（每 0.1 s 更新）：

```
RF 开启：稳态功率 = Drive × 0.1  (kW)
RF 关闭：功率指数衰减至 0
```

Drive=100 对应 10 kW，Drive=200 对应 20 kW，Drive=300 对应 30 kW。

`pulse_cw=1` 使用 `pulse_drive`，`pulse_cw=0` 使用 `cw_drive`。

### 1.3 启动方式

```bash
# 终端 1：启动仿真 IOC
python tests/sim_ioc.py

# 终端 2：启动控制器（连接 sim_ioc）
python main.py

# 终端 3（可选）：手动注入故障或查询 PV
caproto-put RFQ:SIM:TriggerArc 1
caproto-get RFQ:LLRF:Con01_RFIn03:Power
```

---

## 2. 单元测试

> **当前状态：全部缺失，需编写。**  
> 以下每个测试项均对应一个具体的类/方法，可用 mock PVManager 隔离硬件依赖。

### 2.1 PowerController（`rfq/controllers/power.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-P-01 | 功率在小裕度内 | `current_power=10.0`, `target=10.0`, `margin_small=1.0` | 返回 `(True, ...)`, Drive 不变 |
| U-P-02 | 功率偏低，大误差 | `current_power=5.0`, `target=10.0`, `margin_large=3.0` | 使用 `drive_step1` 增大 Drive |
| U-P-03 | 功率偏低，小误差 | `current_power=9.0`, `target=10.0`, `margin_large=3.0` | 使用 `drive_step2` 增大 Drive |
| U-P-04 | 功率偏高，大误差 | `current_power=15.0`, `target=10.0`, `margin_large=3.0` | 使用 `drive_step1` 减小 Drive |
| U-P-05 | iteration 计数 | 连续调用 adjust() | 每次调用 `iteration_count` 加 1 |
| U-P-06 | Drive 下限保护 | Drive 已为 0，功率仍偏高 | Drive 不变为负数，返回调整失败信息 |

### 2.2 PulseController（`rfq/controllers/pulse.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-PL-01 | 脉宽已达 pulse_end | `current_pulse=110ms`, `pulse_end=110ms` | 返回 `(True, ...)` |
| U-PL-02 | 正常展宽 | `current_pulse=100ms`, `pulse_end=110ms`, `pulse_step=2ms` | 写入 102ms，返回 `(False, ...)` |
| U-PL-03 | 展宽模式：不降功率 | `reduce_power_before_expand=False` | 不修改 Drive，直接写新脉宽 |
| U-PL-04 | 展宽模式：先降功率 | `reduce_power_before_expand=True` | 先将 Drive 写为 init_drive，再写新脉宽 |
| U-PL-05 | 脉宽超过 pulse_end | `current_pulse=115ms`, `pulse_end=110ms` | 返回 `(True, ...)` |
| U-PL-06 | 单位换算正确 | PV 读取单位为秒（0.1 s = 100 ms） | 内部换算后写入 ms，不出现量级错误 |

### 2.3 FaultHandler（`rfq/controllers/fault.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-F-01 | fault_count 累加 | 连续触发 3 次故障 | `get_fault_count()` 返回 3 |
| U-F-02 | 超限标志 | `max_faults=3`，触发第 3 次故障 | `is_fault_exceeded()` 返回 True |
| U-F-03 | 未超限时不设标志 | `max_faults=5`，触发 4 次 | `is_fault_exceeded()` 返回 False |
| U-F-04 | reset_fault_count | 触发 3 次后调用 reset | `get_fault_count()` 返回 0 |
| U-F-05 | 故障恢复步骤顺序 | 模拟 arc 故障 | 按序执行：VacReset → ResetInterlock → ResetPWFaultStat1 → ResetPWFaultStat2 |
| U-F-06 | 恢复后验证 PV | 故障 PV 恢复为 1 后 | `_check_fault_status()` 日志显示故障状态均恢复 |
| U-F-07 | 恢复失败处理 | 复位后故障 PV 仍为 0 | 记录错误，不进入死循环 |
| U-F-08 | cleanup 取消回调 | 调用 cleanup() | 回调不再响应后续故障注入 |

### 2.4 VacuumChecker（`rfq/controllers/vacuum.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-V-01 | 初始状态 fail-safe | 未收到任何回调 | `is_vacuum_ok()` 返回 `(False, ...)` |
| U-V-02 | 全部正常 | 8 路 PV 均为 1e-6 Pa | 返回 `(True, 1e-6, ...)` |
| U-V-03 | 单路超标 | Vac3 = 1e-3 Pa，其余正常 | 返回 `(False, 1e-3, 'RFQ:Vac3')` |
| U-V-04 | 取最差值 | Vac2=3e-5, Vac6=6e-5, 其余正常 | 返回 `(False, 6e-5, 'RFQ:Vac6')` |
| U-V-05 | 恢复正常 | 超标后降回 1e-6 Pa | 返回 `(True, ...)` |
| U-V-06 | 阈值边界 | 压强恰好等于 threshold（5e-5） | 视为超标（`pressure >= threshold`） |

### 2.5 RFQController.reset()（`rfq/core/controller.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-R-01 | 手动 reset（clear_faults=True） | 故障计数=5，当前目标=第2段 | fault_count 清零，回到第1段功率，pulse_start 恢复 original |
| U-R-02 | 自动恢复 reset（clear_faults=False） | 故障计数=3，当前目标=第2段 | fault_count 保持 3，保持当前目标，pulse_start 减少 pulse_drop |
| U-R-03 | pulse_start 下限 | pulse_start 已很小，pulse_drop 大 | pulse_start 不低于 `original_pulse_start` |
| U-R-04 | reset 重建子控制器 | 调用 reset 后 | FaultHandler 和 VacuumChecker 为新实例（旧回调已 cleanup） |

### 2.6 Config（`rfq/core/config.py`）

| 编号 | 测试名称 | 输入条件 | 预期结果 |
|------|---------|---------|---------|
| U-C-01 | 嵌套路径访问 | `config.get('loop', 'max_faults')` | 正确返回值 |
| U-C-02 | 缺失路径默认值 | `config.get('loop', 'not_exists', default=123)` | 返回 `123` |
| U-C-03 | PV 名称查找 | `config.get_pv('rf.pulse_drive')` | 返回 `'RFQ:LLRF:Con01:AmpPulseDrive_Set'` |
| U-C-04 | reload 生效 | 修改配置文件后调用 `config.reload()` | 后续 `config.get(...)` 返回新值 |

> 注：PV 读取成功/失败及回退默认值属于 `RFQController._load_parameters()`、`PowerController`、`PulseController` 的测试范围，不属于 `Config` 类本身。

---

## 3. 集成测试（基于 sim_ioc）

> **前提：** 运行 `python tests/sim_ioc.py`，等待 IOC 就绪后再启动控制器。

### 3.1 正常流程（Happy Path）

#### TC-INT-01：完整三段功率老练

**前置条件：**
- sim_ioc 运行，PV 初始值：`AutoC_PowerTargets=[10,20,30,0,...]`, `pulse_start=100ms`, `pulse_end=110ms`, `pulse_step=10ms`
- `pulse_cw=1`（脉冲模式），`init_drive=100`

**操作步骤：**
1. 写入 `AutoC_Start=1`
2. 等待系统运行

**验证点：**

| 步骤 | 观测 PV | 预期值/行为 |
|------|---------|-----------|
| 初始化 | `AutoC_Status` | 先出现 `INITIALIZING`，后出现 `ADJUSTING_POWER` |
| | `rf_on` | 置为 1 |
| | `freq_sweep`, `freq_tracking` | 置为 1 |
| 第1段调功率 | `AutoC_CurrentTargetPower` | 10.0 |
| | `Power` | 趋近 10 kW（±1 kW 裕度内） |
| 第1段展脉宽 | `AutoC_Status` | 出现 `EXPANDING_PULSE` |
| | `RFPulseOnTime_Set` | 从 100ms 展宽至 110ms |
| 第2段调功率 | `AutoC_CurrentTargetPower` | 20.0 |
| | `Power` | 趋近 20 kW |
| 第3段展脉宽完成 | `AutoC_Status` | 最终出现 `COMPLETED` |
| 完成后 | `AutoC_Start` | 自动置为 0 |
| | `rf_on` | 仍为 1（完成后不关闭 RF） |

---

#### TC-INT-02：CW 模式完整流程

**前置条件：** `pulse_cw=0`（CW 模式）

**验证点：**
- 初始化时使用 `cw_drive` PV（而非 `pulse_drive`）
- `RFPulseOnTime_Set` 不被写入
- 功率响应基于 `cw_drive` 计算

---

### 3.2 暂停与恢复

#### TC-INT-03：调功率过程中暂停

**操作步骤：**
1. 启动老练，等待进入 `ADJUSTING_POWER`
2. 写入 `AutoC_Start=0`（暂停信号）
3. 等待 5 秒
4. 写入 `AutoC_Start=1`（恢复）

**验证点：**

| 时机 | 预期行为 |
|------|---------|
| 暂停后 | `AutoC_Status` 变为 `PAUSED` |
| 暂停期间 | `rf_on` 保持为 1，功率维持，Drive 不变 |
| 恢复后 | 从暂停前的状态继续，fault_count 不清零 |

---

#### TC-INT-04：展脉宽过程中暂停

**操作步骤：** 同上，但在 `EXPANDING_PULSE` 阶段暂停

**验证点：**
- 暂停后脉宽不再增加
- 恢复后继续从当前脉宽展宽，不重置到 pulse_start

---

### 3.3 用户暂停与复位

#### TC-INT-05：正常运行中用户暂停并复位

**操作步骤：**
1. 启动老练，等待进入 `ADJUSTING_POWER`
2. 写入 `AutoC_Start=0`（暂停信号）
3. 确认进入 `PAUSED` 后，写入 `AutoC_Reset=1`（手动复位）

**验证点：**

| 预期行为 |
|---------|
| 写入 `AutoC_Start=0` 后，`AutoC_Status` 变为 `PAUSED` |
| 写入 `AutoC_Reset=1` 后，状态回到 `IDLE`，fault_count 清零 |
| 重新写 `AutoC_Start=1` 后，可重新启动 |

> 说明：当前实现中，运行态“停止并关RF/Drive归零”不由 `AutoC_Reset` 直接触发。

---

### 3.4 故障处理

#### TC-INT-06：单次 Arc 故障自动恢复

**操作步骤：**
1. 启动老练，等待进入 `ADJUSTING_POWER`
2. 写入 `RFQ:SIM:TriggerArc=1`（注入弧光故障）
3. 等待恢复

**验证点：**

| 时机 | 预期行为 |
|------|---------|
| 故障触发后 | `ArcStatus_Rd` 变为 0，`rf_on` 变为 0 |
| 恢复过程中 | 控制器执行：VacReset → ResetInterlock → ResetPWFaultStat1 → ResetPWFaultStat2 |
| 恢复完成后 | `ArcStatus_Rd` 回到 1，RF 重新启动，功率恢复 |
| fault_count | 较故障前增加 1 |
| pulse_start | 较故障前降低 `pulse_drop`（ms） |

---

#### TC-INT-07：单次 VacInterlock 故障自动恢复

**操作步骤：**
1. 写入 `RFQ:SIM:TriggerInterlock=1`

**验证点：** 同 TC-INT-06，故障 PV 为 `InterlockStatus_Rd`

---

#### TC-INT-08：故障次数超限进入 ERROR

**操作步骤：**
1. 将 `config.yaml` 中 `loop.max_faults` 修改为 `3`，重启控制器
2. 连续触发 3 次 Arc 故障，每次等待恢复完成

**验证点：**

| 预期行为 |
|---------|
| 第 3 次故障后 `AutoC_Status` 变为 `ERROR` |
| `rf_on` 置为 0 |
| Drive 归零 |
| 系统不自动恢复，等待用户手动 Reset |

---

#### TC-INT-09：ERROR 状态后手动复位

**前置条件：** TC-INT-08 完成后处于 ERROR 状态

**操作步骤：**
1. 写入 `AutoC_Reset=1`

**验证点：**

| 预期行为 |
|---------|
| 状态变为 `IDLE` |
| fault_count 清零 |
| pulse_start 恢复为 `original_pulse_start` |
| 可重新写 `AutoC_Start=1` 启动新的老练 |

---

### 3.5 真空超标处理

#### TC-INT-10：运行中真空超标

**操作步骤：**
1. 启动老练，等待进入 `ADJUSTING_POWER`
2. 用 caproto-put 将 `RFQ:Vac3` 写为 `1e-3`（超过阈值 5e-5）

**验证点：**

| 时机 | 预期行为 |
|------|---------|
| 超标后 | `AutoC_Status` 变为 `WAITING_VACUUM` |
| 等待期间 | Drive 不调整，RF 保持（不因真空超标关闭 RF） |
| 恢复后 | 将 `RFQ:Vac3` 写回 `1e-6`，状态回到 `ADJUSTING_POWER` |

---

#### TC-INT-11：多路真空超标，取最差值

**操作步骤：**
1. 将 `RFQ:Vac2=6e-5`，`RFQ:Vac6=8e-5`（阈值 `5e-5`）

**验证点：**
- `is_vacuum_ok()` 返回 False，worst_pv 为 `RFQ:Vac6`，worst_value ≈ 8e-5
- 恢复时，仅将 Vac6 降回正常不够（Vac2 仍超阈值），需要两路都恢复到阈值以下

---

### 3.6 RF 启动重试

#### TC-INT-12：RF 启动后 rf_on 未响应，触发重试

> **注意：** 此测试需要扩展 sim_ioc 后才能可靠执行（见 [第6节](#6-sim_ioc-局限与扩展需求)）

**操作步骤：**
1. 在 sim_ioc 中启用 `block_rf_on` 注入开关（暂不响应 rf_on=1）
2. 写入 `AutoC_Start=1`

**验证点：**

| 预期行为 |
|---------|
| 控制器尝试 rf_on=1，验证失败后执行故障复位 |
| 最多重试 `max_retry`（默认 5）次 |
| 超过重试次数后进入 `ERROR` |
| 日志中出现每次重试的记录 |

---

### 3.7 多目标边界

#### TC-INT-13：第2段目标功率已满足时跳过调功率

**前置条件：** 将 `AutoC_PowerTargets=[10, 10, 30, 0, ...]`（两段相同目标）

**验证点：**
- 完成第1段后，进入第2段时功率已满足条件
- 应直接进入 `EXPANDING_PULSE`，而不是一直调 Drive

---

#### TC-INT-14：脉宽已在 pulse_end 时跳过展宽

**前置条件：** 设置 `AutoC_PulseStart=110ms`，`AutoC_PulseEnd=110ms`

**验证点：**
- `EXPANDING_PULSE` 状态应立即判定完成，不写入 PV，进入下一段

---

## 4. 边界条件与异常测试

### 4.1 配置参数异常

| 编号 | 场景 | 预期结果 |
|------|------|---------|
| E-01 | `AutoC_PowerTargets` 全为 0 | 控制器检测到无有效目标，进入 ERROR 或不启动，日志报错 |
| E-02 | `pulse_start > pulse_end` | 展宽时立即判定完成，不循环 |
| E-03 | `pulse_step = 0` | 当前实现不会自动修正该参数；测试应验证系统不崩溃并记录风险（建议后续增加参数校验） |
| E-04 | `max_faults = 0` | 首次故障即进入 ERROR |
| E-05 | 所有 PV 读取失败 | 关键 PV（如 power_targets/init_drive）读取失败时初始化失败并进入 ERROR |

### 4.2 运行时参数变更

| 编号 | 场景 | 预期结果 |
|------|------|---------|
| E-06 | PAUSED 期间修改 `AutoC_PulseEnd` | 恢复后使用新的 pulse_end 值 |
| E-07 | PAUSED 期间修改 `AutoC_PowerTargets` | 恢复后使用新的目标功率（需确认是否支持） |

### 4.3 字符串截断（PVManager.safe_status）

| 编号 | 场景 | 预期结果 |
|------|------|---------|
| E-08 | 超长中文状态字符串 | 截断不破坏 UTF-8 多字节字符边界 |
| E-09 | 混合中英文长字符串 | 截断后仍为合法字符串 |

---

## 5. 上线前稳定性测试

> 这些测试需要较长运行时间，建议在正式上线前一周完成。

### 5.1 长时间运行测试

**目标：** 检测内存泄漏、线程泄漏、PV 回调未清理等问题

**方法：**
1. 运行 sim_ioc，设置参数使老练过程缩短（例如 pulse_step=5ms，pulse_end=120ms）
2. 完整运行 3 段功率老练至 COMPLETED
3. 手动 Reset 后重新启动，重复 10 次

**监控指标：**

| 指标 | 检查方法 | 通过标准 |
|------|---------|---------|
| 内存占用 | 运行前后 `psutil.Process.memory_info()` | 不持续增长 |
| 线程数量 | `threading.active_count()` | 每次 reset 后回到初始线程数（±2） |
| PV 回调数量 | FaultHandler/VacuumChecker 的 callbacks 列表 | cleanup() 后为空 |
| 日志大小 | 查看 `rfq_auto_conditioning.log` | 无异常重复错误 |

---

### 5.2 故障-恢复循环压力测试

**目标：** 验证多次故障往复后 fault_count 和状态机保持一致

**方法：**
1. 设置 `max_faults=50`
2. 启动老练后，每 30 秒注入一次 Arc 故障
3. 等待每次故障自动恢复后再注入下一次
4. 重复 20 次

**验证点：**

| 指标 | 预期 |
|------|------|
| 每次故障后 fault_count 单调增加 | fault_count 累计达到 20 |
| pulse_start 单调递减（每次故障后减少 pulse_drop） | 最终 pulse_start 降低约 20×pulse_drop |
| 系统不死锁、不崩溃 | 全程稳定运行 |

---

### 5.3 并发故障注入测试

**目标：** 验证同时触发多种故障时系统不死锁

**方法：**
1. 在 1 秒内同时写入：
   ```bash
   caproto-put RFQ:SIM:TriggerArc 1
   caproto-put RFQ:SIM:TriggerInterlock 1
   ```
2. 等待恢复

**验证点：**
- 两个故障回调均被处理
- fault_count 合理增加（1 或 2，取决于实现）
- 不出现死锁或状态不一致

---

### 5.4 日志完整性验证

**目标：** 确保关键操作全部有日志记录，便于事后追溯

运行完整老练后，检查 `rfq_auto_conditioning.log` 是否包含：

| 必须出现的日志关键字 |
|-------------------|
| 每次状态转换（状态名 + 数字代码） |
| RF 启动成功/失败 |
| 每次功率调整（Drive 值变化） |
| 每次故障触发（类型 + fault_count） |
| 每次故障恢复步骤 |
| 每次脉宽增加（新值） |
| 老练完成统计信息 |

---

## 6. sim_ioc 局限与扩展需求

当前 sim_ioc 存在以下不足，建议在测试前扩展：

### 6.1 缺少真空注入接口

**当前状态：** 真空 PV 只能通过 `caproto-put RFQ:Vac3 1e-3` 手动设置。  
**建议扩展：** 增加 `RFQ:SIM:TriggerVacuum` PV，写入后自动将指定 Vac PV 升至超标值，便于自动化测试。

```
trigger_vacuum = pvproperty(value=0, dtype=int, name='RFQ:SIM:TriggerVacuum')
# 写 1 → 将 vac3 升至 1e-3，写 0 → 恢复 1e-6
```

### 6.2 缺少 RF 启动失败模拟

**当前状态：** sim_ioc 的 rf_on PV 被写入后立即响应，无法测试 RF 启动失败重试逻辑。  
**建议扩展：** 增加 `RFQ:SIM:BlockRFOn` 开关。当该开关为 1 时，rf_on 写入后不更新（返回 0），模拟 RF 系统无响应。

```
block_rf_on = pvproperty(value=0, dtype=int, name='RFQ:SIM:BlockRFOn')
```

---

## 7. 测试执行检查清单

在正式上线前，确认以下所有项目已完成：

### 单元测试

- [ ] U-P 系列（PowerController，6 项）
- [ ] U-PL 系列（PulseController，6 项）
- [ ] U-F 系列（FaultHandler，8 项）
- [ ] U-V 系列（VacuumChecker，6 项）
- [ ] U-R 系列（reset() 逻辑，4 项）
- [ ] U-C 系列（Config 访问与 reload 逻辑，4 项）

### 集成测试

- [ ] TC-INT-01：完整三段功率老练（Happy Path）
- [ ] TC-INT-02：CW 模式
- [ ] TC-INT-03：调功率中暂停/恢复
- [ ] TC-INT-04：展脉宽中暂停/恢复
- [ ] TC-INT-05：用户暂停并复位
- [ ] TC-INT-06：Arc 故障自动恢复
- [ ] TC-INT-07：VacInterlock 故障自动恢复
- [ ] TC-INT-08：故障次数超限进入 ERROR
- [ ] TC-INT-09：ERROR 后手动复位
- [ ] TC-INT-10：真空超标 → 等待 → 恢复
- [ ] TC-INT-11：多路真空超标取最差值
- [ ] TC-INT-13：第2段目标功率已满足时跳过
- [ ] TC-INT-14：脉宽已在 pulse_end 时跳过展宽

### 边界条件测试

- [ ] E-01 至 E-09

### 稳定性测试

- [ ] 长时间运行（10 次完整循环）
- [ ] 故障-恢复压力测试（20 次故障循环）
- [ ] 并发故障注入
- [ ] 日志完整性验证

### sim_ioc 扩展（建议先完成再做 TC-INT-12）

- [ ] 添加真空注入接口（`RFQ:SIM:TriggerVacuum`）
- [ ] 添加 RF 启动失败模拟（`RFQ:SIM:BlockRFOn`）

---

*文档维护：每完成一个测试项在检查清单中打勾，发现问题在对应用例下添加"问题记录"小节。*

# 稳定建场（STABLE_BUILDING）模块逻辑说明

## 1. 目标

在 RF 启动后的早期阶段，通过 detuning 判据分步增加 Drive，将腔体功率提升到 `stable_power`，然后再进入常规调功率流程。

---

## 2. 新增 PV 清单

| 逻辑键                    | 含义                      | 方向 | 备注                          |
| ------------------------- | ------------------------- | ---- | ----------------------------- |
| `control.stable_step`   | 稳定建场阶段 Drive 步长   | R/W  | 每次满足条件时增加的 Drive 值 |
| `control.stable_power`  | 稳定建场目标功率（kW）    | R/W  | 达到该值视为建场完成          |
| `rf.detuning`           | 当前 detuning 读数        | R    | 来自低电平或频率相关测量      |
| `control.stable_margin` | detuning 判稳阈值（死区） | R/W  | 判据：`                       |

说明：`timeout_seconds` 不发布 PV，直接放 `config.yaml`。

---

## 3. 配置项（config.yaml）

当前代码使用 `loop` 下的扁平键：

- `stable_timeout_seconds`: 稳定建场阶段最大时长（建议默认 60s）
- `stable_detuning_cycles`: `detuning` 连续稳定的主循环周期数（建议默认 3）

---

## 4. 状态流程

### INITIALIZING 阶段（`rf_manager.startup()`）

按以下顺序执行，频率初始化在 `init_drive` 写入之前：

1. 写入起始频率 `rf.freq_start`（由 `config.yaml` 的 `loop.rf_startup.start_frequency` 配置，未配置则跳过）
2. `pulse_drive` / `cw_drive` 清零
3. 打开 RF（`rf_on=1`），验证 RF 状态
4. 写入 `init_drive`
5. 打开 `sweep=1` 和 `tracking=1`

完成后转入 `STABLE_BUILDING`。

### STABLE_BUILDING 阶段

1. 通用条件检查（暂停、真空、RF、故障计数）
2. 读取 `rf.power`，若已 `>= stable_power`：跳过建场，直接进入 `ADJUSTING_POWER`
3. 建场循环：
   - 读取 `rf.detuning_error`、`control.stable_margin`、`control.stable_step`
   - 若 `|detuning| <= stable_margin`，稳定计数 `+1`
   - 若稳定计数达到 `stable_detuning_cycles`，则 `drive += stable_step`
   - 若任一周期 `|detuning| > stable_margin`，稳定计数清零
   - 读取 `rf.power`，若 `>= stable_power`：建场完成，进入 `ADJUSTING_POWER`
   - 否则继续循环
4. 超时：若持续时间超过 `stable_timeout_seconds`，进入 `ERROR`

---

## 5. 通用条件复用

暂停、RF 掉线、真空联锁、故障计数等，沿用现有通用检查链路（`_check_common_conditions()`）。

---

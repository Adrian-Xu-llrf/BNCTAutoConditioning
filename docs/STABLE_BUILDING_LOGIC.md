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

建议放在 `loop.stable_field` 下：

- `timeout_seconds`: 稳定建场阶段最大时长（建议默认 60s）
- `wait_after_tracking_seconds`: 打开扫频跟踪后的等待时间(默认5s)

---

## 4. 状态流程

1. `INITIALIZING` 阶段完成以下动作：
   - 设置 `init_drive`
   - 打开 `sweep=1`
   - 打开 `tracking=1`
2. 等待  `wait_after_tracking_seconds`
3. 读取 `rf.power` 与 `stable_power`
4. 分支：
   - 若 `rf.power >= stable_power`：跳过建场，直接进入 `ADJUSTING_POWER`
   - 若 `rf.power < stable_power`：进入 `STABLE_BUILDING`
5. `STABLE_BUILDING` 循环：
   - 读取 `rf.detuning`、`control.stable_margin`、`control.stable_step`
   - 若 `|detuning| <= stable_margin`，则 `drive += stable_step`
   - 再次读取 `rf.power`
   - 若 `rf.power >= stable_power`，建场完成，进入 `ADJUSTING_POWER`
   - 否则继续循环
6. 超时判断：
   - 若 `STABLE_BUILDING` 持续时间超过 `timeout_seconds`，进入 `ERROR`

---

1. 通用条件复用：

- 暂停、RF 掉线、真空联锁、故障计数等，沿用现有通用检查链路。

---

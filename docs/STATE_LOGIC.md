# 各状态内部逻辑详解

各状态对应 `controller.py` 中的 `_handle_xxx()` 方法，每次主循环迭代调用一次。

---

## IDLE（空闲等待）

**进入条件**：系统启动初始状态，或任意状态执行 `reset()` 后

**退出条件**：检测到 `control.start == 1` → 转 `INITIALIZING`

**逻辑**：轮询 `start` PV，每次循环固定 sleep 1 秒（不使用 `_sleep_loop`，避免因 config 未加载而出错）。

---

## INITIALIZING（初始化）

**进入条件**：`start=1` 信号触发

**退出条件**：
- 成功 → `STABLE_BUILDING`（待实现，当前直接到 `ADJUSTING_POWER`）
- 任意步骤失败 → `ERROR`
- 通用条件触发 → 对应状态

**逻辑（三步）**：

```
1. PV 健康检查：pv_manager.check_all_connected()
   ↓ 失败 → ERROR（PV连接失败）

2. 参数加载：param_loader.load(params, is_auto_recovery=self._is_auto_recovery)
   - is_auto_recovery=True 时：保留当前 pulse_start，不从 PV 重新读取
   - is_auto_recovery=False 时：从 PV 加载全部参数，保存 original_pulse_start
   ↓ 失败 → ERROR（参数加载失败）

3. RF 启动：rf_manager.setup_mode() + rf_manager.startup()
   - setup_mode：识别脉冲/CW模式，设置 current_drive_pv
   - startup：最多重试 max_retry 次，每次失败后执行 reset_all_faults()
   ↓ 失败 → ERROR（RF启动失败）
```

成功后：`_is_auto_recovery = False`，转目标状态。

---

## STABLE_BUILDING（稳定建场）

**当前状态**：已实现，使用 `detuning` 连续稳定判据门控 Drive 步进。

**设计逻辑**（见 `docs/STABLE_BUILDING_LOGIC.md`）：

```
1. 检查通用条件
2. 检查是否已跳过建场（rf.power >= stable_power → 直接转 ADJUSTING_POWER）
3. 建场循环：
   - 读取 rf.detuning_error 和 control.stable_margin
   - 若 |detuning| <= stable_margin：连续稳定计数 +1
   - 仅当连续稳定计数达到 stable_detuning_cycles 时：drive += stable_step
   - 若任一周期超出 stable_margin：连续稳定计数清零
   - 读取 rf.power
   - 若 rf.power >= stable_power → 转 ADJUSTING_POWER
4. 超时（> timeout_seconds）→ ERROR
```

连续稳定周期数来自 `config.yaml` 中的 `loop.stable_detuning_cycles`。

---

## ADJUSTING_POWER（调节功率）

**进入条件**：
- 来自 `INITIALIZING` / `STABLE_BUILDING`（正常流程）
- 来自 `WAITING_VACUUM`（真空恢复后）
- 来自 `EXPANDING_PULSE`（切换到下一功率目标后，带 `_wait_before_power=True`）

**退出条件**：
- 功率达标，脉冲模式 → `EXPANDING_PULSE`
- 功率达标，CW 模式 → `COMPLETED`
- `power_controller.fatal_error`（Drive 超限且功率为0）→ `ERROR`
- 通用条件触发 → 对应状态

**关键逻辑**：

**展脉宽后等待机制**（`_wait_before_power`）：

从 `EXPANDING_PULSE` 切换到下一功率目标时，设置 `_wait_before_power=True`。进入 `ADJUSTING_POWER` 后，先等待 `wait_before_expand` 秒（从 `state_enter_time` 计时），期间不调功率，等待结束后：
1. 清除 `_wait_before_power`
2. 若 `_need_reset_pulse=True`：将脉宽恢复到 `original_pulse_start`，清除标志

**功率调节算法**（`PowerController.adjust()`）：

```
error = current_power - target_power
if |error| < margin_small → 达标，返回 True
if |error| >= margin_large → 大步（drive_step1）
else → 小步（drive_step2）

error < 0（功率偏低）→ drive += step
error > 0（功率偏高）→ drive -= step

drive 不超过 AmpLimiter 上限
```

---

## WAITING_VACUUM（等待真空恢复）

**进入条件**：任意活动状态检测到真空超标

**退出条件**：真空恢复（`worst_vacuum < threshold`）→ **始终转 `ADJUSTING_POWER`**

**设计说明**：不记录来源状态，真空恢复后统一回到 `ADJUSTING_POWER`，重新验证功率后再决定下一步。这避免了从 `EXPANDING_PULSE` 来的情况下直接恢复展脉宽可能带来的功率不稳定。

**逻辑**：通用条件检查 → 轮询 `vacuum_checker.is_vacuum_ok()`（读取 callback 缓存值，不触发新的 PV 读取）→ 达标后转态。

---

## EXPANDING_PULSE（展宽脉冲）

**进入条件**：`ADJUSTING_POWER` 功率达标（脉冲模式）

**退出条件**：
- 当前脉宽 < 目标脉宽 且有下一功率目标 → `ADJUSTING_POWER`（带标志）
- 所有功率目标完成 → `COMPLETED`
- 通用条件触发 → 对应状态

**展宽前等待（`_pulse_step_start_time`）**：

每次展脉宽前等待 `wait_time` 秒，计时从 `_pulse_step_start_time` 开始：
- 初次进入状态：`_pulse_step_start_time = state_enter_time`
- 展宽一步完成后：`_pulse_step_start_time = time.time()`（重置，为下一步等待计时）
- 等待期间真空超标：直接转 `WAITING_VACUUM`，`_pulse_step_start_time` **不重置**（真空恢复后回到 `ADJUSTING_POWER`，而非继续展脉宽）

**展宽逻辑（`PulseController.expand()`）**：

```
current_ms = rf.pulse_time × 1000
if current_ms >= pulse_end → 已完成，返回 True

new_ms = min(current_ms + pulse_step, pulse_end)

if reduce_power_before_expand=True:
    缓慢降 Drive 到 init_drive（每步 drive_step1，sleep 1s）

写入 rf.pulse_time = new_ms / 1000
返回 False（未完成）
```

**多功率目标切换**：

`pulse_ok=True` 且还有下一目标时：
1. `target_index += 1`，更新 `target_power` 和 `current_target_power` PV
2. 重置 `power_controller.iteration_count`
3. 设置 `_need_reset_pulse=True`（等待结束后恢复脉宽）
4. 设置 `_wait_before_power=True`
5. 转 `ADJUSTING_POWER`

---

## PAUSED（暂停）

**进入条件**：活动状态下 `start=0`，同时保存 `state_before_pause`

**退出条件**：
- `start=1` → 恢复到 `state_before_pause`
- `reset=1` → `reset()` → `IDLE`

**恢复时的参数处理**：

`start=1` 检测到后，重载参数（`param_loader.load()`），但**保留当前 `pulse_start`**（不从 PV 重读），原因：暂停期间操作员可能修改了目标功率等参数，但脉宽是实际硬件当前状态，不应被 PV 设定值覆盖。

---

## COMPLETED（老练完成）

**进入条件**：所有功率目标完成

**一次性清理**（由 `terminal_cleaned` 保证只执行一次）：
1. 打印完成日志（总故障次数、总迭代次数）
2. 将 `control.start` 写 0
3. 调用 `fault_handler.cleanup()` 和 `vacuum_checker.cleanup()`（清除 callback）

之后轮询 `reset=1` 信号，触发 `reset()` 回到 `IDLE`。

---

## ERROR（错误）

**进入条件**：任意初始化失败、故障超限、Drive 超限且功率为0、非法状态转换等

**一次性清理**：
1. 记录 `error_message` 到日志
2. `rf_manager.shutdown()`（Drive 清零，关闭 RF）
3. 将 `control.start` 写 0
4. 调用 `fault_handler.cleanup()` 和 `vacuum_checker.cleanup()`

之后轮询 `reset=1` 信号。

---

## STOPPED（用户停止）

**进入条件**：非活动状态下 `start=0`（如 `INITIALIZING` 中用户取消）

**一次性清理**：
1. 记录停止日志
2. `rf_manager.shutdown()`

之后轮询 `reset=1` 信号。

---

## 终止状态一次性清理机制

`ERROR`、`STOPPED`、`COMPLETED` 使用 `_cleanup_terminal_state(state_name, cleanup_func)` 保证清理只执行一次：

```python
if state_name not in self.terminal_cleaned:
    cleanup_func()           # 各状态特有清理
    fault_handler.cleanup()  # 清除 callback
    vacuum_checker.cleanup() # 清除 callback
    terminal_cleaned[state_name] = True
```

`terminal_cleaned` 在 `reset()` 时被清空，下次进入终止状态时重新执行清理。

> **已知问题**：callback 清除后，`reset()` 不会重新注册，导致重新老练时监控失效。见 `docs/PROJECT_OPTIMIZATION_PLAN.md` 三.1。

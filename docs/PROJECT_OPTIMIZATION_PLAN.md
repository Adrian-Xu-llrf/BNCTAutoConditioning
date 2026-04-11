# 项目整体优化计划

> 基于 2026-04 回退后的代码状态（HEAD: 9150c06），不再采用 StateHandler 子类迁移方案。
> 架构整体合理，不做大规模重构，聚焦 bug 修复、新功能和少量代码改善。

---

## 一、P0 Bug 修复

### 1.1 sim_ioc.py vac7/vac8 引用不存在的属性

`sim_ioc.py:486` 的 `sim_vac_single` putter 引用了 `self.vac7` 和 `self.vac8`，但只定义了 vac1-vac6。

**修复**：将 targets 列表改为 `[self.vac1, ..., self.vac6]`（6个元素）。

### 1.2 日志 namer 硬编码年份

`main.py:42` 用 `parts[1].startswith('2026')` 判断日期后缀，2027年起失效。

**修复**：改为正则匹配 `r'\d{4}-\d{2}-\d{2}'`。

---

## 二、新功能：实现 STABLE_BUILDING 状态

### 现状

`state.py` 中已定义 `RFQState.STABLE_BUILDING = 18` 和合法转换关系，但 `controller.py` 的 `state_handlers` 映射表中没有这个状态，`_handle_stable_building()` 方法也不存在。`_handle_initializing()` 完成后直接跳到 `ADJUSTING_POWER`。

### 方案

1. 在 `controller.py` 中新增 `_handle_stable_building()` 方法，逻辑按 `docs/STABLE_BUILDING_LOGIC.md` 实现
2. 在 `state_handlers` 映射表中添加 `RFQState.STABLE_BUILDING: self._handle_stable_building`
3. 将 `STABLE_BUILDING` 加入 `active_states` 和 `states_need_rf` 集合
4. 在 `config.yaml` 的 `pv` 部分添加新 PV（`rf.detuning`, `control.stable_step`, `control.stable_power`, `control.stable_margin`）
5. 在 `config.yaml` 的 `loop` 部分添加 `stable_field.timeout_seconds` 和 `stable_field.wait_after_tracking_seconds`
6. 在 `sim_ioc.py` 中添加对应仿真 PV
7. 在 `pv_keys.py` 中添加新 PV 常量

详见 `docs/STABLE_BUILDING_LOGIC.md`。

---

## 三、逻辑 Bug 修复

### 3.1 终止状态 cleanup 后 callback 不会恢复

**问题**：`_cleanup_terminal_state()`（`controller.py:293`）调用 `fault_handler.cleanup()` 和 `vacuum_checker.cleanup()`，清除了所有 PV callback。但 `reset()` 后重新启动时（IDLE → INITIALIZING），**没有重新注册 callback**。

结果：ERROR/STOPPED → reset → 重新老练这条路上，`VacuumChecker` 使用的是 cleanup 前的缓存旧值，`FaultHandler` 不会再收到新故障通知，监控完全失效。

**修复方案**（二选一）：
- 在 `fault_handler` 和 `vacuum_checker` 中各自添加 `restart()` 方法重新注册 callback，在 `_handle_initializing()` 开始时调用
- 或者去掉 `_cleanup_terminal_state` 中对 `cleanup()` 的调用，仅在进程退出时清理（EPICS callback 本身是轻量的，不需要主动清理）

### 3.2 `_handle_adjusting_power` 重复检查真空

**问题**：`controller.py:455` 的 `_check_common_conditions()` 已包含真空检查，若不达标会直接跳转 `WAITING_VACUUM`。执行到第482行时真空必然达标，第482-488行的显式真空检查是**冗余代码**。

**修复**：删除 `_handle_adjusting_power` 中第482-488行的独立真空检查块。

### 3.3 `_handle_initializing` 中在 except 块内 import

**问题**：`controller.py:443` 在异常处理中执行 `import epics.ca`，若 import 本身失败会掩盖原始异常，导致调试困难。

**修复**：将 `import epics.ca` 移到文件顶部。

---

## 四、run() 主循环简化

### 现状

`controller.py:687-716` 的 `run()` 有三段逻辑：
1. 第695-704行：活动状态循环，调用 `handler()`
2. 第706-708行：到达终止状态后再调用一次 handler
3. 第710-715行：独立的终止状态等待循环，轮询 reset 信号

第2、3段与终止状态 handler 内部的 `_check_reset_signal()` + `_sleep(1)` 逻辑重复。

### 方案

统一为单循环，所有状态（包括终止状态）都走 handler：

```python
while True:
    handler = self.state_handlers.get(self.current_state)
    if handler is None:
        self.error_message = f"未知状态: {self.current_state}"
        self.set_state(RFQState.ERROR)
        continue
    handler()
```

终止状态的 reset 检查和 sleep 已在 `_handle_completed/error/stopped()` 内部处理，不需要外层额外循环。

---

## 优先级排序

| 优先级 | 项目 | 理由 |
|--------|------|------|
| P0 | sim_ioc.py vac7/vac8 bug（一.1） | 运行时崩溃 |
| P0 | 日志 namer 硬编码年份（一.2） | 2027年起日志轮转失效 |
| P0 | callback 不恢复 bug（三.1） | 终止状态后重启监控失效 |
| P1 | 实现 STABLE_BUILDING 状态（二） | 核心新功能 |
| P2 | 冗余真空检查（三.2） | 删除几行代码 |
| P2 | except 块内 import（三.3） | 防止异常掩盖 |
| P2 | run() 主循环简化（四） | 去除重复逻辑，~10行改动 |

# 3.4 集成测试结果（TC-INT-06/07/08/09）

## 执行信息

- 时间: `2026-03-31T20:24:13`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_4/results`

## 汇总

- 总用例: `4`
- 通过: `4`
- 不通过: `0`

## TC-INT-06 单次 Arc 故障自动恢复

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING"
  ],
  "recovery_sequence_from_log": true,
  "pulse_before_s": 0.11,
  "pulse_after_s": 0.1,
  "power_before": 9.999999999999996,
  "power_after": 5.1,
  "recovery_state": "INITIALIZING"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `fault_window_ready` | `PASS` |
| `fault_status_to_0` | `PASS` |
| `rf_off_after_fault` | `PASS` |
| `recovery_sequence_order` | `PASS` |
| `fault_status_back_to_1` | `PASS` |
| `rf_on_after_recovery` | `PASS` |
| `recovery_state_seen` | `PASS` |
| `power_recovered_positive` | `PASS` |
| `pulse_dropped_after_fault` | `PASS` |

### 结论

- `通过`

## TC-INT-07 单次 VacInterlock 故障自动恢复

### 测试输出

```json
{
  "status_timeline": [
    "INITIALIZING",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING"
  ],
  "recovery_sequence_from_log": true,
  "pulse_before_s": 0.11,
  "pulse_after_s": 0.1,
  "power_before": 9.999999999999996,
  "power_after": 5.1,
  "recovery_state": "INITIALIZING"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `fault_window_ready` | `PASS` |
| `fault_status_to_0` | `PASS` |
| `rf_off_after_fault` | `PASS` |
| `recovery_sequence_order` | `PASS` |
| `fault_status_back_to_1` | `PASS` |
| `rf_on_after_recovery` | `PASS` |
| `recovery_state_seen` | `PASS` |
| `power_recovered_positive` | `PASS` |
| `pulse_dropped_after_fault` | `PASS` |

### 结论

- `通过`

## TC-INT-08 故障次数超限进入 ERROR

### 测试输出

```json
{
  "status_timeline": [
    "INITIALIZING",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "ERROR",
    "IDLE",
    "INITIALIZING"
  ],
  "recovery_flags_first_three_faults": [
    true,
    true,
    true
  ],
  "rf_on_error": 0,
  "pulse_drive_error": 0.0,
  "cw_drive_error": 0.0,
  "status_after_5s": "ERROR"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `running_before_faults` | `PASS` |
| `first_two_faults_recovered` | `PASS` |
| `third_fault_triggers_error` | `PASS` |
| `rf_off_in_error` | `PASS` |
| `drive_zero_in_error` | `PASS` |
| `stays_error_without_manual_reset` | `PASS` |

### 结论

- `通过`

## TC-INT-09 ERROR 状态后手动复位

### 测试输出

```json
{
  "status_timeline": [
    "INITIALIZING",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "ERROR",
    "IDLE",
    "INITIALIZING"
  ],
  "pulse_after_reset_s": 0.1,
  "start_after_reset": 0,
  "target_after_reset": 20.0,
  "restart_state": "INITIALIZING"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `reset_back_to_idle` | `PASS` |
| `pulse_restored_to_original_start` | `PASS` |
| `target_reinitialized` | `PASS` |
| `restart_possible_after_error` | `PASS` |

### 结论

- `通过`

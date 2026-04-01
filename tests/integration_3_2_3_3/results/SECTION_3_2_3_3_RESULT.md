# 3.2/3.3 集成测试结果（TC-INT-03/04/05）

## 执行信息

- 时间: `2026-03-31T19:54:14`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_2_3_3/results`

## 汇总

- 总用例: `3`
- 通过: `3`
- 不通过: `0`

## TC-INT-03 调功率过程中暂停与恢复

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "PAUSED",
    "ADJUSTING_POWER"
  ],
  "pause_begin": {
    "status": "PAUSED",
    "start": 0,
    "rf_on": 1,
    "power": 10.999997260144365,
    "drive": 110.0,
    "pulse_time_s": 0.1,
    "target_power": 20.0
  },
  "pause_end": {
    "status": "PAUSED",
    "start": 0,
    "rf_on": 1,
    "power": 10.999999999999948,
    "drive": 110.0,
    "pulse_time_s": 0.1,
    "target_power": 20.0
  }
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_adjusting` | `PASS` |
| `drive_changed_before_pause` | `PASS` |
| `entered_paused` | `PASS` |
| `rf_on_kept_1_during_pause` | `PASS` |
| `drive_not_changed_during_pause` | `PASS` |
| `resumed_to_adjusting` | `PASS` |
| `resumed_without_reinit` | `PASS` |

### 结论

- `通过`

## TC-INT-04 展脉宽过程中暂停与恢复

### 测试输出

```json
{
  "status_timeline": [
    "ADJUSTING_POWER",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "PAUSED",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE"
  ],
  "pulse_before_pause_s": 0.102,
  "pulse_pause_begin_s": 0.102,
  "pulse_pause_end_s": 0.102,
  "pulse_after_resume_s": 0.104
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_expanding` | `PASS` |
| `expanding_progress_observed` | `PASS` |
| `entered_paused` | `PASS` |
| `pulse_frozen_during_pause` | `PASS` |
| `resume_signal_processed` | `PASS` |
| `pulse_continues_after_resume` | `PASS` |
| `pulse_not_reset_on_resume` | `PASS` |

### 结论

- `通过`

## TC-INT-05 用户暂停后手动复位

### 测试输出

```json
{
  "status_timeline": [
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "PAUSED",
    "IDLE",
    "INITIALIZING"
  ],
  "pre_reset_target": 20.0,
  "pre_reset_pulse_s": 0.1,
  "target_after_reset": 10.0,
  "pulse_after_reset_s": 0.1,
  "start_after_reset": 0
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `reached_second_target_before_pause` | `PASS` |
| `entered_paused` | `PASS` |
| `reset_returns_to_idle` | `PASS` |
| `target_restored_to_first` | `PASS` |
| `pulse_restored_to_start` | `PASS` |
| `start_cleared_after_reset` | `PASS` |
| `restart_after_reset` | `PASS` |

### 结论

- `通过`

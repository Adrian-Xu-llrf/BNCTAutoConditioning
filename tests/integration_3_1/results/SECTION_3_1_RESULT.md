# 3.1 集成测试结果（TC-INT-01/02）

## 执行信息

- 时间: `2026-03-31T19:45:21`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_1/results`

## 汇总

- 总用例: `2`
- 通过: `2`
- 不通过: `0`

## TC-INT-01 完整三段功率老练（Happy Path）

### 测试输出

```json
{
  "statuses": [
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED"
  ],
  "targets_seen": [
    0.0,
    10.0,
    20.0,
    30.0
  ],
  "final_start": 0,
  "final_rf_on": 1,
  "final_pulse_time_s": 0.11,
  "sample_count": 272
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `completed` | `PASS` |
| `status_initializing_seen` | `PASS` |
| `status_adjusting_seen` | `PASS` |
| `status_expanding_seen` | `PASS` |
| `status_completed_seen` | `PASS` |
| `target_10_seen` | `PASS` |
| `target_20_seen` | `PASS` |
| `target_30_seen` | `PASS` |
| `start_auto_reset_to_0` | `PASS` |
| `rf_on_kept_1_after_complete` | `PASS` |
| `pulse_reached_end_110ms` | `PASS` |

### 结论

- `通过`

## TC-INT-02 CW 模式完整流程

### 测试输出

```json
{
  "statuses": [
    "IDLE",
    "INITIALIZING",
    "COMPLETED"
  ],
  "targets_seen": [
    10.0
  ],
  "pulse_time_expected_s": 0.123,
  "pulse_time_sentinel_s": 0.123,
  "final_pulse_time_s": 0.123,
  "final_cw_drive": 100.0,
  "final_pulse_drive": 0.0,
  "final_power": 9.976739135822404,
  "sample_count": 10
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `completed` | `PASS` |
| `status_completed_seen` | `PASS` |
| `cw_target_seen_10` | `PASS` |
| `pulse_time_unchanged` | `PASS` |
| `cw_drive_used` | `PASS` |
| `pulse_drive_not_used` | `PASS` |
| `power_positive` | `PASS` |

### 结论

- `通过`

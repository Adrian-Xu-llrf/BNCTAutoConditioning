# 3.7 集成测试结果（TC-INT-13/14）

## 执行信息

- 时间: `2026-03-31T20:53:00`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_7/results`

## 汇总

- 总用例: `2`
- 通过: `2`
- 不通过: `0`

## TC-INT-13 第2段目标功率已满足时跳过调功率

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
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER"
  ],
  "target_now": 30.0,
  "drive_adjust_count_in_second_segment": 0,
  "has_power_ok_log": true,
  "has_direct_expand_log": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `switched_to_second_target_log` | `PASS` |
| `switched_to_third_target_log` | `PASS` |
| `target_progressed_to_30_by_pv` | `PASS` |
| `no_drive_adjust_while_second_target_already_satisfied` | `PASS` |
| `second_target_directly_returns_to_expanding` | `PASS` |

### 结论

- `通过`

## TC-INT-14 脉宽已在 pulse_end 时跳过展宽

### 测试输出

```json
{
  "status_timeline": [
    "ADJUSTING_POWER",
    "PAUSED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER"
  ],
  "pulse_final_s": 0.11,
  "pulse_min_s": 0.1,
  "pulse_max_s": 0.11,
  "has_reached_log": true,
  "has_expand_write_log": false
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `switched_to_second_target` | `PASS` |
| `pulse_kept_at_pulse_end` | `PASS` |
| `expand_immediately_marked_complete` | `PASS` |
| `no_pulse_expand_write` | `PASS` |

### 结论

- `通过`

# 第4章 边界与异常测试结果（E-01 ~ E-09）

## 执行信息

- 时间: `2026-03-31T21:09:52`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_4/results`

## 汇总

- 总用例: `9`
- 通过: `9`
- 不通过: `0`

## E-01 AutoC_PowerTargets 全为 0

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "ERROR"
  ],
  "start_after_error": 0,
  "error_log_present": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_error_or_not_started` | `PASS` |
| `start_cleared` | `PASS` |
| `error_log_present` | `PASS` |

### 结论

- `通过`

## E-02 pulse_start > pulse_end

### 测试输出

```json
{
  "status_timeline": [
    "ERROR",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "COMPLETED"
  ],
  "pulse_time_after_s": 0.12,
  "has_no_expand_write": true,
  "has_reached_log": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `completed_without_looping` | `PASS` |
| `pulse_time_kept_at_start` | `PASS` |
| `no_pulse_expand_write` | `PASS` |
| `reached_target_log_present` | `PASS` |

### 结论

- `通过`

## E-03 pulse_step = 0

### 测试输出

```json
{
  "status_timeline": [
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER"
  ],
  "pulse_before_s": 0.1,
  "pulse_after_s": 0.1,
  "final_status": "ADJUSTING_POWER",
  "controller_alive": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_active_states` | `PASS` |
| `controller_not_crashed` | `PASS` |
| `not_enter_error` | `PASS` |
| `no_progress_risk_observed` | `PASS` |

### 结论

- `通过`

## E-04 max_faults = 0

### 测试输出

```json
{
  "status_timeline": [
    "INITIALIZING",
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "ERROR"
  ],
  "rf_on_in_error": 0
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_adjusting` | `PASS` |
| `first_fault_enters_error` | `PASS` |
| `rf_off_in_error` | `PASS` |

### 结论

- `通过`

## E-05 关键 PV 读取失败

### 测试输出

```json
{
  "status_timeline": [
    "INITIALIZING",
    "STOPPED",
    "IDLE",
    "INITIALIZING",
    "ERROR"
  ],
  "critical_fail_log_present": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_error` | `PASS` |
| `critical_pv_read_fail_log_present` | `PASS` |

### 结论

- `通过`

## E-06 PAUSED 期间修改 AutoC_PulseEnd

### 测试输出

```json
{
  "status_timeline": [
    "ADJUSTING_POWER",
    "PAUSED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "PAUSED",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE"
  ],
  "pulse_when_paused_s": 0.1,
  "pulse_after_resume_s": 0.13
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_expanding_before_pause` | `PASS` |
| `paused_successfully` | `PASS` |
| `resume_uses_new_pulse_end` | `PASS` |
| `pulse_after_resume_gt_old_end` | `PASS` |

### 结论

- `通过`

## E-07 PAUSED 期间修改 AutoC_PowerTargets

### 测试输出

```json
{
  "status_timeline": [
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "PAUSED",
    "ADJUSTING_POWER"
  ],
  "target_before_pause": 30.0,
  "target_after_resume": 15.0
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_adjusting_before_pause` | `PASS` |
| `paused_successfully` | `PASS` |
| `new_targets_applied_on_resume` | `PASS` |

### 结论

- `通过`

## E-08 超长中文状态字符串截断

### 测试输出

```json
{
  "input_len_chars": 120,
  "output_text": "状态异常状态异常状态异常状",
  "output_len_chars": 13,
  "output_len_bytes": 39
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `valid_utf8_after_truncate` | `PASS` |
| `bytes_within_limit` | `PASS` |
| `no_replacement_char` | `PASS` |

### 结论

- `通过`

## E-09 中英文混合长字符串截断

### 测试输出

```json
{
  "input_len_chars": 108,
  "output_text": "Status状态混合-0123456789-异常告",
  "output_len_chars": 25,
  "output_len_bytes": 39
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `valid_utf8_after_truncate` | `PASS` |
| `bytes_within_limit` | `PASS` |
| `no_replacement_char` | `PASS` |

### 结论

- `通过`

# 3.6 集成测试结果（TC-INT-12）

## 执行信息

- 时间: `2026-03-31T20:48:34`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_6/results`

## 汇总

- 总用例: `1`
- 通过: `1`
- 不通过: `0`

## TC-INT-12 RF 启动后 rf_on 未响应，触发重试

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "ERROR",
    "IDLE"
  ],
  "rf_on_in_error": 0,
  "retry_attempt_count": 5,
  "has_retry_log": true,
  "has_max_retry_log": true
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_error_after_retries` | `PASS` |
| `rf_off_in_error` | `PASS` |
| `retry_count_reached_max_5` | `PASS` |
| `retry_logs_present` | `PASS` |
| `manual_reset_back_to_idle` | `PASS` |

### 结论

- `通过`

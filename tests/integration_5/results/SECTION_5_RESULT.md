# 第5章 稳定性测试结果（S-5.1 ~ S-5.4）

## 执行信息

- 时间: `2026-03-31T22:07:29`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_5/results`

## 汇总

- 总用例: `4`
- 通过: `4`
- 不通过: `0`

## S-5.1 长时间运行测试（10次完整循环）

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
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "EXPANDING_PULSE",
    "COMPLETED",
    "IDLE"
  ],
  "completed_cycles": 10,
  "completion_log_seen": 10,
  "cycle_metrics": [
    {
      "rss_mb": 44.25,
      "num_threads": 15,
      "cycle": 1,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.36,
      "num_threads": 15,
      "cycle": 2,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.45,
      "num_threads": 15,
      "cycle": 3,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.5,
      "num_threads": 15,
      "cycle": 4,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.53,
      "num_threads": 15,
      "cycle": 5,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.61,
      "num_threads": 15,
      "cycle": 6,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.64,
      "num_threads": 15,
      "cycle": 7,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.69,
      "num_threads": 15,
      "cycle": 8,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.72,
      "num_threads": 15,
      "cycle": 9,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    },
    {
      "rss_mb": 44.75,
      "num_threads": 15,
      "cycle": 10,
      "completed": true,
      "start_cleared": true,
      "completion_log_seen": true
    }
  ],
  "rss_growth_mb": 0.5,
  "thread_delta": 0
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `all_10_cycles_completed` | `PASS` |
| `memory_growth_within_80mb` | `PASS` |
| `thread_delta_within_2` | `PASS` |
| `completion_log_seen_in_cycles` | `PASS` |

### 结论

- `通过`

## S-5.2 故障-恢复循环压力测试（20次）

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING",
    "EXPANDING_PULSE",
    "ADJUSTING_POWER",
    "INITIALIZING"
  ],
  "recovered_count": 20,
  "pulse_drop_count": 20,
  "fault_count_logs_found": 20,
  "fault_count_last": 39,
  "final_status": "EXPANDING_PULSE",
  "per_fault": [
    {
      "index": 1,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 2,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 3,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 4,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 5,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 6,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 7,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 8,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 9,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 10,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 11,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 12,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 13,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 14,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 15,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 16,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 17,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 18,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 19,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    },
    {
      "index": 20,
      "ready_for_inject": true,
      "arc_to_0": true,
      "recovered": true,
      "stable_after_recovery": true,
      "fault_done_log": true,
      "pulse_before_s": 0.11,
      "pulse_after_s": 0.1
    }
  ]
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_active_before_injection` | `PASS` |
| `all_20_faults_recovered` | `PASS` |
| `fault_count_monotonic` | `PASS` |
| `pulse_drop_observed` | `PASS` |
| `controller_still_running` | `PASS` |

### 结论

- `通过`

## S-5.3 并发故障注入测试

### 测试输出

```json
{
  "status_timeline": [
    "EXPANDING_PULSE",
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "INITIALIZING"
  ],
  "arc_fault_logs": 1,
  "vac_fault_logs": 1,
  "final_status": "INITIALIZING"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_active_before_injection` | `PASS` |
| `recovered_after_concurrent_injection` | `PASS` |
| `no_deadlock_or_error` | `PASS` |
| `both_fault_callbacks_seen` | `PASS` |

### 结论

- `通过`

## S-5.4 日志完整性验证

### 测试输出

```json
{
  "controller_log_size_bytes": 117189
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `state_transition_logs` | `PASS` |
| `rf_startup_logs` | `PASS` |
| `power_adjust_logs` | `PASS` |
| `fault_trigger_logs` | `PASS` |
| `fault_recovery_step_logs` | `PASS` |
| `pulse_expand_logs` | `PASS` |
| `completion_summary_logs` | `PASS` |

### 结论

- `通过`

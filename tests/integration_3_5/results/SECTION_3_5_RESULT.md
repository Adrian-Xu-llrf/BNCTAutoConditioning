# 3.5 集成测试结果（TC-INT-10/11）

## 执行信息

- 时间: `2026-03-31T20:46:31`
- Python: `3.12.2`
- 结果目录: `/Users/xullrf/Library/CloudStorage/OneDrive-个人/200-Academic/03-Project/西核所/AutoConditioning/tests/integration_3_5/results`

## 汇总

- 总用例: `2`
- 通过: `2`
- 不通过: `0`

## TC-INT-10 运行中真空超标

### 测试输出

```json
{
  "status_timeline": [
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "WAITING_VACUUM",
    "ADJUSTING_POWER"
  ],
  "rf_wait_begin": 1,
  "rf_wait_end": 1,
  "drive_wait_begin": 110.0,
  "drive_wait_end": 110.0,
  "vac3_inject": 0.001,
  "vac3_restore": 1e-06
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_adjusting` | `PASS` |
| `entered_waiting_vacuum` | `PASS` |
| `rf_kept_on_during_waiting` | `PASS` |
| `drive_not_changed_during_waiting` | `PASS` |
| `recovered_to_adjusting_after_vacuum_restore` | `PASS` |

### 结论

- `通过`

## TC-INT-11 多路真空超标，取最差值

### 测试输出

```json
{
  "status_timeline": [
    "ADJUSTING_POWER",
    "IDLE",
    "INITIALIZING",
    "ADJUSTING_POWER",
    "WAITING_VACUUM",
    "ADJUSTING_POWER"
  ],
  "vac_values_when_both_bad": {
    "RFQ:Vac2": 6e-05,
    "RFQ:Vac6": 8e-05
  },
  "worst_expected_pv": "RFQ:Vac6",
  "worst_expected_value": 8e-05,
  "status_after_vac6_restore": "WAITING_VACUUM"
}
```

### 检查项

| 检查项 | 结果 |
|---|---|
| `idle_ready` | `PASS` |
| `entered_adjusting` | `PASS` |
| `entered_waiting_vacuum` | `PASS` |
| `worst_expected_is_vac6` | `PASS` |
| `still_waiting_when_only_vac6_restored` | `PASS` |
| `recovered_after_vac2_vac6_all_normal` | `PASS` |

### 结论

- `通过`

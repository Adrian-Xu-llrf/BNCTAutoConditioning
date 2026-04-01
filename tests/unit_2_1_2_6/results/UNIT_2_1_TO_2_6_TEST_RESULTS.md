# 测试结果报告（2.1-2.6，逐条明细）

## 执行信息

- 执行时间: `2026-03-31T17:54:38.294767`
- 执行命令:

```bash
pytest -vv -rxX tests/unit_2_1_2_6/cases --junitxml tests/unit_2_1_2_6/results/UNIT_2_1_TO_2_6_junit.xml
```

## 结果汇总

- 总数: `34`
- PASSED: `33`
- XFAIL: `1`
- FAILED: `0`
- ERROR: `0`
- SKIPPED: `0`

## 2.1 PowerController

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_p_01_within_small_margin` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 2 | `test_u_p_02_low_power_large_error_use_step1` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 3 | `test_u_p_03_low_power_small_error_use_step2` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 4 | `test_u_p_04_high_power_large_error_decrease_step1` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 5 | `test_u_p_05_iteration_count_increments` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 6 | `test_u_p_06_drive_lower_bound_protection` | `XFAIL (time=0.000s)` | 预期失败，当前实现存在已知缺口：当前实现未做Drive下限保护。 |

## 2.2 PulseController

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_pl_01_already_at_end` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 2 | `test_u_pl_02_expand_normally` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 3 | `test_u_pl_03_no_reduce_power_mode` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 4 | `test_u_pl_04_reduce_power_before_expand` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 5 | `test_u_pl_05_over_end_treated_as_done` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 6 | `test_u_pl_06_unit_conversion_seconds_to_ms` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |

## 2.3 FaultHandler

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_f_01_fault_count_accumulates` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 2 | `test_u_f_02_fault_exceeded_at_limit` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 3 | `test_u_f_03_not_exceeded_below_limit` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 4 | `test_u_f_04_reset_fault_count` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 5 | `test_u_f_05_recovery_order` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 6 | `test_u_f_06_check_faults_cleared` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 7 | `test_u_f_07_recovery_failure_handled` | `PASSED (time=0.001s)` | 通过，断言满足预期。 |
| 8 | `test_u_f_08_cleanup_clears_callbacks` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |

## 2.4 VacuumChecker

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_v_01_fail_safe_without_callbacks` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 2 | `test_u_v_02_all_normal` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 3 | `test_u_v_03_single_over_threshold` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 4 | `test_u_v_04_pick_worst_value` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 5 | `test_u_v_05_recover_to_normal` | `PASSED (time=0.001s)` | 通过，断言满足预期。 |
| 6 | `test_u_v_06_threshold_boundary_is_not_ok` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |

## 2.5 RFQController.reset()

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_r_01_manual_reset_clear_faults` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 2 | `test_u_r_02_auto_reset_keep_faults_and_drop_pulse` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 3 | `test_u_r_03_pulse_start_floor_is_original` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |
| 4 | `test_u_r_04_reset_rebuilds_subcontrollers` | `PASSED (time=0.000s)` | 通过，断言满足预期。 |

## 2.6 Config

| 序号 | 测试用例 | 测试输出 | 结论 |
|---|---|---|---|
| 1 | `test_u_c_01_nested_get` | `PASSED (time=0.005s)` | 通过，断言满足预期。 |
| 2 | `test_u_c_02_missing_path_default` | `PASSED (time=0.002s)` | 通过，断言满足预期。 |
| 3 | `test_u_c_03_get_pv` | `PASSED (time=0.002s)` | 通过，断言满足预期。 |
| 4 | `test_u_c_04_reload_reflects_file_change` | `PASSED (time=0.002s)` | 通过，断言满足预期。 |


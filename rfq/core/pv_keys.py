#!/usr/bin/env python3
"""
PV键常量定义
集中管理所有PV逻辑键，避免魔法字符串拼写错误

作者: Chengye Xu
日期: 2026-04
"""


class PVKeys:
    """PV逻辑键常量 — 集中定义，统一引用"""

    # ==================== RF 控制 ====================
    RF_ON = 'rf.rf_on'
    RF_POWER = 'rf.power'
    PULSE_DRIVE = 'rf.pulse_drive'
    CW_DRIVE = 'rf.cw_drive'
    PULSE_CW = 'rf.pulse_cw'
    PULSE_TIME = 'rf.pulse_time'
    SWEEP = 'rf.sweep'
    TRACKING = 'rf.tracking'
    AMP_LIMITER = 'rf.Amp_Limiter'
    AMP_SETPOINT = 'rf.setpoint_set'
    AMP_ERROR = 'rf.error_read'
    AMP_LOOP_STATUS = 'rf.loop_status_read'
    AMP_CLOSE_LOOP = 'rf.close_loop'

    # ==================== 故障 PV ====================
    FAULT_ARC = 'fault.arc'
    FAULT_VAC_INTERLOCK = 'fault.VacInterlock'
    FAULT_INTERLOCK2 = 'fault.interlock2'
    FAULT_DI4 = 'fault.di4'

    # 故障复位 PV
    FAULT_VAC_RESET = 'fault.VacReset'
    FAULT_RESET_INTERLOCK = 'fault.reset_interlock'
    FAULT_RESET_PW_STAT1 = 'fault.ResetPWFaultStat1'
    FAULT_RESET_PW_STAT2 = 'fault.ResetPWFaultStat2'

    # ==================== 控制 PV ====================
    CONTROL_START = 'control.start'
    CONTROL_RESET = 'control.reset'
    CONTROL_STATUS = 'control.status'
    CONTROL_POWER_TARGETS = 'control.power_targets'
    CONTROL_INIT_DRIVE = 'control.init_drive'
    CONTROL_PULSE_START = 'control.pulse_start'
    CONTROL_PULSE_END = 'control.pulse_end'
    CONTROL_PULSE_STEP = 'control.pulse_step'
    CONTROL_PULSE_WAIT = 'control.pulse_wait'
    CONTROL_PULSE_DROP = 'control.pulse_drop'
    CONTROL_DRIVE_STEP1 = 'control.drive_step1'
    CONTROL_DRIVE_STEP2 = 'control.drive_step2'
    CONTROL_MARGIN_LARGE = 'control.margin_large'
    CONTROL_MARGIN_SMALL = 'control.margin_small'
    CONTROL_WAIT_BEFORE_EXPAND = 'control.wait_before_expand'
    CONTROL_CURRENT_TARGET_POWER = 'control.current_target_power'
    CONTROL_CURRENT_PULSE = 'control.current_pulse'

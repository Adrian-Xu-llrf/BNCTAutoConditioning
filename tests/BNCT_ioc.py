#!/usr/bin/env python3
"""
RFQ 老练控制仿真 IOC - 基于 caproto
只提供老练控制相关的 PV 接口。

使用方法:
    python tests/sim_autoc_ioc.py

作者: Adrian Xu
日期: 2026-04
"""

from caproto.server import pvproperty, PVGroup, run, ioc_arg_parser


class RFQAutoCIOC(PVGroup):
    """RFQ 老练控制仿真 IOC"""

    # ==================== 老练控制 PV ====================
    autoc_start = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:AutoC_Start',
        doc='启动老练',
    )
    autoc_reset = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:AutoC_Reset',
        doc='复位',
    )
    autoc_status = pvproperty(
        value='IDLE', dtype=str,
        name='RFQ:LLRF:Con01:AutoC_Status',
        doc='当前状态文本',
    )
    autoc_power_targets = pvproperty(
        value=[80.0, 90.0, 100.0, 0.0],
        dtype=float,
        max_length=4,
        name='RFQ:LLRF:Con01:AutoC_PowerTargets',
        doc='目标功率列表（waveform，kW），零值为无效元素',
    )
    autoc_current_target_power = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_CurrentTargetPower',
        doc='当前正在老练的目标功率（kW）[程序写入]',
    )
    autoc_init_drive = pvproperty(
        value=600.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_InitDrive',
        doc='初始 Drive',
    )
    autoc_pulse_start = pvproperty(
        value=0.1, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseStart',
        doc='脉冲起始宽度（ms）',
    )
    autoc_pulse_end = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseEnd',
        doc='脉冲目标宽度（ms）',
    )
    autoc_current_pulse = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_CurrentPulse',
        doc='当前脉冲宽度（ms）',
    )
    autoc_pulse_step = pvproperty(
        value=0.5, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseStep',
        doc='展宽步长（ms）',
    )
    autoc_drive_step1 = pvproperty(
        value=20.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_DriveStep1',
        doc='功率调节大步长',
    )
    autoc_drive_step2 = pvproperty(
        value=5.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_DriveStep2',
        doc='功率调节小步长',
    )
    autoc_margin_large = pvproperty(
        value=5.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_MarginLarge',
        doc='大裕度阈值（kW）',
    )
    autoc_margin_small = pvproperty(
        value=1.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_MarginSmall',
        doc='小裕度阈值（kW）',
    )
    autoc_pulse_wait = pvproperty(
        value=20.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseWaitTime',
        doc='展宽等待时间（ms）',
    )
    autoc_power_wait = pvproperty(
        value=20.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PowerWaitTime',
        doc='功率等待时间（ms）',
    )
    autoc_pulse_drop = pvproperty(
        value=20.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseDrop',
        doc='脉冲下降宽度（ms）',
    )
    # ==================== 稳定建场 PV ====================
    autoc_stable_step = pvproperty(
        value=20.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_stable_step',
        doc='稳定建场步长',
    )
    autoc_stable_margin = pvproperty(
        value=1.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_stable_margin',
        doc='稳定建场容差',
    )
    autoc_stable_power = pvproperty(
        value=5.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_stable_power',
        doc='稳定建场功率',
    )


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='',
        desc='RFQ 老练控制仿真 IOC',
    )
    ioc = RFQAutoCIOC(**ioc_options)

    print("=" * 55)
    print("RFQ 老练控制仿真 IOC 就绪")
    print("  仅发布老练控制相关 PV")
    print("  PV 前缀: RFQ:LLRF:Con01:")
    print("=" * 55)
    print("快速验证:")
    print("  caproto-put RFQ:LLRF:Con01:AutoC_Start 1")
    print("  caproto-get RFQ:LLRF:Con01:AutoC_Status")
    print("  caproto-get RFQ:LLRF:Con01:AutoC_PowerTargets")
    print("=" * 55)

    run(ioc.pvdb, **run_options)

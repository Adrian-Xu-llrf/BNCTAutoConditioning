#!/usr/bin/env python3
"""
RFQ 仿真 IOC - 基于 caproto
提供与真实硬件相同的 PV 接口，内置功率物理仿真和故障注入。

使用方法:
    python tests/sim_ioc.py

作者: Adrian Xu
日期: 2025-11
"""

from caproto.server import pvproperty, PVGroup, run, ioc_arg_parser


class RFQSimIOC(PVGroup):
    """RFQ 仿真 IOC"""

    # ==================== 3.1 RF 控制 PV ====================
    rf_on = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:Opr_RFOn',
        doc='RF 开/关',
    )
    pulse_drive = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AmpPulseDrive_Set',
        doc='脉冲模式 Drive',
    )
    cw_drive = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AmpCWDrive_Set',
        doc='CW 模式 Drive',
    )
    pulse_cw = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:pulsecw',
        doc='模式选择（0=CW，1=脉冲）',
    )
    pulse_time = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:RFPulseOnTime_Set',
        doc='脉冲宽度（s）',
    )
    freq_sweep = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01_DAC:FreqSweep_Set',
        doc='频率扫描',
    )
    freq_tracking = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:frequency_tracking',
        doc='频率跟踪',
    )
    power = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01_RFIn03:Power',
        doc='当前腔体功率（kW）[仿真输出]',
    )
    wait_time = pvproperty(
        value=0.5, dtype=float,
        name='RFQ:LLRF:Con01:WaitTime_Set',
        doc='等待时间',
    )

    # ==================== 3.2 故障 PV ====================
    arc_status = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:Arc_Status',
        doc='弧光状态（1=正常，0=故障）',
    )
    interlock_status = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:Interlock_Status',
        doc='联锁状态（1=正常，0=故障）',
    )
    reset_interlock = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:ResetInterlock',
        doc='复位联锁',
    )
    ssa_comp = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Mon02:ForwardPowerComp',
        doc='SSA 前向功率补偿状态',
    )
    reflected_power_comp = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Mon02:ReflectedPowerComp',
        doc='反射功率补偿状态',
    )
    reset_pw_fault = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Mon02:ResetPWFaultStat',
        doc='复位功率故障',
    )

    # ==================== 3.3 真空 PV ====================
    vac4 = pvproperty(
        value=1e-6, dtype=float,
        name='RFQ:Vac4',
        doc='真空计1（Pa）',
    )
    vac_cav = pvproperty(
        value=1e-6, dtype=float,
        name='IA-RFQ-CR:VG01_CH02_CavE:Pres',
        doc='真空计2（Pa）',
    )

    # ==================== 3.4 老练控制 PV ====================
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
    autoc_target_power = pvproperty(
        value=50.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_TargetPower',
        doc='目标功率（kW）',
    )
    autoc_init_drive = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_InitDrive',
        doc='初始 Drive',
    )
    autoc_pulse_start = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseStart',
        doc='脉冲起始宽度（ms）',
    )
    autoc_pulse_end = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseEnd',
        doc='脉冲目标宽度（ms）',
    )
    autoc_pulse_step = pvproperty(
        value=50.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseStep',
        doc='展宽步长（ms）',
    )
    autoc_drive_step1 = pvproperty(
        value=10.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_DriveStep1',
        doc='功率调节大步长',
    )
    autoc_drive_step2 = pvproperty(
        value=2.0, dtype=float,
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

    # ==================== 3.5 测试辅助 PV ====================
    trigger_arc = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerArc',
        doc='写 1 → 触发弧光故障（自动清零）',
    )
    trigger_interlock = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerInterlock',
        doc='写 1 → 触发联锁故障（自动清零）',
    )

    # ==================== 4.1 功率仿真 (startup 钩子) ====================

    @power.startup
    async def power(self, instance, async_lib):
        """
        功率仿真主循环，在 caproto 事件循环中运行（每 0.1 秒更新）

        稳态功率 = drive × 0.1  (kW)
          pulse_cw=0 → 脉冲模式 → 使用 pulse_drive
          pulse_cw=1 → CW模式   → 使用 cw_drive

        实时功率（一阶低通滤波，模拟响应延迟）：
          power_new = power_old × 0.7 + 稳态功率 × 0.3

        RF 关闭时（rf_on = 0）：
          power 指数衰减（× 0.3 每步）直至归零。
        """
        current_power = 0.0

        while True:
            await async_lib.library.sleep(0.1)

            rf_on_val = self.rf_on.value

            if rf_on_val == 1:
                # pulse_cw=1 → 脉冲模式用 pulse_drive
                # pulse_cw=0 → CW 模式用 cw_drive
                if self.pulse_cw.value == 1:
                    drive = float(self.pulse_drive.value)
                else:
                    drive = float(self.cw_drive.value)

                steady_state = drive * 0.1  # kW
                current_power = current_power * 0.7 + steady_state * 0.3
            else:
                # RF 关闭：指数衰减
                current_power *= 0.3
                if current_power < 0.01:
                    current_power = 0.0

            await instance.write(current_power)

    # ==================== 4.3 故障注入回调 ====================

    @trigger_arc.putter
    async def trigger_arc(self, instance, value):
        """触发弧光故障: arc_status→0, rf_on→0, power→0，PV 自动清零（返回0）"""
        if value == 1:
            await self.arc_status.write(0)
            await self.rf_on.write(0)
            await self.power.write(0.0)
            return 0  # PV 写入后立即归零（自动清零）
        return value

    @trigger_interlock.putter
    async def trigger_interlock(self, instance, value):
        """触发联锁故障: interlock_status→0, rf_on→0, power→0，PV 自动清零"""
        if value == 1:
            await self.interlock_status.write(0)
            await self.rf_on.write(0)
            await self.power.write(0.0)
            return 0
        return value

    # ==================== 4.3 故障复位回调 ====================

    @reset_interlock.putter
    async def reset_interlock(self, instance, value):
        """复位联锁: 延迟 1 秒后 arc_status / interlock_status → 1"""
        if value == 1:
            import asyncio
            await asyncio.sleep(1.0)
            await self.arc_status.write(1)
            await self.interlock_status.write(1)
        return value

    @reset_pw_fault.putter
    async def reset_pw_fault(self, instance, value):
        """复位功率故障: 延迟 1 秒后 SSAComp / ReflectedPowerComp → 1"""
        if value == 1:
            import asyncio
            await asyncio.sleep(1.0)
            await self.ssa_comp.write(1)
            await self.reflected_power_comp.write(1)
        return value


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='',
        desc='RFQ 仿真 IOC for AutoConditioning tests',
    )

    ioc = RFQSimIOC(**ioc_options)

    print("=" * 55)
    print("RFQ 仿真 IOC 就绪")
    print("  功率仿真: power = drive × 0.1 (kW), 0.1s 更新")
    print("  pulse_cw=0 → 脉冲模式 (pulse_drive)")
    print("  pulse_cw=1 → CW 模式  (cw_drive)")
    print("=" * 55)
    print("快速验证:")
    print("  caproto-put RFQ:LLRF:Con01:Opr_RFOn 1")
    print("  caproto-put RFQ:LLRF:Con01:AmpCWDrive_Set 100")
    print("  caproto-get RFQ:LLRF:Con01_RFIn03:Power   # 期望≈10kW")
    print("=" * 55)

    run(ioc.pvdb, **run_options)

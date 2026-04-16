#!/usr/bin/env python3
"""
RFQ 仿真 IOC - 基于 caproto
提供与真实硬件相同的 PV 接口，内置功率物理仿真和故障注入。

使用方法:
    python tests/sim_ioc.py

作者: Adrian Xu
日期: 2026-03
"""

from caproto.server import pvproperty, PVGroup, run, ioc_arg_parser


class RFQSimIOC(PVGroup):
    """RFQ 仿真 IOC"""

    # ==================== 3.1 RF 控制 PV ====================
    rf_on = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:RFOn',
        doc='RF 开/关',
    )
    pulse_drive = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AmpPulseDrive',
        doc='脉冲模式 Drive',
    )
    cw_drive = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AmpCWDrive',
        doc='CW 模式 Drive',
    )
    pulse_cw = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:pulsecw',
        doc='模式选择（0=CW，1=脉冲）',
    )
    pulse_time = pvproperty(
        value=1.0, dtype=float,
        name='RFQ:LLRF:Con01:pulseontime',
        doc='脉冲宽度（s）',
    )
    freq_sweep = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:sweepfrequency',
        doc='频率扫描',
    )
    freq_tracking = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:frequency_tracking',
        doc='频率跟踪',
    )
    amp_limiter = pvproperty(
        value=400.0, dtype=float,
        name='RFQ:LLRF:Con01:amplimiter',
        doc='Drive 幅度上限',
    )
    power = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:rf1power',
        doc='当前腔体功率（kW）[仿真输出]',
    )
    wait_time = pvproperty(
        value=0.5, dtype=float,
        name='RFQ:LLRF:Con01:WaitTime_Set',
        doc='每次展脉宽等待时间（s）',
    )
    detuning_error = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:Detuning_Err2',
        doc='失谐误差（稳定建场用）',
    )
    freq_start = pvproperty(
        value=162.620, dtype=float,
        name='RFQ:LLRF:Con01:sweepstartfreq',
        doc='频率扫描起始频率（MHz）',
    )

    ### 闭环控制PV
    amp_setpoint = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:ampsetpoint',
        doc='Drive 幅度设置点',
    )
    amp_error = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:amperror',
        doc='Drive 幅度误差',
    )
    amp_loop_status = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:amploopstatus',
        doc='Drive 闭环状态（0=未开启，1=已开启）',
    )
    amp_close_loop = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:ampcloseloop',
        doc='Drive 闭环关闭',
    )

    # ==================== 3.2 故障 PV ====================
    arc_status_rd = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:Arc_Lock',
        doc='打火状态（1=正常，0=故障）',
    )
    interlock_status_rd = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:Arc_Status',
        doc='联锁状态（1=正常，0=故障）',
    )
    interlock_status2_rd = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:Interlock_Status',
        doc='联锁状态2（1=正常，0=故障）',
    )
    di4 = pvproperty(
        value=1, dtype=int,
        name='RFQ:LLRF:Con01:di4',
        doc='数字输入4（1=正常，0=故障）',
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
    reset_pw_fault1 = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Mon01:ResetPWFaultStat',
        doc='复位功率故障1',
    )
    reset_pw_fault2 = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Mon02:ResetPWFaultStat',
        doc='复位功率故障2',
    )
    vac_reset = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:SPS:Reset',
        doc='真空复位',
    )

    # ==================== 3.3 真空 PV ====================
    vac1 = pvproperty(
        value=1e-6, dtype=float,
        name='C1:VAC',
        doc='真空计1（Pa）',
    )
    vac2 = pvproperty(
        value=1e-6, dtype=float,
        name='C2:VAC',
        doc='真空计2（Pa）',
    )
    vac3 = pvproperty(
        value=1e-6, dtype=float,
        name='C3:VAC',
        doc='真空计3（Pa）',
    )
    vac4 = pvproperty(
        value=1e-6, dtype=float,
        name='C4:VAC',
        doc='真空计4（Pa）',
    )
    vac5 = pvproperty(
        value=1e-6, dtype=float,
        name='C5:VAC',
        doc='真空计5（Pa）',
    )
    vac6 = pvproperty(
        value=1e-6, dtype=float,
        name='C6:VAC',
        doc='真空计6（Pa）',
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
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:AutoC_Status',
        doc='当前状态码（RFQState.value）',
    )
    autoc_power_targets = pvproperty(
        value=[10.0, 20.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        dtype=float,
        max_length=10,
        name='RFQ:LLRF:Con01:AutoC_PowerTargets',
        doc='目标功率列表（waveform，kW），零值为无效元素',
    )
    autoc_current_target_power = pvproperty(
        value=0.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_CurrentTargetPower',
        doc='当前正在老练的目标功率（kW）[程序写入]',
    )
    autoc_init_drive = pvproperty(
        value=10.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_InitDrive',
        doc='初始 Drive',
    )
    autoc_pulse_start = pvproperty(
        value=10.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseStart',
        doc='脉冲起始宽度（ms）',
    )
    autoc_pulse_end = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseEnd',
        doc='脉冲目标宽度（ms）',
    )
    autoc_current_pulse = pvproperty(
        value=100.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_CurrentPulse',
        doc='当前脉冲宽度（ms）',
    )
    autoc_pulse_step = pvproperty(
        value=10.0, dtype=float,
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
    autoc_pulse_wait = pvproperty(
        value=2.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseWaitTime',
        doc='展宽等待时间（ms）',
    )
    autoc_power_wait = pvproperty(
        value=0.2, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PowerWaitTime',
        doc='功率等待时间（ms）',
    )
    autoc_pulse_drop = pvproperty(
        value=10.0, dtype=float,
        name='RFQ:LLRF:Con01:AutoC_PulseDrop',
        doc='脉冲下降宽度（ms）',
    )
    autoc_stable_step = pvproperty(
        value=10.0, dtype=float,
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
        doc='稳定建场功率（kW）[程序写入]',
    )
    autoc_auto_load = pvproperty(
        value=0, dtype=int,
        name='RFQ:LLRF:Con01:AutoC_AutoLoad',
        doc='自动加载模式（0=关, 1=开）',
    )



    # ==================== 3.5 测试辅助 PV ====================
    trigger_arc = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerArc',
        doc='写 1 → 触发打火故障（自动清零）',
    )
    trigger_interlock = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerInterlock',
        doc='写 1 → 触发联锁故障（自动清零）',
    )
    trigger_interlock2 = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerInterlock2',
        doc='写 1 → 触发联锁2故障（自动清零）',
    )
    trigger_di4 = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:TriggerDI4',
        doc='写 1 → 触发DI4故障（自动清零）',
    )
    block_rf_on = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:BlockRFOn',
        doc='写 1 → 拦截 rf_on=1（保持RF关闭）',
    )
    block_power = pvproperty(
        value=0, dtype=int,
        name='RFQ:SIM:BlockPower',
        doc='写 1 → 强制功率输出为 0（模拟 Drive 增加但无功率输出）',
    )
    sim_vac_all = pvproperty(
        value=1e-6, dtype=float,
        name='RFQ:SIM:VacAll',
        doc='写入值 → 同时设置所有真空计（Pa），用于模拟真空整体变化',
    )
    sim_vac_target = pvproperty(
        value=-1, dtype=int,
        name='RFQ:SIM:VacTarget',
        doc='指定单个真空计编号（0-5），配合 RFQ:SIM:VacSingle 使用；-1表示不生效',
    )
    sim_vac_single = pvproperty(
        value=1e-6, dtype=float,
        name='RFQ:SIM:VacSingle',
        doc='写入值 → 设置 RFQ:SIM:VacTarget 指定的单个真空计（Pa）',
    )

    @rf_on.putter
    async def rf_on(self, instance, value):
        """
        RF 开关 putter：
        - block_rf_on=1 时拒绝 rf_on=1
        - 任一故障 PV==0 时拒绝 rf_on=1（必须全部复位后才能启动 RF）
        """
        if int(value) == 1:
            if int(self.block_rf_on.value) == 1:
                return 0
            fault_pvs = [
                self.arc_status_rd,
                self.interlock_status_rd,
                self.interlock_status2_rd,
                self.di4,
            ]
            if any(pv.value == 0 for pv in fault_pvs):
                return 0
        return int(value)

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

            if self.block_power.value == 1:
                current_power *= 0.3
                if current_power < 0.01:
                    current_power = 0.0
                await instance.write(current_power)
                continue

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

    # ==================== 4.2 故障监控 (startup 钩子) ====================

    @arc_status_rd.startup
    async def arc_status_rd(self, instance, async_lib):
        """
        故障监控主循环，每 0.1 秒检查所有故障 PV。
        任一故障 PV == 0 时自动关闭 RF、清零 Drive（模拟硬件保护行为）。
        """
        while True:
            await async_lib.library.sleep(0.1)

            fault_pvs = [
                self.arc_status_rd,
                self.interlock_status_rd,
                self.interlock_status2_rd,
                self.di4,
            ]
            any_fault = any(pv.value == 0 for pv in fault_pvs)

            if any_fault and self.rf_on.value == 1:
                await self.rf_on.write(0)
                await self.pulse_drive.write(0.0)
                await self.cw_drive.write(0.0)

    # ==================== 4.3 故障注入回调 ====================

    @trigger_arc.putter
    async def trigger_arc(self, instance, value):
        """触发打火故障: arc_status_rd→0，PV 自动清零（RF 由故障监控循环关闭）"""
        if value == 1:
            await self.arc_status_rd.write(0)
            return 0
        return value

    @trigger_interlock.putter
    async def trigger_interlock(self, instance, value):
        """触发联锁故障: interlock_status_rd→0，PV 自动清零（RF 由故障监控循环关闭）"""
        if value == 1:
            await self.interlock_status_rd.write(0)
            return 0
        return value

    @trigger_interlock2.putter
    async def trigger_interlock2(self, instance, value):
        """触发联锁2故障: interlock_status2_rd→0，PV 自动清零（RF 由故障监控循环关闭）"""
        if value == 1:
            await self.interlock_status2_rd.write(0)
            return 0
        return value

    @trigger_di4.putter
    async def trigger_di4(self, instance, value):
        """触发DI4故障: di4→0，PV 自动清零（RF 由故障监控循环关闭）"""
        if value == 1:
            await self.di4.write(0)
            return 0
        return value

    # ==================== 4.4 故障复位回调 ====================
    #
    # 所有 reset PV 必须被触发一遍，故障才会消除。
    # _reset_done 集合追踪哪些 reset 已执行，全部完成后恢复故障 PV。

    _reset_done = set()
    _reset_all_keys = {'vac_reset', 'reset_interlock', 'reset_pw_fault1', 'reset_pw_fault2'}

    async def _check_reset_complete(self):
        """检查是否所有 reset 都已触发，如果是则恢复所有故障 PV"""
        if self._reset_all_keys.issubset(self._reset_done):
            self._reset_done.clear()
            await self.arc_status_rd.write(1)
            await self.interlock_status_rd.write(1)
            await self.interlock_status2_rd.write(1)
            await self.di4.write(1)
            await self.ssa_comp.write(1)
            await self.reflected_power_comp.write(1)

    @vac_reset.putter
    async def vac_reset(self, instance, value):
        """真空复位: 标记完成，全部 reset 到齐后恢复故障"""
        if value == 1:
            self._reset_done.add('vac_reset')
            await self._check_reset_complete()
        return value

    @reset_interlock.putter
    async def reset_interlock(self, instance, value):
        """联锁复位: 标记完成，全部 reset 到齐后恢复故障"""
        if value == 1:
            self._reset_done.add('reset_interlock')
            await self._check_reset_complete()
        return value

    @reset_pw_fault1.putter
    async def reset_pw_fault1(self, instance, value):
        """功率故障1复位: 标记完成，全部 reset 到齐后恢复故障"""
        if value == 1:
            self._reset_done.add('reset_pw_fault1')
            await self._check_reset_complete()
        return value

    @reset_pw_fault2.putter
    async def reset_pw_fault2(self, instance, value):
        """功率故障2复位: 标记完成，全部 reset 到齐后恢复故障"""
        if value == 1:
            self._reset_done.add('reset_pw_fault2')
            await self._check_reset_complete()
        return value

    # ==================== 4.5 真空控制回调 ====================

    @sim_vac_all.putter
    async def sim_vac_all(self, instance, value):
        """同时设置所有真空计"""
        for v in [self.vac1, self.vac2, self.vac3, self.vac4,
                   self.vac5, self.vac6]:
            await v.write(float(value))
        return float(value)

    @sim_vac_single.putter
    async def sim_vac_single(self, instance, value):
        """设置单个真空计（由 sim_vac_target 指定编号 0-7）"""
        idx = int(self.sim_vac_target.value)
        targets = [self.vac1, self.vac2, self.vac3, self.vac4,
                   self.vac5, self.vac6]
        if 0 <= idx < len(targets):
            await targets[idx].write(float(value))
        return float(value)


if __name__ == '__main__':
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='',
        desc='RFQ 仿真 IOC for AutoConditioning tests',
    )

    ioc = RFQSimIOC(**ioc_options)

    print("=" * 55)
    print("RFQ 仿真 IOC 就绪")
    print("  功率仿真: power = drive × 0.1 (kW), 0.1s 更新")
    print("  pulse_cw=1 → 脉冲模式 (pulse_drive)")
    print("  pulse_cw=0 → CW 模式  (cw_drive)")
    print("=" * 55)
    print("快速验证:")
    print("  caproto-put RFQ:LLRF:Con01:RFOn 1")
    print("  caproto-put RFQ:LLRF:Con01:AmpCWDrive 100")
    print("  caproto-get RFQ:LLRF:Con01:rf1power   # 期望≈10kW")
    print("  caproto-get RFQ:LLRF:Con01:AutoC_PowerTargets  # 期望[10,20,30,0,...]")
    print("=" * 55)

    run(ioc.pvdb, **run_options)

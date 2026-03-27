#!/usr/bin/env python3
"""
PV 连接测试脚本
测试 sim_ioc.py 中的 PV 是否可以正常读写

使用方法:
    python tests/test_pv_connect.py
"""

import time
import sys


def test_pv(pv_name, timeout=3.0):
    """测试单个 PV 连接"""
    try:
        import epics
        value = epics.caget(pv_name, timeout=timeout)
        if value is None:
            return False, f"无法读取 (返回 None)"
        return True, f"值={value}"
    except Exception as e:
        return False, f"异常: {e}"


def main():
    print("=" * 60)
    print("PV 连接测试")
    print("=" * 60)

    all_pvs = [
        # 故障 PV
        ('RFQ:LLRF:Con01:ArcStatus_Rd', '弧光状态'),
        ('RFQ:LLRF:Con01:InterlockStatus_Rd', '联锁状态'),
        ('RFQ:LLRF:Con01:InterlockStatus2_Rd', '联锁状态2'),
        ('RFQ:LLRF:Con01:di4', '数字输入4'),

        # 复位 PV
        ('RFQ:LLRF:Con01:ResetInterlock', '复位联锁'),
        ('RFQ:LLRF:Mon01:ResetPWFaultStat', '复位功率故障1'),
        ('RFQ:LLRF:Mon02:ResetPWFaultStat', '复位功率故障2'),
        ('RFQ:Reset', '真空复位'),

        # 补偿 PV
        ('RFQ:LLRF:Mon02:ForwardPowerComp', 'SSA补偿'),
        ('RFQ:LLRF:Mon02:ReflectedPowerComp', '反射功率补偿'),

        # RF 控制 PV
        ('RFQ:LLRF:Con01:Opr_RFOn', 'RF开关'),
        ('RFQ:LLRF:Con01:pulsecw', '脉冲/CW模式'),
        ('RFQ:LLRF:Con01:AmpCWDrive_Set', 'CW Drive'),
        ('RFQ:LLRF:Con01_RFIn03:Power', '功率'),

        # 真空 PV
        ('RFQ:Vac1', '真空1'),
        ('RFQ:Vac4', '真空4'),
        ('RFQ:Vac8', '真空8'),
    ]

    passed = 0
    failed = 0

    for pv_name, desc in all_pvs:
        ok, result = test_pv(pv_name)
        status = "[OK]" if ok else "[FAIL]"
        print(f"{status} {pv_name:<40} ({desc})")
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"       └─ {result}")

    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")

    if failed > 0:
        print("\n注意: 如果所有 PV 都失败，请确认 sim_ioc.py 已启动")
        sys.exit(1)
    else:
        print("\n所有 PV 连接正常!")
        sys.exit(0)


if __name__ == '__main__':
    main()

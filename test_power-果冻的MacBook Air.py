#!/usr/bin/env python3
"""测试 sim_ioc 的 power 功能 - 使用 asyncio 客户端"""
import asyncio
import caproto.aSYNC

class IOCTester:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.channels = {}

    async def connect(self):
        """连接到 IOC"""
        self.circuit = caproto.aSYNC.ClientCircuit((self.host, self.port))
        await self.circuit.connect()
        print(f"已连接到 {self.host}:{self.port}")

    async def read_pv(self, name):
        """读取 PV"""
        chan = caproto.aSYNC.Channel(name, self.circuit)
        await chan.search()
        await chan.connect()
        data = await chan.read()
        await chan.close()
        return data.data[0]

    async def write_pv(self, name, value):
        """写入 PV"""
        chan = caproto.aSYNC.Channel(name, self.circuit)
        await chan.search()
        await chan.connect()
        await chan.write(value)
        await chan.close()
        print(f"写入 {name} = {value}")

    async def close(self):
        """关闭连接"""
        await self.circuit.close()

async def test_power():
    print("=== RFQ Power 测试 ===\n")

    tester = IOCTester('127.0.0.1', 5064)

    try:
        await tester.connect()

        # 检查当前状态
        print("1. 读取初始状态...")
        rf_on = await tester.read_pv('RFQ:LLRF:Con01:Opr_RFOn')
        pulse_cw = await tester.read_pv('RFQ:LLRF:Con01:pulsecw')
        cw_drive = await tester.read_pv('RFQ:LLRF:Con01:AmpCWDrive_Set')
        pulse_drive = await tester.read_pv('RFQ:LLRF:Con01:AmpPulseDrive_Set')
        power = await tester.read_pv('RFQ:LLRF:Con01_RFIn03:Power')

        print(f"   rf_on = {rf_on}")
        print(f"   pulse_cw = {pulse_cw}")
        print(f"   cw_drive = {cw_drive}")
        print(f"   pulse_drive = {pulse_drive}")
        print(f"   power = {power}")
        print()

        # 步骤1: 设置 drive = 100
        print("2. 设置 cw_drive = 100...")
        await tester.write_pv('RFQ:LLRF:Con01:AmpCWDrive_Set', 100.0)

        # 等待一下让仿真线程更新
        await asyncio.sleep(0.5)

        # 再次检查 power
        print("\n3. 再次读取 power（未开启 RF）...")
        power = await tester.read_pv('RFQ:LLRF:Con01_RFIn03:Power')
        print(f"   power = {power}")
        print()

        # 步骤2: 开启 RF
        print("4. 开启 RF (rf_on = 1)...")
        await tester.write_pv('RFQ:LLRF:Con01:Opr_RFOn', 1)

        # 等待让功率上升
        print("\n5. 等待 2 秒，每 0.3 秒读取一次 power...")
        for i in range(7):
            await asyncio.sleep(0.3)
            power = await tester.read_pv('RFQ:LLRF:Con01_RFIn03:Power')
            print(f"   t={0.3*(i+1):.1f}s: power = {power}")
        print()

        # 测试关闭 RF 后的衰减
        print("6. 关闭 RF (rf_on = 0)，观察功率衰减...")
        await tester.write_pv('RFQ:LLRF:Con01:Opr_RFOn', 0)

        for i in range(7):
            await asyncio.sleep(0.3)
            power = await tester.read_pv('RFQ:LLRF:Con01_RFIn03:Power')
            print(f"   t={0.3*(i+1):.1f}s: power = {power}")
        print()

        print("=== 测试完成 ===")

    finally:
        await tester.close()

if __name__ == '__main__':
    asyncio.run(test_power())

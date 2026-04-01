#!/usr/bin/env python3
"""
集成测试 3.1 - 正常流程 (Happy Path)

TC-INT-01: 完整三段功率老练（脉冲模式, pulse_cw=1）
TC-INT-02: CW 模式完整流程（pulse_cw=0）

运行方式：
    cd <project_root>
    pytest tests/integration/test_happy_path.py -v -s

预计用时：
    TC-INT-01: ~120 s
    TC-INT-02: ~30 s
"""

import os
import sys
import time
import threading
import subprocess
import logging

import pytest
import epics

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from rfq.core.config import Config
from rfq import RFQController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("INT_TEST.3.1")

# ── PV 名称常量 ────────────────────────────────────────────
PV_START       = "RFQ:LLRF:Con01:AutoC_Start"
PV_STATUS      = "RFQ:LLRF:Con01:AutoC_Status"
PV_RF_ON       = "RFQ:LLRF:Con01:Opr_RFOn"
PV_PULSE_CW    = "RFQ:LLRF:Con01:pulsecw"
PV_FREQ_SWEEP  = "RFQ:LLRF:Con01_DAC:FreqSweep_Set"
PV_FREQ_TRACK  = "RFQ:LLRF:Con01:frequency_tracking"
PV_PULSE_TIME  = "RFQ:LLRF:Con01:RFPulseOnTime_Set"
PV_PULSE_DRIVE = "RFQ:LLRF:Con01:AmpPulseDrive_Set"
PV_CW_DRIVE    = "RFQ:LLRF:Con01:AmpCWDrive_Set"

SIM_IOC_SCRIPT = os.path.join(PROJECT_ROOT, "tests", "sim_ioc.py")
CONFIG_FILE    = os.path.join(PROJECT_ROOT, "config.yaml")

STATUS_ALIASES = {
    "IDLE": "IDLE",
    "INIT": "INITIALIZING",
    "INITIALIZING": "INITIALIZING",
    "ADJU": "ADJUSTING_POWER",
    "ADJUSTING_POWER": "ADJUSTING_POWER",
    "WAIT": "WAITING_VACUUM",
    "WAITING_VACUUM": "WAITING_VACUUM",
    "EXPA": "EXPANDING_PULSE",
    "EXPANDING_PULSE": "EXPANDING_PULSE",
    "PAUS": "PAUSED",
    "PAUSED": "PAUSED",
    "COMP": "COMPLETED",
    "COMPLETED": "COMPLETED",
    "ERRO": "ERROR",
    "ERROR": "ERROR",
    "STOP": "STOPPED",
    "STOPPED": "STOPPED",
}


def _decode_status_value(raw):
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip().rstrip("\x00")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="ignore").strip().rstrip("\x00")
    if hasattr(raw, "tolist"):
        arr = raw.tolist()
        if isinstance(arr, list) and arr and isinstance(arr[0], (int, float)):
            chars = []
            for item in arr:
                val = int(item)
                if val == 0:
                    break
                if 32 <= val <= 126:
                    chars.append(chr(val))
            if chars:
                return "".join(chars)
    return str(raw).strip().rstrip("\x00")


def normalize_status(raw):
    decoded = _decode_status_value(raw)
    if not decoded:
        return None
    return STATUS_ALIASES.get(decoded.upper(), decoded.upper())


# ── 辅助类 ────────────────────────────────────────────────

class StatusMonitor:
    """订阅 AutoC_Status PV，记录所有不重复的状态变化"""

    def __init__(self):
        self.history: list = []
        self._lock = threading.Lock()
        self._pv: epics.PV | None = None

    def start(self):
        self._pv = epics.PV(PV_STATUS, auto_monitor=True)
        self._pv.add_callback(self._on_change)

    def _on_change(self, pvname=None, value=None, char_value=None, **kw):
        v = normalize_status(char_value)
        if not v:
            v = normalize_status(value)
        if not v:
            return
        with self._lock:
            if not self.history or self.history[-1] != v:
                self.history.append(v)
                logger.info(f"  [STATUS→] {v}")

    def stop(self):
        if self._pv:
            self._pv.clear_callbacks()
            self._pv.disconnect()
            self._pv = None

    def get_history(self) -> list:
        with self._lock:
            return list(self.history)

    def wait_for(self, status: str, timeout: float) -> bool:
        """阻塞直到 status 出现在历史中，或超时"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if status in self.get_history():
                return True
            time.sleep(0.3)
        return False


# ── 控制器停止机制 ─────────────────────────────────────────

def make_stoppable(controller: RFQController) -> threading.Event:
    """
    向 controller 注入可中断的 _sleep，返回 stop_event。
    设置 stop_event 后，下一次 _sleep 调用会抛出 KeyboardInterrupt，
    controller.run() 捕获后进入 STOPPED 终止状态，线程正常退出。
    """
    stop_event = threading.Event()
    _orig_sleep = controller._sleep

    def _stoppable_sleep(seconds):
        if stop_event.is_set():
            raise KeyboardInterrupt("test teardown signal")
        _orig_sleep(seconds)

    controller._sleep = _stoppable_sleep
    return stop_event


# ── 工具函数 ──────────────────────────────────────────────

def wait_for_ioc_ready(timeout: float = 30) -> bool:
    """轮询直到 sim_ioc 的基准 PV 可读（返回非 None）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if epics.caget(PV_START, timeout=2) is not None:
            return True
        time.sleep(1)
    return False


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture()
def sim_ioc():
    """
    启动 sim_ioc 子进程；yield 后强制终止。
    每个测试函数独立拥有一个干净的 sim_ioc 实例。
    """
    if wait_for_ioc_ready(timeout=2):
        logger.info("检测到已有 sim_ioc，复用外部实例")
        yield None
        return

    proc = subprocess.Popen(
        [sys.executable, SIM_IOC_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"sim_ioc 已启动 (pid={proc.pid})")

    if not wait_for_ioc_ready(timeout=30):
        proc.terminate()
        pytest.fail("sim_ioc 启动超时：PV 未在 30 s 内就绪")

    logger.info("sim_ioc PV 就绪 ✓")
    yield proc

    logger.info("teardown: 终止 sim_ioc")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def controller_env(sim_ioc):
    """
    创建 Config + RFQController，在守护线程中运行。
    teardown 时设置 stop_event，等待线程退出（最多 10 s）。
    """
    config = Config(CONFIG_FILE)
    ctrl = RFQController(config)
    stop_event = make_stoppable(ctrl)

    t = threading.Thread(target=ctrl.run, name="rfq-controller", daemon=True)
    t.start()
    logger.info("controller 线程已启动")

    yield ctrl, stop_event

    logger.info("teardown: 向 controller 发送停止信号")
    stop_event.set()
    t.join(timeout=10)
    if t.is_alive():
        logger.warning("controller 线程在 10 s 内未退出（守护线程，进程结束时自动清理）")


# ══════════════════════════════════════════════════════════
# TC-INT-01: 完整三段功率老练（脉冲模式）
# ══════════════════════════════════════════════════════════

class TestTCINT01:
    """TC-INT-01: 完整三段功率老练 (Happy Path, 脉冲模式 pulse_cw=1)"""

    def test_full_three_segment_pulse_conditioning(self, controller_env):
        ctrl, stop_event = controller_env
        monitor = StatusMonitor()
        monitor.start()

        try:
            # ── 前置验证 ──────────────────────────────────────
            assert epics.caget(PV_PULSE_CW, timeout=3) == 1, \
                "前置条件失败：pulse_cw 应为 1（脉冲模式）"

            initial_pulse_time = epics.caget(PV_PULSE_TIME, timeout=3)
            logger.info(f"初始 RFPulseOnTime_Set = {initial_pulse_time:.4f} s")

            # ── Step 1: 写入 AutoC_Start=1 ───────────────────
            logger.info("写入 AutoC_Start=1，启动老练")
            epics.caput(PV_START, 1)

            # ── Step 2: 验证初始化状态 ────────────────────────
            assert monitor.wait_for("INITIALIZING", timeout=10), \
                "未在 10 s 内观察到 INITIALIZING 状态"
            logger.info("✓ 观察到 INITIALIZING")

            assert monitor.wait_for("ADJUSTING_POWER", timeout=30), \
                "未在 30 s 内进入 ADJUSTING_POWER"
            logger.info("✓ 进入 ADJUSTING_POWER")

            time.sleep(0.5)  # 等待 RF 状态写入稳定

            # ── Step 3: 验证 RF 启动 ─────────────────────────
            rf_on = epics.caget(PV_RF_ON,      timeout=3)
            sweep = epics.caget(PV_FREQ_SWEEP, timeout=3)
            track = epics.caget(PV_FREQ_TRACK, timeout=3)
            logger.info(f"RF 状态: rf_on={rf_on}, freq_sweep={sweep}, freq_tracking={track}")

            assert rf_on == 1, f"RF 应已开启（rf_on={rf_on}）"
            assert sweep == 1, f"freq_sweep 应为 1（实际={sweep}）"
            assert track == 1, f"freq_tracking 应为 1（实际={track}）"
            logger.info("✓ RF 启动验证通过")

            # ── Step 4: 等待老练完成（最多 180 s）────────────
            logger.info("等待老练完成（最多 180 s）…")
            assert monitor.wait_for("COMPLETED", timeout=180), (
                f"未在 180 s 内完成老练\n"
                f"状态历史: {monitor.get_history()}\n"
                f"当前 AutoC_Status: {epics.caget(PV_STATUS, timeout=3)}"
            )
            logger.info("✓ 到达 COMPLETED 状态")

            # ── Step 5: 验证完成后的 PV ──────────────────────
            time.sleep(1.5)  # 等待 _handle_completed() 写入 AutoC_Start=0

            history = monitor.get_history()
            logger.info(f"完整状态历史: {history}")

            # 必须经过 EXPANDING_PULSE
            assert "EXPANDING_PULSE" in history, \
                f"三段老练应至少经过一次 EXPANDING_PULSE，历史: {history}"

            start_pv       = epics.caget(PV_START,      timeout=3)
            rf_on_final    = epics.caget(PV_RF_ON,       timeout=3)
            final_pulse_t  = epics.caget(PV_PULSE_TIME,  timeout=3)

            logger.info(
                f"完成后: AutoC_Start={start_pv}, rf_on={rf_on_final}, "
                f"RFPulseOnTime_Set={final_pulse_t:.4f} s"
            )

            assert start_pv == 0, \
                f"完成后 AutoC_Start 应自动置 0（实际={start_pv}）"
            assert rf_on_final == 1, \
                f"完成后 RF 应保持开启（rf_on={rf_on_final}）"
            assert abs(final_pulse_t - 0.11) < 0.001, (
                f"完成后 RFPulseOnTime_Set 应为 0.11 s "
                f"（实际={final_pulse_t:.4f} s）"
            )

            logger.info("✓ TC-INT-01 全部验证通过")

        finally:
            monitor.stop()


# ══════════════════════════════════════════════════════════
# TC-INT-02: CW 模式完整流程
# ══════════════════════════════════════════════════════════

class TestTCINT02:
    """TC-INT-02: CW 模式完整流程 (pulse_cw=0)"""

    def test_cw_mode_conditioning(self, controller_env):
        ctrl, stop_event = controller_env
        monitor = StatusMonitor()
        monitor.start()

        initial_pulse_time = epics.caget(PV_PULSE_TIME, timeout=3)
        logger.info(f"初始 RFPulseOnTime_Set = {initial_pulse_time:.4f} s")

        try:
            # ── 前置：切换到 CW 模式 ──────────────────────────
            logger.info("设置 pulse_cw=0（CW 模式）")
            epics.caput(PV_PULSE_CW, 0)
            time.sleep(0.5)
            assert epics.caget(PV_PULSE_CW, timeout=3) == 0, \
                "前置条件失败：pulse_cw 应为 0（CW 模式）"

            # ── Step 1: 启动 ──────────────────────────────────
            logger.info("写入 AutoC_Start=1")
            epics.caput(PV_START, 1)

            # ── Step 2: 验证进入 ADJUSTING_POWER ─────────────
            assert monitor.wait_for("ADJUSTING_POWER", timeout=30), \
                "CW 模式未在 30 s 内进入 ADJUSTING_POWER"
            logger.info("✓ 进入 ADJUSTING_POWER")

            # 等待 startup_rf 完成后 drive 稳定
            time.sleep(2)
            cw_drive    = epics.caget(PV_CW_DRIVE,    timeout=3)
            pulse_drive = epics.caget(PV_PULSE_DRIVE, timeout=3)
            logger.info(f"Drive 状态: cw_drive={cw_drive}, pulse_drive={pulse_drive}")

            assert cw_drive > 0, \
                f"CW 模式应使用 cw_drive > 0（实际={cw_drive}）"
            assert pulse_drive == 0, \
                f"CW 模式 pulse_drive 应为 0（实际={pulse_drive}）"
            logger.info("✓ CW Drive 验证通过")

            # ── Step 3: 等待完成（CW 模式单段，最多 60 s）───
            logger.info("等待 CW 模式老练完成（最多 60 s）…")
            assert monitor.wait_for("COMPLETED", timeout=60), (
                f"CW 模式未在 60 s 内完成\n"
                f"状态历史: {monitor.get_history()}"
            )
            logger.info("✓ 到达 COMPLETED")

            # ── Step 4: 验证结果 ──────────────────────────────
            time.sleep(1.5)
            history = monitor.get_history()
            logger.info(f"完整状态历史: {history}")

            # CW 模式不应进入 EXPANDING_PULSE
            assert "EXPANDING_PULSE" not in history, \
                f"CW 模式不应进入 EXPANDING_PULSE，历史: {history}"

            # RFPulseOnTime_Set 不应被修改
            final_pulse_time = epics.caget(PV_PULSE_TIME, timeout=3)
            logger.info(
                f"RFPulseOnTime_Set: 初始={initial_pulse_time:.4f}s, "
                f"最终={final_pulse_time:.4f}s"
            )
            assert abs(final_pulse_time - initial_pulse_time) < 0.001, (
                f"CW 模式不应修改 RFPulseOnTime_Set "
                f"（初始={initial_pulse_time:.4f}s, 最终={final_pulse_time:.4f}s）"
            )

            start_pv = epics.caget(PV_START, timeout=3)
            assert start_pv == 0, \
                f"完成后 AutoC_Start 应自动置 0（实际={start_pv}）"

            logger.info("✓ TC-INT-02 全部验证通过")

        finally:
            monitor.stop()
            # 恢复脉冲模式，避免影响后续测试
            epics.caput(PV_PULSE_CW, 1)
            logger.info("已恢复 pulse_cw=1（脉冲模式）")

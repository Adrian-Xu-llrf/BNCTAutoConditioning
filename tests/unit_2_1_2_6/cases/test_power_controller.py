import pytest

from rfq.controllers.power import PowerController


class DummyConfig:
    def __init__(self):
        self._pvs = {
            "rf.power": "PV:POWER",
            "control.drive_step1": "PV:STEP1",
            "control.drive_step2": "PV:STEP2",
            "control.margin_large": "PV:MARGIN_L",
            "control.margin_small": "PV:MARGIN_S",
        }

    def get_pv(self, key):
        return self._pvs[key]


class FakePVManager:
    def __init__(self, values):
        self.values = dict(values)
        self.put_calls = []

    def get(self, pv_name):
        return self.values.get(pv_name)

    def put(self, pv_name, value):
        self.put_calls.append((pv_name, value))
        self.values[pv_name] = value
        return True


@pytest.fixture
def cfg():
    return DummyConfig()


def _build_controller(cfg, monkeypatch, values):
    ctl = PowerController(cfg)
    ctl.pv_manager = FakePVManager(values)
    monkeypatch.setattr("rfq.controllers.power.time.sleep", lambda _: None)
    return ctl


def test_u_p_01_within_small_margin(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 10.0,
            "PV:DRIVE": 120.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 1.0,
        },
    )
    ok, _ = ctl.adjust("PV:DRIVE", 10.0)
    assert ok is True
    assert ctl.pv_manager.put_calls == []


def test_u_p_02_low_power_large_error_use_step1(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 5.0,
            "PV:DRIVE": 100.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 1.0,
        },
    )
    ok, _ = ctl.adjust("PV:DRIVE", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("PV:DRIVE", 110.0)


def test_u_p_03_low_power_small_error_use_step2(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 9.0,
            "PV:DRIVE": 100.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 0.2,
        },
    )
    ok, _ = ctl.adjust("PV:DRIVE", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("PV:DRIVE", 102.0)


def test_u_p_04_high_power_large_error_decrease_step1(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 15.0,
            "PV:DRIVE": 100.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 1.0,
        },
    )
    ok, _ = ctl.adjust("PV:DRIVE", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("PV:DRIVE", 90.0)


def test_u_p_05_iteration_count_increments(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 7.0,
            "PV:DRIVE": 100.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 0.5,
        },
    )
    ctl.adjust("PV:DRIVE", 10.0)
    ctl.pv_manager.values["PV:POWER"] = 8.0
    ctl.adjust("PV:DRIVE", 10.0)
    assert ctl.get_iteration_count() == 2


@pytest.mark.xfail(reason="当前实现未做Drive下限保护", strict=False)
def test_u_p_06_drive_lower_bound_protection(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "PV:POWER": 15.0,
            "PV:DRIVE": 0.0,
            "PV:STEP1": 10.0,
            "PV:STEP2": 2.0,
            "PV:MARGIN_L": 3.0,
            "PV:MARGIN_S": 1.0,
        },
    )
    ok, _ = ctl.adjust("PV:DRIVE", 10.0)
    assert ok is False
    assert ctl.pv_manager.values["PV:DRIVE"] >= 0.0

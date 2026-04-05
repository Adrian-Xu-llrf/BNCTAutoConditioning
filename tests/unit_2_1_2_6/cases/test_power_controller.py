import pytest

from rfq.controllers.power import PowerController


class FakePVManager:
    def __init__(self, values):
        self.values = dict(values)
        self.put_calls = []

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.put_calls.append((key, value))
        self.values[key] = value
        return True


class DummyConfig:
    pass


@pytest.fixture
def cfg():
    return DummyConfig()


def _build_controller(cfg, monkeypatch, values):
    pv_mgr = FakePVManager(values)
    ctl = PowerController(cfg, pv_mgr)
    monkeypatch.setattr("rfq.controllers.power.time.sleep", lambda _: None)
    return ctl


def test_u_p_01_within_small_margin(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 10.0,
            "rf.pulse_drive": 120.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 1.0,
        },
    )
    ok, _ = ctl.adjust("rf.pulse_drive", 10.0)
    assert ok is True
    assert ctl.pv_manager.put_calls == []


def test_u_p_02_low_power_large_error_use_step1(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 5.0,
            "rf.pulse_drive": 100.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 1.0,
        },
    )
    ok, _ = ctl.adjust("rf.pulse_drive", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_drive", 110.0)


def test_u_p_03_low_power_small_error_use_step2(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 9.0,
            "rf.pulse_drive": 100.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 0.2,
        },
    )
    ok, _ = ctl.adjust("rf.pulse_drive", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_drive", 102.0)


def test_u_p_04_high_power_large_error_decrease_step1(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 15.0,
            "rf.pulse_drive": 100.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 1.0,
        },
    )
    ok, _ = ctl.adjust("rf.pulse_drive", 10.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_drive", 90.0)


def test_u_p_05_iteration_count_increments(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 7.0,
            "rf.pulse_drive": 100.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 0.5,
        },
    )
    ctl.adjust("rf.pulse_drive", 10.0)
    ctl.pv_manager.values["rf.power"] = 8.0
    ctl.adjust("rf.pulse_drive", 10.0)
    assert ctl.get_iteration_count() == 2


@pytest.mark.xfail(reason="当前实现未做Drive下限保护", strict=False)
def test_u_p_06_drive_lower_bound_protection(cfg, monkeypatch):
    ctl = _build_controller(
        cfg,
        monkeypatch,
        {
            "rf.power": 15.0,
            "rf.pulse_drive": 0.0,
            "control.drive_step1": 10.0,
            "control.drive_step2": 2.0,
            "control.margin_large": 3.0,
            "control.margin_small": 1.0,
        },
    )
    ok, _ = ctl.adjust("rf.pulse_drive", 10.0)
    assert ok is False
    assert ctl.pv_manager.values["rf.pulse_drive"] >= 0.0

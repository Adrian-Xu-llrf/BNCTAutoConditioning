from rfq.controllers.pulse import PulseController


class DummyConfig:
    def __init__(self, reduce_power=False):
        self.loop = {"reduce_power_before_expand": reduce_power}


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


def _build_controller(monkeypatch, reduce_power, values):
    pv_mgr = FakePVManager(values)
    ctl = PulseController(DummyConfig(reduce_power=reduce_power), pv_mgr)
    monkeypatch.setattr("rfq.controllers.pulse.time.sleep", lambda _: None)
    return ctl


def test_u_pl_01_already_at_end(monkeypatch):
    ctl = _build_controller(monkeypatch, False, {"rf.pulse_time": 0.110})
    ok, _ = ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=110.0, pulse_step=2.0)
    assert ok is True
    assert ctl.pv_manager.put_calls == []


def test_u_pl_02_expand_normally(monkeypatch):
    ctl = _build_controller(monkeypatch, False, {"rf.pulse_time": 0.100})
    ok, _ = ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=110.0, pulse_step=2.0)
    assert ok is False
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_time", 0.102)


def test_u_pl_03_no_reduce_power_mode(monkeypatch):
    ctl = _build_controller(monkeypatch, False, {"rf.pulse_time": 0.100, "rf.pulse_drive": 150.0})
    ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=110.0, pulse_step=2.0)
    assert ("rf.pulse_drive", 100.0) not in ctl.pv_manager.put_calls
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_time", 0.102)


def test_u_pl_04_reduce_power_before_expand(monkeypatch):
    ctl = _build_controller(
        monkeypatch,
        True,
        {
            "rf.pulse_time": 0.100,
            "rf.pulse_drive": 120.0,
            "control.drive_step1": 10.0,
        },
    )
    ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=110.0, pulse_step=2.0)
    drive_writes = [call for call in ctl.pv_manager.put_calls if call[0] == "rf.pulse_drive"]
    assert drive_writes
    assert drive_writes[-1] == ("rf.pulse_drive", 100.0)
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_time", 0.102)


def test_u_pl_05_over_end_treated_as_done(monkeypatch):
    ctl = _build_controller(monkeypatch, False, {"rf.pulse_time": 0.115})
    ok, _ = ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=110.0, pulse_step=2.0)
    assert ok is True
    assert ctl.pv_manager.put_calls == []


def test_u_pl_06_unit_conversion_seconds_to_ms(monkeypatch):
    ctl = _build_controller(monkeypatch, False, {"rf.pulse_time": 0.100})
    ctl.expand("rf.pulse_drive", init_drive=100.0, pulse_end=105.0, pulse_step=1.0)
    assert ctl.pv_manager.put_calls[-1] == ("rf.pulse_time", 0.101)

from rfq.controllers.vacuum import VacuumChecker


class DummyConfig:
    def __init__(self, threshold=5e-5):
        self.vacuum = {"threshold": threshold}
        self.pv = {"vacuum": [f"PV:VAC{i}" for i in range(1, 9)]}


class FakePV:
    values = {}

    def __init__(self, name):
        self.name = name
        self.callbacks = []
        self.cleared = False

    def add_callback(self, cb, **kwargs):
        self.callbacks.append((cb, kwargs))

    def clear_callbacks(self):
        self.cleared = True
        self.callbacks = []

    def get(self):
        return self.values.get(self.name)


def _build_checker(monkeypatch, initial_values, threshold=5e-5):
    FakePV.values = dict(initial_values)
    monkeypatch.setattr("rfq.controllers.vacuum.epics.PV", lambda name: FakePV(name))
    return VacuumChecker(DummyConfig(threshold=threshold))


def test_u_v_01_fail_safe_without_callbacks(monkeypatch):
    c = _build_checker(monkeypatch, initial_values={})
    ok, worst, pv = c.is_vacuum_ok()
    assert ok is False
    assert worst == float("inf")
    assert pv is None


def test_u_v_02_all_normal(monkeypatch):
    vals = {f"PV:VAC{i}": 1e-6 for i in range(1, 9)}
    c = _build_checker(monkeypatch, initial_values=vals)
    ok, worst, _ = c.is_vacuum_ok()
    assert ok is True
    assert worst == 1e-6


def test_u_v_03_single_over_threshold(monkeypatch):
    vals = {f"PV:VAC{i}": 1e-6 for i in range(1, 9)}
    vals["PV:VAC3"] = 1e-3
    c = _build_checker(monkeypatch, initial_values=vals)
    ok, worst, pv = c.is_vacuum_ok()
    assert ok is False
    assert worst == 1e-3
    assert pv == "PV:VAC3"


def test_u_v_04_pick_worst_value(monkeypatch):
    vals = {f"PV:VAC{i}": 1e-6 for i in range(1, 9)}
    vals["PV:VAC2"] = 3e-5
    vals["PV:VAC6"] = 6e-5
    c = _build_checker(monkeypatch, initial_values=vals)
    ok, worst, pv = c.is_vacuum_ok()
    assert ok is False
    assert worst == 6e-5
    assert pv == "PV:VAC6"


def test_u_v_05_recover_to_normal(monkeypatch):
    vals = {f"PV:VAC{i}": 1e-6 for i in range(1, 9)}
    vals["PV:VAC3"] = 1e-3
    c = _build_checker(monkeypatch, initial_values=vals)
    c._on_vacuum_change(pvname="PV:VAC3", value=1e-6, pv_name="PV:VAC3")
    ok, worst, _ = c.is_vacuum_ok()
    assert ok is True
    assert worst == 1e-6


def test_u_v_06_threshold_boundary_is_not_ok(monkeypatch):
    vals = {f"PV:VAC{i}": 1e-6 for i in range(1, 9)}
    vals["PV:VAC5"] = 5e-5
    c = _build_checker(monkeypatch, initial_values=vals, threshold=5e-5)
    ok, worst, pv = c.is_vacuum_ok()
    assert ok is False
    assert worst == 5e-5
    assert pv == "PV:VAC5"

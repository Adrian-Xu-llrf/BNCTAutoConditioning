from rfq.controllers.vacuum import VacuumChecker


class DummyConfig:
    def __init__(self, threshold=5e-5):
        self.vacuum = {"threshold": threshold}
        self.pv = {"vacuum": [f"PV:VAC{i}" for i in range(1, 9)]}


class FakePV:
    def __init__(self, name):
        self.name = name
        self.callbacks = []
        self.cleared = False

    def add_callback(self, cb, **kwargs):
        self.callbacks.append((cb, kwargs))

    def clear_callbacks(self):
        self.cleared = True
        self.callbacks = []


class FakePVManager:
    def __init__(self, pv_names, initial_values):
        self._pv_objects = {}
        self._pv_names = {}
        self._values = {}
        for i, pv_name in enumerate(pv_names):
            key = f"vacuum.{i}"
            self._pv_objects[key] = FakePV(pv_name)
            self._pv_names[key] = pv_name
            self._values[key] = initial_values.get(pv_name)

    def get_pv_object(self, pv_key):
        return self._pv_objects.get(pv_key)

    def get_pv_name(self, pv_key):
        return self._pv_names.get(pv_key)

    def get(self, pv_key):
        return self._values.get(pv_key)


def _build_checker(monkeypatch, initial_values, threshold=5e-5):
    config = DummyConfig(threshold=threshold)
    pv_mgr = FakePVManager(config.pv['vacuum'], initial_values)
    return VacuumChecker(config, pv_mgr)


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
    c._on_vacuum_change(pvname="PV:VAC3", value=1e-6, pv_key="vacuum.2")
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

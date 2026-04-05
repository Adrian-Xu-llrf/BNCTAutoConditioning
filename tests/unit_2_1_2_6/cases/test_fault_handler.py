import threading

from rfq.controllers.fault import FaultHandler


class DummyConfig:
    def __init__(self, max_faults=20):
        self.loop = {"max_faults": max_faults}


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
    def __init__(self):
        self.put_calls = []
        self.get_map = {}
        self._pv_objects = {}

    def put(self, pv_key, value):
        self.put_calls.append((pv_key, value))
        return True

    def get(self, pv_key):
        return self.get_map.get(pv_key, 1)

    def get_pv_object(self, pv_key):
        return self._pv_objects.get(pv_key)

    def get_pv_name(self, pv_key):
        return f"PV:{pv_key.upper()}"


FAULT_PV_KEYS = [
    'fault.arc',
    'fault.VacInterlock',
    'fault.interlock2',
    'fault.di4',
]


def _build_handler(monkeypatch, max_faults=20):
    pv_mgr = FakePVManager()
    for key in FAULT_PV_KEYS:
        pv_mgr._pv_objects[key] = FakePV(key)
    h = FaultHandler(DummyConfig(max_faults=max_faults), pv_mgr)
    return h


def _trigger_callback(h, key_index, value):
    key = FAULT_PV_KEYS[key_index]
    pv_obj = h.pv_manager.get_pv_object(key)
    for cb, kwargs in pv_obj.callbacks:
        cb(pvname=pv_obj.name, value=value, pv_key=key)


def test_u_f_01_fault_count_accumulates(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    _trigger_callback(h, 0, 0)
    _trigger_callback(h, 1, 0)
    _trigger_callback(h, 2, 0)
    assert h.get_fault_count() == 3


def test_u_f_02_fault_exceeded_at_limit(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=3)
    for i in range(3):
        _trigger_callback(h, 0, 0)
    assert h.is_fault_exceeded() is True


def test_u_f_03_not_exceeded_below_limit(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=5)
    for i in range(4):
        _trigger_callback(h, 0, 0)
    assert h.is_fault_exceeded() is False


def test_u_f_04_reset_fault_count(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=5)
    _trigger_callback(h, 0, 0)
    _trigger_callback(h, 0, 0)
    h.reset_fault_count()
    assert h.get_fault_count() == 0
    assert h.is_fault_exceeded() is False


def test_u_f_05_reset_all_faults_sequence(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.reset_all_faults()
    seq = [pv for pv, _ in h.pv_manager.put_calls]
    assert seq == [
        "fault.VacReset",
        "fault.VacReset",
        "fault.reset_interlock",
        "fault.reset_interlock",
        "fault.ResetPWFaultStat1",
        "fault.ResetPWFaultStat1",
        "fault.ResetPWFaultStat2",
        "fault.ResetPWFaultStat2",
    ]


def test_u_f_06_check_faults_all_ok(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.pv_manager.get_map = {
        "fault.arc": 1,
        "fault.VacInterlock": 1,
        "fault.interlock2": 1,
        "fault.di4": 1,
    }
    assert h.check_fault_status() is True


def test_u_f_07_check_faults_still_fault(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.pv_manager.get_map = {
        "fault.arc": 0,
        "fault.VacInterlock": 1,
        "fault.interlock2": 1,
        "fault.di4": 1,
    }
    assert h.check_fault_status() is False


def test_u_f_08_cleanup_clears_callbacks(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    pvs = [h.pv_manager.get_pv_object(k) for k in FAULT_PV_KEYS]
    assert any(p.callbacks for p in pvs)
    h.cleanup()
    assert all(p.cleared for p in pvs)
    assert all(not p.callbacks for p in pvs)


def test_u_f_09_last_fault_type(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    assert h.get_last_fault_type() is None
    _trigger_callback(h, 0, 0)
    assert h.get_last_fault_type() == "Arc"
    _trigger_callback(h, 1, 0)
    assert h.get_last_fault_type() == "VacInterlock"

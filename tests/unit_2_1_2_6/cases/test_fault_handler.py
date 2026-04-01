import threading

from rfq.controllers.fault import FaultHandler


class DummyConfig:
    def __init__(self, max_faults=20):
        self.loop = {"max_faults": max_faults}
        self._pvs = {
            "fault.arc": "PV:ARC",
            "fault.VacInterlock": "PV:VAC_INTERLOCK",
            "fault.interlock2": "PV:INTERLOCK2",
            "fault.di4": "PV:DI4",
            "fault.VacReset": "PV:VAC_RESET",
            "fault.reset_interlock": "PV:RESET_INTERLOCK",
            "fault.ResetPWFaultStat1": "PV:RESET_PW1",
            "fault.ResetPWFaultStat2": "PV:RESET_PW2",
        }

    def get_pv(self, key):
        return self._pvs[key]


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

    def put(self, pv_name, value):
        self.put_calls.append((pv_name, value))
        return True

    def get(self, pv_name):
        return self.get_map.get(pv_name, 1)


def _build_handler(monkeypatch, max_faults=20):
    monkeypatch.setattr("rfq.controllers.fault.epics.PV", lambda name: FakePV(name))
    monkeypatch.setattr("rfq.controllers.fault.time.sleep", lambda _: None)
    h = FaultHandler(DummyConfig(max_faults=max_faults))
    h.pv_manager = FakePVManager()
    return h


def test_u_f_01_fault_count_accumulates(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.record_fault()
    h.record_fault()
    h.record_fault()
    assert h.get_fault_count() == 3


def test_u_f_02_fault_exceeded_at_limit(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=3)
    for _ in range(3):
        h.record_fault()
    assert h.is_fault_exceeded() is True


def test_u_f_03_not_exceeded_below_limit(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=5)
    for _ in range(4):
        h.record_fault()
    assert h.is_fault_exceeded() is False


def test_u_f_04_reset_fault_count(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=5)
    h.record_fault()
    h.record_fault()
    h.reset_fault_count()
    assert h.get_fault_count() == 0
    assert h.is_fault_exceeded() is False


def test_u_f_05_recovery_order(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h._handle_fault("Arc")
    seq = [pv for pv, _ in h.pv_manager.put_calls]
    assert seq == [
        "PV:VAC_RESET",
        "PV:VAC_RESET",
        "PV:RESET_INTERLOCK",
        "PV:RESET_INTERLOCK",
        "PV:RESET_PW1",
        "PV:RESET_PW1",
        "PV:RESET_PW2",
        "PV:RESET_PW2",
    ]


def test_u_f_06_check_faults_cleared(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.pv_manager.get_map = {
        "PV:ARC": 1,
        "PV:VAC_INTERLOCK": 1,
        "PV:INTERLOCK2": 1,
        "PV:DI4": 1,
    }
    h._check_fault_status("Arc")
    assert True


def test_u_f_07_recovery_failure_handled(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    h.pv_manager.get_map = {
        "PV:ARC": 0,
        "PV:VAC_INTERLOCK": 1,
        "PV:INTERLOCK2": 1,
        "PV:DI4": 1,
    }
    h._check_fault_status("Arc")
    assert True


def test_u_f_08_cleanup_clears_callbacks(monkeypatch):
    h = _build_handler(monkeypatch, max_faults=10)
    pvs = [h.pv_arc, h.pv_vac_interlock, h.pv_interlock2, h.pv_di4]
    assert any(p.callbacks for p in pvs)
    h.cleanup()
    assert all(p.cleared for p in pvs)
    assert all(not p.callbacks for p in pvs)

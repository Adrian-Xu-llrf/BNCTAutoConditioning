import threading

from rfq.core.controller import RFQController


class DummyConfig:
    def __init__(self):
        self.loop = {
            "interval": 0.1,
            "max_faults": 20,
            "max_iterations": 1000,
            "rf_startup": {"max_retry": 3, "retry_interval": 1},
        }
        self._pvs = {
            "control.current_target_power": "PV:CURRENT_TARGET",
            "rf.pulse_time": "PV:PULSE_TIME",
            "control.current_pulse": "PV:CURRENT_PULSE",
            "control.pulse_drop": "PV:PULSE_DROP",
            "control.status": "PV:STATUS",
        }

    def get(self, *keys, default=None):
        current = {"loop": self.loop}
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return default
        return default if current is None else current

    def get_pv(self, path):
        return self._pvs[path]


class FakePVManager:
    def __init__(self):
        self.get_values = {"PV:PULSE_DROP": 20.0}
        self.put_calls = []

    def get(self, pv_name):
        return self.get_values.get(pv_name)

    def put(self, pv_name, value):
        self.put_calls.append((pv_name, value))
        self.get_values[pv_name] = value
        return True

    def safe_status(self, text):
        return text


class FakeFaultHandler:
    instances = []

    def __init__(self, _config):
        self.fault_count = 0
        self.fault_exceeded = False
        self.cleanup_called = False
        self.reset_called = False
        self.lock = threading.Lock()
        FakeFaultHandler.instances.append(self)

    def get_fault_count(self):
        return self.fault_count

    def is_fault_exceeded(self):
        return self.fault_exceeded

    def reset_fault_count(self):
        self.reset_called = True
        self.fault_count = 0
        self.fault_exceeded = False

    def cleanup(self):
        self.cleanup_called = True


class FakeVacuumChecker:
    instances = []

    def __init__(self, _config):
        self.cleanup_called = False
        FakeVacuumChecker.instances.append(self)

    def cleanup(self):
        self.cleanup_called = True


class FakePowerController:
    def __init__(self, _config):
        self.reset_count = 0

    def reset_iteration_count(self):
        self.reset_count += 1


class FakePulseController:
    def __init__(self, _config):
        pass


def _build_controller(monkeypatch):
    FakeFaultHandler.instances = []
    FakeVacuumChecker.instances = []
    monkeypatch.setattr("rfq.core.controller.FaultHandler", FakeFaultHandler)
    monkeypatch.setattr("rfq.core.controller.VacuumChecker", FakeVacuumChecker)
    monkeypatch.setattr("rfq.core.controller.PowerController", FakePowerController)
    monkeypatch.setattr("rfq.core.controller.PulseController", FakePulseController)

    c = RFQController(DummyConfig(), pv_manager=FakePVManager())
    return c


def test_u_r_01_manual_reset_clear_faults(monkeypatch):
    c = _build_controller(monkeypatch)
    c.power_targets = [10.0, 20.0]
    c.target_index = 1
    c.original_pulse_start = 100.0
    c.pulse_start = 120.0
    c.fault_handler.fault_count = 5
    old_fh = c.fault_handler
    old_vc = c.vacuum_checker

    c.reset(clear_faults=True)

    assert c.target_index == 0
    assert c.pulse_start == 100.0
    assert old_fh.reset_called is True
    assert old_fh.cleanup_called is True
    assert old_vc.cleanup_called is True
    assert any(call == ("PV:CURRENT_TARGET", 10.0) for call in c.pv_manager.put_calls)


def test_u_r_02_auto_reset_keep_faults_and_drop_pulse(monkeypatch):
    c = _build_controller(monkeypatch)
    c.power_targets = [10.0, 20.0]
    c.target_index = 1
    c.original_pulse_start = 100.0
    c.pulse_start = 140.0
    c.fault_handler.fault_count = 3
    c.fault_handler.fault_exceeded = False

    c.reset(clear_faults=False)

    assert c.target_index == 1
    assert c.pulse_start == 120.0
    assert c.fault_handler.get_fault_count() == 3
    assert c.fault_handler.is_fault_exceeded() is False


def test_u_r_03_pulse_start_floor_is_original(monkeypatch):
    c = _build_controller(monkeypatch)
    c.original_pulse_start = 100.0
    c.pulse_start = 105.0
    c.pv_manager.get_values["PV:PULSE_DROP"] = 20.0

    c.reset(clear_faults=False)

    assert c.pulse_start == 100.0


def test_u_r_04_reset_rebuilds_subcontrollers(monkeypatch):
    c = _build_controller(monkeypatch)
    old_fh = c.fault_handler
    old_vc = c.vacuum_checker

    c.reset(clear_faults=True)

    assert c.fault_handler is not old_fh
    assert c.vacuum_checker is not old_vc
    assert old_fh.cleanup_called is True
    assert old_vc.cleanup_called is True

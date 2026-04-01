from rfq.core.config import Config


def _write_config(path, max_faults):
    path.write_text(
        f"""vacuum:
  threshold: 5.0e-5
loop:
  max_faults: {max_faults}
pv:
  rf:
    pulse_drive: 'RFQ:LLRF:Con01:AmpPulseDrive_Set'
""",
        encoding="utf-8",
    )


def test_u_c_01_nested_get(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    _write_config(cfg_file, 20)
    cfg = Config(str(cfg_file))
    assert cfg.get("loop", "max_faults") == 20


def test_u_c_02_missing_path_default(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    _write_config(cfg_file, 20)
    cfg = Config(str(cfg_file))
    assert cfg.get("loop", "not_exists", default=123) == 123


def test_u_c_03_get_pv(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    _write_config(cfg_file, 20)
    cfg = Config(str(cfg_file))
    assert cfg.get_pv("rf.pulse_drive") == "RFQ:LLRF:Con01:AmpPulseDrive_Set"


def test_u_c_04_reload_reflects_file_change(tmp_path):
    cfg_file = tmp_path / "cfg.yaml"
    _write_config(cfg_file, 20)
    cfg = Config(str(cfg_file))
    _write_config(cfg_file, 3)
    cfg.reload()
    assert cfg.get("loop", "max_faults") == 3

import pytest
from nff import config as cfg_module


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect config paths to tmp_path so tests never touch ~/.nff/config.json."""
    cfg_dir = tmp_path / ".nff"
    monkeypatch.setattr(cfg_module, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", cfg_dir / "config.json")
    return cfg_dir

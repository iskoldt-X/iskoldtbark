import json

import pytest

from iskoldtbark.config import ConfigManager

BARK_ENV_VARS = [
    "BARK_DEVICE_KEY",
    "BARK_SERVER_URL",
    "BARK_ENCRYPTION_KEY",
    "BARK_ENCRYPTION_ALGO",
    "BARK_ENCRYPTION_IV",
    "BARK_USER_NICKNAME",
]


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Redirect ConfigManager to a temp dir and clear all BARK_* env vars."""
    global_dir = tmp_path / ".iskoldtbark"
    monkeypatch.setattr(ConfigManager, "GLOBAL_CONFIG_DIR", global_dir)
    monkeypatch.setattr(ConfigManager, "GLOBAL_CONFIG_FILE", global_dir / "config.json")
    monkeypatch.setattr(ConfigManager, "LOCAL_CONFIG_FILE", tmp_path / ".iskoldtbark.json")
    for var in BARK_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return ConfigManager


def write_global_raw(cm, data):
    """Write a raw config dict (legacy or v1) to the isolated global file."""
    cm.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(cm.GLOBAL_CONFIG_FILE, "w") as f:
        json.dump(data, f)

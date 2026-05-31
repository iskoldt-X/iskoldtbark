import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .crypto import CryptoAlgorithm, EncryptionConfig
from .exceptions import BarkValidationError


@dataclass
class BarkConfig:
    """Holds the loaded configuration for the Bark client."""

    device_key: str
    server_url: str
    encryption_config: Optional[EncryptionConfig] = None


class ConfigManager:
    GLOBAL_CONFIG_DIR = Path.home() / ".iskoldtbark"
    GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"
    LOCAL_CONFIG_FILE = Path.cwd() / ".iskoldtbark.json"

    @classmethod
    def load(cls) -> BarkConfig:
        """
        Loads configuration using a 3-tier cascade:
        1. Environment Variables (Highest Priority)
        2. Local Config (./.iskoldtbark.json)
        3. Global Config (~/.iskoldtbark/config.json)
        """
        config_data = {}

        # 3. Load Global
        if cls.GLOBAL_CONFIG_FILE.exists():
            try:
                with open(cls.GLOBAL_CONFIG_FILE, "r") as f:
                    config_data.update(json.load(f))
            except Exception:
                pass

        # 2. Load Local (Overrides Global)
        if cls.LOCAL_CONFIG_FILE.exists():
            try:
                with open(cls.LOCAL_CONFIG_FILE, "r") as f:
                    config_data.update(json.load(f))
            except Exception:
                pass

        # 1. Load Env Vars (Overrides Everything)
        device_key = os.environ.get("BARK_DEVICE_KEY", config_data.get("device_key"))
        server_url = os.environ.get(
            "BARK_SERVER_URL", config_data.get("server_url", "https://api.day.app")
        )

        encryption_key = os.environ.get("BARK_ENCRYPTION_KEY", config_data.get("encryption_key"))
        encryption_algo_str = os.environ.get(
            "BARK_ENCRYPTION_ALGO", config_data.get("encryption_algo", "AES_256_GCM")
        )
        encryption_iv = os.environ.get("BARK_ENCRYPTION_IV", config_data.get("encryption_iv"))

        if not device_key:
            raise BarkValidationError(
                "Bark device key is missing. Please set BARK_DEVICE_KEY or run `iskoldtbark init`."
            )

        encryption_config = None
        if encryption_key:
            algo = CryptoAlgorithm(encryption_algo_str)
            key_bytes = encryption_key.encode("utf-8")
            iv_bytes = encryption_iv.encode("utf-8") if encryption_iv else None
            encryption_config = EncryptionConfig(key=key_bytes, algorithm=algo, iv=iv_bytes)

        return BarkConfig(
            device_key=device_key, server_url=server_url, encryption_config=encryption_config
        )

    @classmethod
    def save_global(
        cls, device_key: str, encryption_key: str, algorithm: str, iv: Optional[str] = None
    ):
        """Saves a new global configuration."""
        cls.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "device_key": device_key,
            "encryption_key": encryption_key,
            "encryption_algo": algorithm,
        }
        if iv:
            data["encryption_iv"] = iv

        with open(cls.GLOBAL_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)

import json

import pytest
from conftest import write_global_raw

from iskoldtbark import (
    BarkClient,
    BarkConfigError,
    CryptoAlgorithm,
    MultiUserConfig,
    UserConfig,
    make_encryption_config,
)
from iskoldtbark.exceptions import BarkSecurityWarning, BarkValidationError


def test_migration_preserves_all_fields(isolated_config):
    cm = isolated_config
    write_global_raw(
        cm,
        {
            "device_key": "DEV123",
            "server_url": "https://bark.example.com",
            "encryption_key": "k" * 32,
            "encryption_algo": "AES_256_GCM",
            "encryption_iv": None,
        },
    )
    config = cm.load_multi()

    assert config.default_user == "default"
    user = config.get_user("default")
    assert user.device_key == "DEV123"
    # server_url must be preserved, not hardcoded back to the public default.
    assert user.server_url == "https://bark.example.com"
    assert user.encryption is not None
    assert user.encryption.algorithm == CryptoAlgorithm.AES_256_GCM


def test_migration_is_non_destructive_on_read(isolated_config):
    cm = isolated_config
    legacy = {
        "device_key": "DEV",
        "server_url": "https://x",
        "encryption_key": "k" * 32,
        "encryption_algo": "AES_256_GCM",
    }
    write_global_raw(cm, legacy)

    cm.load_multi()

    with open(cm.GLOBAL_CONFIG_FILE) as f:
        on_disk = json.load(f)
    assert on_disk == legacy
    assert "version" not in on_disk
    assert cm.is_legacy_on_disk()


def test_migration_with_static_cbc_iv_roundtrips(isolated_config):
    cm = isolated_config
    write_global_raw(
        cm,
        {
            "device_key": "DEV",
            "encryption_key": "k" * 16,
            "encryption_algo": "AES_128_CBC",
            "encryption_iv": "0123456789abcdef",
        },
    )
    enc = cm.load_multi().get_user("default").encryption
    assert enc.algorithm == CryptoAlgorithm.AES_128_CBC
    assert enc.iv == b"0123456789abcdef"
    assert len(enc.iv) == 16


def test_wrong_length_static_iv_rejected():
    # CBC requires exactly 16-byte static IV.
    with pytest.raises(BarkConfigError):
        make_encryption_config("k" * 16, "AES_128_CBC", "short")
    # CBC rejects 12-byte IV.
    with pytest.raises(BarkConfigError):
        make_encryption_config("k" * 16, "AES_128_CBC", "000000000000")
    # GCM rejects 5-byte IV.
    with pytest.raises(BarkConfigError):
        make_encryption_config("k" * 32, "AES_256_GCM", "short")


def test_gcm_with_12char_static_iv_accepted():
    # GCM now accepts 12-byte static IV (previously rejected).
    with pytest.warns(BarkSecurityWarning):
        cfg = make_encryption_config("k" * 32, "AES_256_GCM", "000000000000")
    assert cfg.algorithm == CryptoAlgorithm.AES_256_GCM
    assert cfg.iv == b"000000000000"


def test_gcm_with_16char_static_iv_accepted():
    # A 16-byte static IV with GCM was always accepted; keep it non-breaking.
    with pytest.warns(BarkSecurityWarning):
        cfg = make_encryption_config("k" * 32, "AES_256_GCM", "0123456789abcdef")
    assert cfg.algorithm == CryptoAlgorithm.AES_256_GCM
    assert cfg.iv == b"0123456789abcdef"


def test_gcm_static_iv_config_loads(isolated_config):
    # A legacy/env config with GCM + a 16-byte static IV must still load (no break).
    cm = isolated_config
    write_global_raw(
        cm,
        {
            "device_key": "DEV",
            "encryption_key": "k" * 32,
            "encryption_algo": "AES_256_GCM",
            "encryption_iv": "0123456789abcdef",
        },
    )
    with pytest.warns(BarkSecurityWarning):
        enc = cm.load_multi().get_user("default").encryption
    assert enc.algorithm == CryptoAlgorithm.AES_256_GCM
    assert enc.iv == b"0123456789abcdef"


def test_cross_tier_encryption_algo_inherited(isolated_config, monkeypatch):
    # Global sets CBC; env overrides only the key. The algorithm must stay CBC
    # (inherited from the lower tier), not silently switch to the GCM default.
    cm = isolated_config
    write_global_raw(
        cm,
        {
            "device_key": "DEV",
            "encryption_key": "k" * 16,
            "encryption_algo": "AES_128_CBC",
            "encryption_iv": "0123456789abcdef",
        },
    )
    monkeypatch.setenv("BARK_ENCRYPTION_KEY", "c" * 16)
    enc = cm.load_multi().get_user("default").encryption
    assert enc.algorithm == CryptoAlgorithm.AES_128_CBC  # inherited from global
    assert enc.key == b"cccccccccccccccc"  # overridden by env
    assert enc.iv == b"0123456789abcdef"  # inherited from global


def test_env_overrides_only_default_user(isolated_config, monkeypatch):
    cm = isolated_config
    config = MultiUserConfig()
    config.add_user(UserConfig("phone", "PHONE_KEY"), make_default=True)
    config.add_user(UserConfig("laptop", "LAPTOP_KEY"))
    cm.save_multi(config)

    monkeypatch.setenv("BARK_DEVICE_KEY", "ENV_OVERRIDE")
    loaded = cm.load_multi()
    assert loaded.get_user("phone").device_key == "ENV_OVERRIDE"
    assert loaded.get_user("laptop").device_key == "LAPTOP_KEY"


def test_save_load_roundtrip(isolated_config):
    cm = isolated_config
    config = MultiUserConfig()
    config.add_user(
        UserConfig("phone", "PK", encryption=make_encryption_config("k" * 32, "AES_256_GCM")),
        make_default=True,
    )
    config.add_user(
        UserConfig(
            "laptop",
            "LK",
            encryption=make_encryption_config("c" * 16, "AES_128_CBC", "0123456789abcdef"),
        )
    )
    config.create_group("work", "work devices")
    config.add_user_to_group("phone", "work")
    config.add_user_to_group("laptop", "work")
    cm.save_multi(config)

    loaded = cm.load_multi()
    assert set(loaded.users) == {"phone", "laptop"}
    assert loaded.default_user == "phone"
    assert loaded.get_group("work").members == ["phone", "laptop"]
    assert loaded.get_user("laptop").encryption.iv == b"0123456789abcdef"


def test_remove_user_strips_group_membership_and_reassigns_default():
    config = MultiUserConfig()
    config.add_user(UserConfig("a", "AK"), make_default=True)
    config.add_user(UserConfig("b", "BK"))
    config.create_group("g")
    config.add_user_to_group("a", "g")
    config.add_user_to_group("b", "g")

    config.remove_user("a")
    assert "a" not in config.users
    assert config.get_group("g").members == ["b"]
    assert config.default_user == "b"


def test_user_in_many_groups():
    config = MultiUserConfig()
    config.add_user(UserConfig("a", "AK"), make_default=True)
    config.create_group("g1")
    config.create_group("g2")
    config.add_user_to_group("a", "g1")
    config.add_user_to_group("a", "g2")
    assert config.get_group("g1").members == ["a"]
    assert config.get_group("g2").members == ["a"]


def test_dangling_group_member_warns_and_drops(isolated_config):
    cm = isolated_config
    write_global_raw(
        cm,
        {
            "version": 1,
            "default_user": "a",
            "users": {
                "a": {"device_key": "AK", "server_url": "https://api.day.app", "encryption": None}
            },
            "groups": {"g": {"description": "", "members": ["a", "ghost"]}},
        },
    )
    with pytest.warns(UserWarning):
        config = cm.load_multi()
    assert config.get_group("g").members == ["a"]


def test_add_duplicate_user_raises():
    config = MultiUserConfig()
    config.add_user(UserConfig("a", "AK"))
    with pytest.raises(BarkConfigError):
        config.add_user(UserConfig("a", "AK2"))


def test_invalid_nickname_raises():
    config = MultiUserConfig()
    with pytest.raises(BarkConfigError):
        config.add_user(UserConfig("bad nick!", "K"))


def test_unknown_user_and_group_raise():
    config = MultiUserConfig()
    with pytest.raises(BarkConfigError):
        config.get_user("nope")
    with pytest.raises(BarkConfigError):
        config.get_group("nope")


def test_load_without_config_raises_validation(isolated_config):
    with pytest.raises(BarkValidationError):
        isolated_config.load()


def test_load_resolves_default_user(isolated_config):
    cm = isolated_config
    config = MultiUserConfig()
    config.add_user(
        UserConfig(
            "phone", "PK", server_url="https://x", encryption=make_encryption_config("k" * 32)
        ),
        make_default=True,
    )
    cm.save_multi(config)

    bark = cm.load()
    assert bark.device_key == "PK"
    assert bark.server_url == "https://x"
    assert bark.encryption_config is not None


def test_from_config_works_after_migration(isolated_config):
    cm = isolated_config
    write_global_raw(
        cm,
        {"device_key": "DK", "encryption_key": "k" * 32, "encryption_algo": "AES_256_GCM"},
    )
    client = BarkClient.from_config()
    assert client.device_key == "DK"
    assert client.encryption_config is not None

"""Regression tests for the FIXES.md bug fix batch.

Each test maps to a finding ID from FIXES.md. Tests use the isolated_config
fixture from conftest.py for all config-related tests and the responses library
for HTTP mocking.
"""

import json
import os
import stat

import pytest
import responses
from conftest import write_global_raw

from iskoldtbark import (
    BarkClient,
    BarkConfigError,
    BarkPayload,
    BarkValidationError,
    ConfigManager,
    CryptoAlgorithm,
    EncryptionConfig,
    MultiUserConfig,
    UserConfig,
    UserNotifier,
    cli,
    make_encryption_config,
    send,
)

PUSH_URL = "https://api.day.app/push"


def run_cli(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["iskoldtbark"] + argv)
    cli.main()


# ---------------------------------------------------------------------------
# P0-1: Environment / local config overlays are not persisted
# ---------------------------------------------------------------------------


class TestP0_1_OverlayNotPersisted:
    """load_persistent() must not include env / local-file overlays."""

    def test_env_device_key_not_written_back(self, isolated_config, monkeypatch):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "REAL_KEY"), make_default=True)
        cm.save_multi(config)

        monkeypatch.setenv("BARK_DEVICE_KEY", "TRANSIENT_ENV_KEY")
        # load_persistent must ignore env
        persistent = cm.load_persistent()
        assert persistent.get_user("phone").device_key == "REAL_KEY"

    def test_env_encryption_key_not_written_back(self, isolated_config, monkeypatch):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(
            UserConfig(
                "phone",
                "PK",
                encryption=make_encryption_config("a" * 32, "AES_256_GCM"),
            ),
            make_default=True,
        )
        cm.save_multi(config)

        monkeypatch.setenv("BARK_ENCRYPTION_KEY", "b" * 32)
        persistent = cm.load_persistent()
        assert persistent.get_user("phone").encryption.key == b"a" * 32

    def test_env_server_url_not_written_back(self, isolated_config, monkeypatch):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        monkeypatch.setenv("BARK_SERVER_URL", "https://temp.example.com")
        persistent = cm.load_persistent()
        assert persistent.get_user("phone").server_url == "https://api.day.app"

    def test_write_back_command_does_not_persist_env(self, isolated_config, monkeypatch):
        cm = isolated_config
        run_cli(["init", "--nickname", "phone", "--device-key", "REAL_KEY"], monkeypatch)

        monkeypatch.setenv("BARK_DEVICE_KEY", "TRANSIENT_ENV_KEY")
        # group create uses load_persistent -> save_multi
        run_cli(["group", "create", "work"], monkeypatch)

        # reload from disk only
        with open(cm.GLOBAL_CONFIG_FILE) as f:
            raw = json.load(f)
        assert raw["users"]["phone"]["device_key"] == "REAL_KEY"
        assert "work" in raw["groups"]

    def test_local_file_users_not_leaked_to_global(self, isolated_config, monkeypatch):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        # Write a local config with an extra user
        local = {
            "version": 1,
            "default_user": "phone",
            "users": {
                "phone": {
                    "device_key": "PK",
                    "server_url": "https://api.day.app",
                    "encryption": None,
                },
                "secret": {
                    "device_key": "SK",
                    "server_url": "https://api.day.app",
                    "encryption": None,
                },
            },
            "groups": {},
        }
        with open(cm._local_config_file(), "w") as f:
            json.dump(local, f)

        # load_persistent should not include the local-file user
        persistent = cm.load_persistent()
        assert "secret" not in persistent.users

    def test_send_path_still_uses_env_overrides(self, isolated_config, monkeypatch):
        """load_multi() (used for sending) still applies env overrides."""
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "ORIG_KEY"), make_default=True)
        cm.save_multi(config)

        monkeypatch.setenv("BARK_DEVICE_KEY", "ENV_KEY")
        loaded = cm.load_multi()
        assert loaded.get_user("phone").device_key == "ENV_KEY"


# ---------------------------------------------------------------------------
# P0-3: Structural config corruption raises BarkConfigError
# ---------------------------------------------------------------------------


class TestP0_3_StructuralCorruption:
    def test_top_level_array_raises(self, isolated_config):
        cm = isolated_config
        cm.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(cm.GLOBAL_CONFIG_FILE, "w") as f:
            json.dump([1, 2, 3], f)
        with pytest.raises(BarkConfigError, match="expected a JSON object"):
            cm.load_multi()

    def test_missing_device_key_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(
            cm,
            {
                "version": 1,
                "default_user": "phone",
                "users": {"phone": {"server_url": "https://api.day.app", "encryption": None}},
                "groups": {},
            },
        )
        with pytest.raises(BarkConfigError, match="missing 'device_key'"):
            cm.load_multi()

    def test_encryption_missing_key_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(
            cm,
            {
                "version": 1,
                "default_user": "phone",
                "users": {
                    "phone": {
                        "device_key": "PK",
                        "server_url": "https://api.day.app",
                        "encryption": {"algorithm": "AES_256_GCM"},
                    }
                },
                "groups": {},
            },
        )
        with pytest.raises(BarkConfigError, match="missing 'key'"):
            cm.load_multi()

    def test_group_members_not_list_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(
            cm,
            {
                "version": 1,
                "default_user": "phone",
                "users": {
                    "phone": {
                        "device_key": "PK",
                        "server_url": "https://api.day.app",
                        "encryption": None,
                    }
                },
                "groups": {"g": {"description": "", "members": "not-a-list"}},
            },
        )
        with pytest.raises(BarkConfigError, match="expected a list"):
            cm.load_multi()

    def test_corrupt_file_not_touched(self, isolated_config):
        """Corruption detection must not overwrite the original file."""
        cm = isolated_config
        cm.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(cm.GLOBAL_CONFIG_FILE, "w") as f:
            json.dump([1, 2, 3], f)
        before = cm.GLOBAL_CONFIG_FILE.read_text()
        with pytest.raises(BarkConfigError):
            cm.load_multi()
        assert cm.GLOBAL_CONFIG_FILE.read_text() == before


# ---------------------------------------------------------------------------
# P1-1: save_multi concurrency / atomicity
# ---------------------------------------------------------------------------


class TestP1_1_SaveMultiAtomicity:
    def test_save_no_tmp_residue_and_permissions(self, isolated_config):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        # No .tmp files should remain
        tmp_files = list(cm.GLOBAL_CONFIG_DIR.glob("*.tmp"))
        assert tmp_files == []

        # File permissions should be 0600
        mode = stat.S_IMODE(os.stat(cm.GLOBAL_CONFIG_FILE).st_mode)
        assert mode == 0o600

        # Content should be valid
        with open(cm.GLOBAL_CONFIG_FILE) as f:
            data = json.load(f)
        assert data["users"]["phone"]["device_key"] == "PK"

    def test_mid_write_failure_preserves_original(self, isolated_config, monkeypatch):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)
        original_content = cm.GLOBAL_CONFIG_FILE.read_text()

        # Make json.dump raise during the next save
        def bad_dump(*args, **kwargs):
            raise IOError("Simulated write failure")

        monkeypatch.setattr("json.dump", bad_dump)
        config2 = MultiUserConfig()
        config2.add_user(UserConfig("laptop", "LK"), make_default=True)
        with pytest.raises(BarkConfigError, match="Failed to save"):
            cm.save_multi(config2)

        # Original file should be intact
        assert cm.GLOBAL_CONFIG_FILE.read_text() == original_content
        # No tmp files should remain
        tmp_files = list(cm.GLOBAL_CONFIG_DIR.glob("*.tmp"))
        assert tmp_files == []


# ---------------------------------------------------------------------------
# P1-2: send() raises when server_url/encryption given without device_key
# ---------------------------------------------------------------------------


class TestP1_2_SendConflictingArgs:
    def test_server_url_without_device_key_raises(self, isolated_config):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        with pytest.raises(BarkValidationError, match="server_url"):
            send("hi", server_url="https://custom.server")

    def test_encryption_without_device_key_raises(self, isolated_config):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        enc = EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)
        with pytest.raises(BarkValidationError, match="encryption"):
            send("hi", encryption=enc)

    @responses.activate
    def test_send_with_device_key_and_server_url_works(self):
        responses.add(responses.POST, "https://custom.server/push", json={"code": 200}, status=200)
        res = send("hi", "DK", server_url="https://custom.server")
        assert res["code"] == 200

    @responses.activate
    def test_send_from_config_still_works(self, isolated_config):
        cm = isolated_config
        config = MultiUserConfig()
        config.add_user(UserConfig("phone", "PK"), make_default=True)
        cm.save_multi(config)

        responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
        res = send("hi")
        assert res["code"] == 200


# ---------------------------------------------------------------------------
# P1-3: isArchive allows "0", --no-archive CLI flag
# ---------------------------------------------------------------------------


class TestP1_3_IsArchive:
    def test_is_archive_zero_valid(self):
        p = BarkPayload(body="x", device_key="k", isArchive="0")
        p.validate()  # should not raise
        assert p.to_dict()["isArchive"] == "0"

    def test_is_archive_one_valid(self):
        p = BarkPayload(body="x", device_key="k", isArchive="1")
        p.validate()
        assert p.to_dict()["isArchive"] == "1"

    def test_is_archive_invalid_value_raises(self):
        with pytest.raises(BarkValidationError):
            BarkPayload(body="x", device_key="k", isArchive="2").validate()

    @responses.activate
    def test_no_archive_cli_flag(self, isolated_config, monkeypatch):
        run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
        run_cli(
            ["user", "add", "--nickname", "plain", "--device-key", "PLK", "--no-encryption"],
            monkeypatch,
        )
        responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
        run_cli(["send", "hi", "--user", "plain", "--no-archive"], monkeypatch)
        body = json.loads(responses.calls[0].request.body)
        assert body["isArchive"] == "0"

    def test_is_archive_and_no_archive_mutually_exclusive(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            run_cli(["send", "hi", "--is-archive", "--no-archive"], monkeypatch)
        assert exc.value.code == 2  # argparse error


# ---------------------------------------------------------------------------
# P1-4: Double encryption prevention
# ---------------------------------------------------------------------------


class TestP1_4_DoubleEncryption:
    def test_pre_encrypted_with_encryption_config_raises(self):
        enc = EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)
        client = BarkClient("k", encryption=enc)
        with pytest.raises(BarkValidationError, match="double-encrypted"):
            client.push(body="x", ciphertext="CT", iv="IVVALUE")

    def test_pre_encrypted_iv_only_with_encryption_config_raises(self):
        enc = EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)
        client = BarkClient("k", encryption=enc)
        with pytest.raises(BarkValidationError, match="double-encrypted"):
            client.push(body="x", iv="IVVALUE")

    @responses.activate
    def test_pre_encrypted_without_encryption_config_ok(self):
        """Existing test_push_accepts_ciphertext_and_iv_kwargs behavior preserved."""
        responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
        BarkClient("k").push(body="x", ciphertext="CT", iv="IVVALUE")
        body = json.loads(responses.calls[0].request.body)
        assert body["ciphertext"] == "CT"
        assert body["iv"] == "IVVALUE"


# ---------------------------------------------------------------------------
# P2-1: GCM allows 12 or 16 byte static IV; CBC only 16
# ---------------------------------------------------------------------------


class TestP2_1_IVLengthByAlgorithm:
    def test_gcm_12_byte_static_iv_warns(self):
        from iskoldtbark import BarkSecurityWarning

        with pytest.warns(BarkSecurityWarning):
            EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM, iv=b"0" * 12)

    def test_cbc_12_byte_static_iv_rejected(self):
        from iskoldtbark import BarkCryptoError

        with pytest.raises(BarkCryptoError, match="16 bytes"):
            EncryptionConfig(key=b"k" * 16, algorithm=CryptoAlgorithm.AES_128_CBC, iv=b"0" * 12)


# ---------------------------------------------------------------------------
# P2-2: Empty recipient group exits 1 in CLI
# ---------------------------------------------------------------------------


class TestP2_2_EmptyGroupBroadcast:
    def test_cli_empty_group_exits_nonzero(self, isolated_config, monkeypatch, capsys):
        run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
        run_cli(["group", "create", "empty"], monkeypatch)
        with pytest.raises(SystemExit) as exc:
            run_cli(["send", "hi", "--user-group", "empty"], monkeypatch)
        assert exc.value.code == 1
        assert "no members" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# P2-3: --device-key with --user-group rejected
# ---------------------------------------------------------------------------


class TestP2_3_DeviceKeyGroupConflict:
    @responses.activate
    def test_device_key_with_user_group_exits_nonzero(self, isolated_config, monkeypatch, capsys):
        run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
        run_cli(["group", "create", "g"], monkeypatch)
        run_cli(["group", "add-user", "g", "phone"], monkeypatch)
        with pytest.raises(SystemExit) as exc:
            run_cli(
                ["send", "hi", "--user-group", "g", "--device-key", "OVERRIDE"],
                monkeypatch,
            )
        assert exc.value.code == 1
        assert "cannot be used" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# P2-4: Duplicate group members deduplicated on load
# ---------------------------------------------------------------------------


class TestP2_4_DuplicateGroupMembers:
    def test_duplicate_members_deduped_on_load(self, isolated_config):
        cm = isolated_config
        write_global_raw(
            cm,
            {
                "version": 1,
                "default_user": "a",
                "users": {
                    "a": {
                        "device_key": "AK",
                        "server_url": "https://api.day.app",
                        "encryption": None,
                    },
                    "b": {
                        "device_key": "BK",
                        "server_url": "https://api.day.app",
                        "encryption": None,
                    },
                },
                "groups": {"g": {"description": "", "members": ["a", "b", "a", "b", "a"]}},
            },
        )
        with pytest.warns(UserWarning, match="duplicate"):
            config = cm.load_multi()
        assert config.get_group("g").members == ["a", "b"]


# ---------------------------------------------------------------------------
# P2-7: Configurable timeout
# ---------------------------------------------------------------------------


class TestP2_7_ConfigurableTimeout:
    def test_custom_timeout_used_in_push(self):
        from unittest.mock import patch

        client = BarkClient("k", timeout=5.0)
        assert client.timeout == 5.0

        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value.json.return_value = {"code": 200}
            mock_post.return_value.ok = True
            client.push(body="x")

            mock_post.assert_called_once()
            assert mock_post.call_args.kwargs.get("timeout") == 5.0

    def test_default_timeout(self):
        client = BarkClient("k")
        assert client.timeout == 30.0


# ---------------------------------------------------------------------------
# P2-8: Future config version rejected
# ---------------------------------------------------------------------------


class TestP2_8_FutureVersion:
    def test_version_2_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(cm, {"version": 2, "users": {}})
        with pytest.raises(BarkConfigError, match="newer version"):
            cm.load_multi()

    def test_version_string_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(cm, {"version": "2", "users": {}})
        with pytest.raises(BarkConfigError, match="must be an integer"):
            cm.load_multi()

    def test_version_2_no_users_raises(self, isolated_config):
        cm = isolated_config
        write_global_raw(cm, {"version": 2, "future_field": "data"})
        with pytest.raises(BarkConfigError, match="newer version"):
            cm.load_multi()

    def test_version_1_still_works(self, isolated_config):
        cm = isolated_config
        write_global_raw(
            cm,
            {
                "version": 1,
                "default_user": "a",
                "users": {
                    "a": {
                        "device_key": "AK",
                        "server_url": "https://api.day.app",
                        "encryption": None,
                    }
                },
                "groups": {},
            },
        )
        config = cm.load_multi()
        assert config.get_user("a").device_key == "AK"

"""Regression tests for the issues found in the security/correctness audit.

Each test maps to a finding ID from AUDIT.md (H = high, M = medium, L = low).
"""

import json
import os
import stat
import warnings

import pytest
import responses

from iskoldtbark import (
    BarkAPIError,
    BarkClient,
    BarkPayload,
    BarkSecurityWarning,
    BarkValidationError,
    ConfigManager,
    CryptoAlgorithm,
    EncryptionConfig,
    MultiUserConfig,
    UserConfig,
    UserNotifier,
    cli,
    make_encryption_config,
)
from iskoldtbark.config import BarkConfigError
from iskoldtbark.crypto import _generate_iv

PUSH_URL = "https://api.day.app/push"

HEX = set("0123456789abcdef")


def run_cli(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["iskoldtbark"] + argv)
    cli.main()


# --- H1: generated key entropy ---------------------------------------------
def test_generated_key_is_full_length_and_not_hex_only():
    for n in (16, 24, 32):
        key = cli.generate_random_string(n)
        assert len(key) == n
        assert len(key.encode("utf-8")) == n  # ASCII: byte length == char length
    # Across many 32-char keys the alphabet must exceed the 16 hex symbols, proving
    # ~5.95 bits/char instead of the old 4 bits/char (128-bit "AES-256").
    seen = set()
    for _ in range(50):
        seen |= set(cli.generate_random_string(32))
    assert not seen <= HEX
    assert len(seen) > 16


def test_generated_key_usable_as_aes256_key():
    key = cli.generate_random_string(32)
    cfg = make_encryption_config(key, "AES_256_GCM")  # 32-byte length check must pass
    assert cfg.algorithm == CryptoAlgorithm.AES_256_GCM


# --- L3: IV entropy ---------------------------------------------------------
def test_generated_iv_lengths_and_charset():
    gcm = _generate_iv(CryptoAlgorithm.AES_256_GCM).decode()
    cbc = _generate_iv(CryptoAlgorithm.AES_128_CBC).decode()
    assert len(gcm) == 12 and len(cbc) == 16
    seen = set()
    for _ in range(50):
        seen |= set(_generate_iv(CryptoAlgorithm.AES_256_GCM).decode())
    assert not seen <= HEX  # higher-entropy alphabet, not hex


# --- H2: GCM + static IV warns (still accepted, non-breaking) ---------------
def test_gcm_static_iv_emits_security_warning():
    with pytest.warns(BarkSecurityWarning):
        EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM, iv=b"0" * 16)


def test_cbc_static_iv_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error", BarkSecurityWarning)
        EncryptionConfig(key=b"k" * 16, algorithm=CryptoAlgorithm.AES_128_CBC, iv=b"0" * 16)


def test_gcm_dynamic_iv_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error", BarkSecurityWarning)
        EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)


# --- H3: corrupted config is not silently swallowed / overwritten -----------
def test_corrupt_config_raises_instead_of_losing_data(isolated_config):
    cm = isolated_config
    config = MultiUserConfig()
    config.add_user(UserConfig("phone", "PK"), make_default=True)
    config.add_user(UserConfig("laptop", "LK"))
    cm.save_multi(config)

    cm.GLOBAL_CONFIG_FILE.write_text('{"version":1,"users":{"phone": {"devi')  # truncated
    before = cm.GLOBAL_CONFIG_FILE.read_text()

    with pytest.raises(BarkConfigError):
        cm.load_multi()
    # The corrupt file must be left untouched (no silent overwrite/data loss).
    assert cm.GLOBAL_CONFIG_FILE.read_text() == before


def test_missing_config_still_returns_empty(isolated_config):
    # Absence is normal and must NOT raise (only corruption does).
    assert isolated_config.load_multi().users == {}


# --- M1: device_keys multicast actually routes ------------------------------
@responses.activate
def test_encrypted_multicast_includes_device_keys():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    cfg = EncryptionConfig(key=b"k" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)
    BarkClient("primary", encryption=cfg).push(body="x", device_keys=["a", "b"])
    body = json.loads(responses.calls[0].request.body)
    assert body["device_keys"] == ["a", "b"]
    assert "device_key" not in body  # routed on the list, not the single key
    assert "ciphertext" in body and "body" not in body


@responses.activate
def test_unencrypted_multicast_drops_single_device_key():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    BarkClient("primary").push(body="x", device_keys=["a", "b"])
    body = json.loads(responses.calls[0].request.body)
    assert body["device_keys"] == ["a", "b"]
    assert "device_key" not in body  # no ambiguous both-fields payload


@responses.activate
def test_single_device_key_unchanged_without_multicast():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    BarkClient("solo").push(body="x")
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "solo"
    assert "device_keys" not in body


# --- M2: HTTP error / non-JSON body handling --------------------------------
@responses.activate
def test_http_error_without_code_surfaces_status_and_body():
    responses.add(responses.POST, PUSH_URL, body="Bad Gateway", status=502)
    with pytest.raises(BarkAPIError, match="HTTP 502"):
        BarkClient("k").push(body="x")


@responses.activate
def test_non_dict_json_body_does_not_crash():
    responses.add(responses.POST, PUSH_URL, json=[1, 2, 3], status=200)
    assert BarkClient("k").push(body="x") == {}


# --- models: badge / ttl validation -----------------------------------------
def test_badge_and_ttl_validation():
    with pytest.raises(BarkValidationError):
        BarkPayload(body="x", device_key="k", badge=-1).validate()
    with pytest.raises(BarkValidationError):
        BarkPayload(body="x", device_key="k", ttl=-5).validate()
    BarkPayload(body="x", device_key="k", badge=0, ttl=0).validate()  # valid


# --- M4: CLI send forwards the previously-dropped fields ---------------------
@responses.activate
def test_cli_send_forwards_extended_fields(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "plain", "--device-key", "PLK", "--no-encryption"],
        monkeypatch,
    )
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    run_cli(
        [
            "send",
            "hello",
            "--user",
            "plain",
            "--markdown",
            "**hi**",
            "--sound",
            "minuet.caf",
            "--copy",
            "code123",
            "--ttl",
            "3600",
            "--call",
            "--id",
            "n-1",
        ],
        monkeypatch,
    )
    body = json.loads(responses.calls[0].request.body)
    assert body["markdown"] == "**hi**"
    assert body["sound"] == "minuet.caf"
    assert body["copy"] == "code123"
    assert body["ttl"] == 3600
    assert body["call"] == "1"
    assert body["id"] == "n-1"


# --- L1: one recipient's unexpected error does not abort the broadcast -------
def test_group_broadcast_survives_unexpected_exception(monkeypatch):
    config = MultiUserConfig()
    config.add_user(UserConfig("a", "AK"), make_default=True)
    config.add_user(UserConfig("b", "BK"))
    config.create_group("g")
    config.add_user_to_group("a", "g")
    config.add_user_to_group("b", "g")

    def boom(self, *a, **k):  # not a Bark/requests error -> previously aborted all
        raise RuntimeError("unexpected")

    monkeypatch.setattr(BarkClient, "push", boom)
    result = UserNotifier(config).send_to_group("g", "hi")  # must not raise
    assert result.total == 2
    assert result.success_count == 0
    assert all("unexpected" in o["error"] for o in result.per_user_results.values())


# --- L4: legacy save_global writes a 0600 file ------------------------------
def test_save_global_writes_owner_only(isolated_config):
    cm = isolated_config
    cm.save_global("DK", "k" * 32, "AES_256_GCM")
    mode = stat.S_IMODE(os.stat(cm.GLOBAL_CONFIG_FILE).st_mode)
    assert mode == 0o600


# --- L7: non-HTTPS server_url warns -----------------------------------------
def test_non_https_server_url_warns():
    with pytest.warns(BarkSecurityWarning):
        BarkClient("k", server_url="http://192.168.0.10:8080")


def test_https_server_url_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error", BarkSecurityWarning)
        BarkClient("k")  # default is https

import json

import pytest
import responses
from conftest import write_global_raw

from iskoldtbark import cli
from iskoldtbark.config import ConfigManager

PUSH_URL = "https://api.day.app/push"


def run_cli(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["iskoldtbark"] + argv)
    cli.main()


def test_init_requires_nickname(isolated_config, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    with pytest.raises(SystemExit) as exc:
        run_cli(["init", "--device-key", "DK"], monkeypatch)
    assert exc.value.code == 1


def test_init_writes_default_user(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "DK"], monkeypatch)
    config = ConfigManager.load_multi()
    assert config.default_user == "phone"
    assert config.get_user("phone").device_key == "DK"
    assert config.get_user("phone").encryption.algorithm.value == "AES_256_GCM"


@responses.activate
def test_send_to_default_target(isolated_config, monkeypatch, capsys):
    run_cli(["init", "--nickname", "phone", "--device-key", "DK"], monkeypatch)
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    run_cli(["send", "hello"], monkeypatch)
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "DK"
    assert "Success" in capsys.readouterr().out


def test_send_user_and_group_are_mutually_exclusive(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "DK"], monkeypatch)
    with pytest.raises(SystemExit) as exc:
        run_cli(["send", "hi", "--user", "phone", "--user-group", "work"], monkeypatch)
    assert exc.value.code == 2  # argparse usage error


@responses.activate
def test_group_flag_maps_to_payload_group(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "plain", "--device-key", "PLK", "--no-encryption"],
        monkeypatch,
    )
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    run_cli(["send", "hi", "--user", "plain", "--group", "Alerts"], monkeypatch)
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "PLK"
    assert body["group"] == "Alerts"  # iOS notification grouping, unchanged behavior


@responses.activate
def test_recipient_group_broadcast_with_group_flag(isolated_config, monkeypatch, capsys):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "p1", "--device-key", "K1", "--no-encryption"], monkeypatch
    )
    run_cli(
        ["user", "add", "--nickname", "p2", "--device-key", "K2", "--no-encryption"], monkeypatch
    )
    run_cli(["group", "create", "team"], monkeypatch)
    run_cli(["group", "add-user", "team", "p1"], monkeypatch)
    run_cli(["group", "add-user", "team", "p2"], monkeypatch)

    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    run_cli(["send", "hi", "--user-group", "team", "--group", "Alerts"], monkeypatch)

    assert len(responses.calls) == 2
    keys = {json.loads(c.request.body)["device_key"] for c in responses.calls}
    assert keys == {"K1", "K2"}
    for c in responses.calls:
        assert json.loads(c.request.body)["group"] == "Alerts"
    assert "2 succeeded, 0 failed" in capsys.readouterr().out


@responses.activate
def test_group_broadcast_partial_failure_exit_code(isolated_config, monkeypatch, capsys):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "p1", "--device-key", "K1", "--no-encryption"], monkeypatch
    )
    run_cli(
        ["user", "add", "--nickname", "p2", "--device-key", "K2", "--no-encryption"], monkeypatch
    )
    run_cli(["group", "create", "team"], monkeypatch)
    run_cli(["group", "add-user", "team", "p1"], monkeypatch)
    run_cli(["group", "add-user", "team", "p2"], monkeypatch)

    def callback(request):
        body = json.loads(request.body)
        if body["device_key"] == "K2":
            return (400, {}, json.dumps({"code": 400, "message": "bad key"}))
        return (200, {}, json.dumps({"code": 200}))

    responses.add_callback(
        responses.POST, PUSH_URL, callback=callback, content_type="application/json"
    )
    run_cli(["send", "hi", "--user-group", "team"], monkeypatch)  # partial success -> exit 0

    out = capsys.readouterr().out
    assert "1 succeeded, 1 failed" in out


@responses.activate
def test_group_broadcast_all_fail_exits_nonzero(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "p1", "--device-key", "K1", "--no-encryption"], monkeypatch
    )
    run_cli(["group", "create", "team"], monkeypatch)
    run_cli(["group", "add-user", "team", "p1"], monkeypatch)

    responses.add(responses.POST, PUSH_URL, json={"code": 400, "message": "bad"}, status=400)
    with pytest.raises(SystemExit) as exc:
        run_cli(["send", "hi", "--user-group", "team"], monkeypatch)
    assert exc.value.code == 1


def test_user_add_wrong_length_iv_rejected(isolated_config, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(
            [
                "user",
                "add",
                "--nickname",
                "x",
                "--device-key",
                "K",
                "--algo",
                "AES_128_CBC",
                "--encryption-key",
                "k" * 16,
                "--iv",
                "short",
            ],
            monkeypatch,
        )
    assert exc.value.code == 1
    assert "Error" in capsys.readouterr().out


def test_migrate_command_rewrites_to_v1(isolated_config, monkeypatch, capsys):
    cm = isolated_config
    write_global_raw(
        cm,
        {"device_key": "DK", "encryption_key": "k" * 32, "encryption_algo": "AES_256_GCM"},
    )
    assert cm.is_legacy_on_disk()

    run_cli(["migrate"], monkeypatch)

    assert not cm.is_legacy_on_disk()
    with open(cm.GLOBAL_CONFIG_FILE) as f:
        data = json.load(f)
    assert data["version"] == 1
    assert "default" in data["users"]


def test_set_default_command(isolated_config, monkeypatch):
    run_cli(["init", "--nickname", "phone", "--device-key", "PK"], monkeypatch)
    run_cli(
        ["user", "add", "--nickname", "laptop", "--device-key", "LK", "--no-encryption"],
        monkeypatch,
    )
    run_cli(["set-default", "laptop"], monkeypatch)
    assert ConfigManager.load_multi().default_user == "laptop"

import json

import pytest
import responses

from iskoldtbark import (
    BarkConfigError,
    MultiUserConfig,
    UserConfig,
    UserNotifier,
    make_encryption_config,
)

PUSH_URL = "https://api.day.app/push"


def make_config():
    config = MultiUserConfig()
    config.add_user(
        UserConfig(
            "phone", "PHONE_KEY", encryption=make_encryption_config("p" * 32, "AES_256_GCM")
        ),
        make_default=True,
    )
    config.add_user(
        UserConfig(
            "laptop",
            "LAPTOP_KEY",
            encryption=make_encryption_config("c" * 16, "AES_128_CBC", "0123456789abcdef"),
        )
    )
    config.create_group("work")
    config.add_user_to_group("phone", "work")
    config.add_user_to_group("laptop", "work")
    return config


@responses.activate
def test_send_to_user_uses_user_key_and_encryption():
    responses.add(responses.POST, PUSH_URL, json={"code": 200, "message": "ok"}, status=200)
    res = UserNotifier(make_config()).send_to_user("phone", "hi")
    assert res["code"] == 200
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "PHONE_KEY"
    assert "ciphertext" in body and "body" not in body


@responses.activate
def test_send_to_default():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    UserNotifier(make_config()).send_to_default("hi")
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "PHONE_KEY"


def test_send_to_default_without_default_raises():
    config = MultiUserConfig()  # no users, no default
    with pytest.raises(BarkConfigError):
        UserNotifier(config).send_to_default("hi")


@responses.activate
def test_send_to_group_all_success():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    result = UserNotifier(make_config()).send_to_group("work", "hi")
    assert result.total == 2
    assert result.success_count == 2
    assert result.failure_count == 0
    assert all(o["ok"] for o in result.per_user_results.values())


@responses.activate
def test_send_to_group_partial_failure_continues():
    def callback(request):
        body = json.loads(request.body)
        if body["device_key"] == "LAPTOP_KEY":
            return (400, {}, json.dumps({"code": 400, "message": "device key not found"}))
        return (200, {}, json.dumps({"code": 200, "message": "ok"}))

    responses.add_callback(
        responses.POST, PUSH_URL, callback=callback, content_type="application/json"
    )
    result = UserNotifier(make_config()).send_to_group("work", "hi")

    assert result.total == 2
    assert result.success_count == 1
    assert result.per_user_results["phone"]["ok"] is True
    assert result.per_user_results["laptop"]["ok"] is False
    assert "device key not found" in result.per_user_results["laptop"]["error"]
    assert not result.all_failed


@responses.activate
def test_send_to_group_per_user_distinct_encryption():
    captured = []

    def callback(request):
        captured.append(json.loads(request.body))
        return (200, {}, json.dumps({"code": 200}))

    responses.add_callback(
        responses.POST, PUSH_URL, callback=callback, content_type="application/json"
    )
    UserNotifier(make_config()).send_to_group("work", "same body")

    by_key = {c["device_key"]: c for c in captured}
    phone, laptop = by_key["PHONE_KEY"], by_key["LAPTOP_KEY"]
    assert phone["ciphertext"] != laptop["ciphertext"]
    assert len(phone["iv"]) == 12  # GCM dynamic IV
    assert len(laptop["iv"]) == 16  # CBC static IV


def test_send_to_empty_group():
    config = MultiUserConfig()
    config.add_user(UserConfig("a", "AK"), make_default=True)
    config.create_group("empty")
    result = UserNotifier(config).send_to_group("empty", "hi")
    assert result.total == 0
    assert result.success_count == 0
    assert result.per_user_results == {}


def test_send_to_unknown_group_raises():
    with pytest.raises(BarkConfigError):
        UserNotifier(MultiUserConfig()).send_to_group("nope", "hi")

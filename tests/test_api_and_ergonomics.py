import dataclasses
import inspect
import json
import os

import pytest
import responses

from iskoldtbark import (
    BarkClient,
    BarkPayload,
    BarkValidationError,
    ConfigManager,
    CryptoAlgorithm,
    EncryptionConfig,
    MultiUserConfig,
    UserConfig,
    send,
)

PUSH_URL = "https://api.day.app/push"


# --- API completeness -------------------------------------------------------
def test_new_payload_fields_serialize():
    payload = BarkPayload(
        body="x",
        device_key="k",
        markdown="**hi**",
        image="https://img.example/i.png",
        id="note-1",
    )
    data = payload.to_dict()
    assert data["markdown"] == "**hi**"
    assert data["image"] == "https://img.example/i.png"
    assert data["id"] == "note-1"


def test_delete_validation():
    # delete requires id
    with pytest.raises(BarkValidationError):
        BarkPayload(body="x", device_key="k", delete="1").validate()
    # delete must be "1"
    with pytest.raises(BarkValidationError):
        BarkPayload(body="x", device_key="k", delete="0", id="a").validate()
    # valid
    BarkPayload(body="x", device_key="k", delete="1", id="a").validate()


@responses.activate
def test_push_sends_new_fields():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    BarkClient("k").push(body="x", markdown="**m**", image="https://i", id="n1")
    body = json.loads(responses.calls[0].request.body)
    assert body["markdown"] == "**m**"
    assert body["image"] == "https://i"
    assert body["id"] == "n1"


@responses.activate
def test_push_accepts_ciphertext_and_iv_kwargs():
    # Backward compat: pre-existing callers could pass a pre-built ciphertext/iv.
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    BarkClient("k").push(body="x", ciphertext="CT", iv="IVVALUE")
    body = json.loads(responses.calls[0].request.body)
    assert body["ciphertext"] == "CT"
    assert body["iv"] == "IVVALUE"


@responses.activate
def test_utility_endpoints():
    responses.add(responses.GET, "https://api.day.app/ping", json={"code": 200, "message": "pong"})
    responses.add(responses.GET, "https://api.day.app/info", json={"version": "2.1.0"})
    responses.add(responses.GET, "https://api.day.app/healthz", body="ok")
    client = BarkClient("k")
    assert client.ping()["message"] == "pong"
    assert client.info()["version"] == "2.1.0"
    assert client.healthz() == "ok"


# --- ergonomics -------------------------------------------------------------
@responses.activate
def test_encryption_via_constructor():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    cfg = EncryptionConfig(key=os.urandom(32), algorithm=CryptoAlgorithm.AES_256_GCM)
    client = BarkClient("k", encryption=cfg)
    client.push(body="secret")
    body = json.loads(responses.calls[0].request.body)
    assert "ciphertext" in body and "body" not in body


@responses.activate
def test_top_level_send_with_device_key():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    res = send("hi", "DEVKEY", title="t")
    assert res["code"] == 200
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "DEVKEY"
    assert body["title"] == "t"


@responses.activate
def test_top_level_send_encrypted_with_device_key():
    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    cfg = EncryptionConfig(key=os.urandom(32), algorithm=CryptoAlgorithm.AES_256_GCM)
    send("secret", "DEVKEY", encryption=cfg)
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "DEVKEY"
    assert "ciphertext" in body and "body" not in body


@responses.activate
def test_top_level_send_from_config(isolated_config):
    config = MultiUserConfig()
    config.add_user(UserConfig("phone", "PK"), make_default=True)
    ConfigManager.save_multi(config)

    responses.add(responses.POST, PUSH_URL, json={"code": 200}, status=200)
    send("hi")
    body = json.loads(responses.calls[0].request.body)
    assert body["device_key"] == "PK"


def test_push_signature_covers_user_facing_payload_fields():
    push_params = set(inspect.signature(BarkClient.push).parameters) - {"self"}
    payload_fields = {f.name for f in dataclasses.fields(BarkPayload)}
    internal = {"device_key", "ciphertext", "iv"}
    # Guard against drift: every user-facing payload field must be reachable via push.
    assert (payload_fields - internal).issubset(push_params)

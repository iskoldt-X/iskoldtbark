import json
import os

import pytest
import responses

from iskoldtbark import (
    BarkAPIError,
    BarkClient,
    BarkValidationError,
    CryptoAlgorithm,
    EncryptionConfig,
)


def test_payload_validation():
    client = BarkClient("dummy_key")

    with pytest.raises(BarkValidationError):
        client.push(body="test", level="invalid_level")

    with pytest.raises(BarkValidationError):
        client.push(body="test", volume=11)

    with pytest.raises(BarkValidationError):
        client.push(body="test", call="2")


@responses.activate
def test_push_success():
    responses.add(
        responses.POST,
        "https://api.day.app/push",
        json={"code": 200, "message": "success", "timestamp": 123456},
        status=200,
    )

    client = BarkClient("dummy_key")
    response = client.push(body="test message", title="test title")

    assert response["code"] == 200

    request = responses.calls[0].request
    assert request.url == "https://api.day.app/push"
    assert "application/json" in request.headers["Content-Type"]

    import json

    body = json.loads(request.body)
    assert body["device_key"] == "dummy_key"
    assert body["body"] == "test message"
    assert body["title"] == "test title"


@responses.activate
def test_push_encrypted():
    responses.add(
        responses.POST,
        "https://api.day.app/push",
        json={"code": 200, "message": "success", "timestamp": 123456},
        status=200,
    )

    client = BarkClient("dummy_key")
    key = os.urandom(32)
    config = EncryptionConfig(key=key, algorithm=CryptoAlgorithm.AES_256_GCM)
    client.set_encryption(config)

    client.push(body="secret message")

    request = responses.calls[0].request

    body = json.loads(request.body)

    # Encrypted requests only send device_key, ciphertext, and iv
    assert body["device_key"] == "dummy_key"
    assert "ciphertext" in body
    assert "iv" in body
    assert "body" not in body


@responses.activate
def test_push_api_error():
    responses.add(
        responses.POST,
        "https://api.day.app/push",
        json={"code": 400, "message": "device key not found", "timestamp": 123456},
        status=400,
    )

    client = BarkClient("dummy_key")
    with pytest.raises(BarkAPIError, match="Bark API Error: device key not found"):
        client.push(body="test message")

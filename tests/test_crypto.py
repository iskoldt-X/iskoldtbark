import base64
import os

import pytest

from iskoldtbark import BarkCryptoError, CryptoAlgorithm, EncryptionConfig
from iskoldtbark.crypto import CryptoProvider


def test_encryption_config_validation():
    # Valid configurations
    EncryptionConfig(key=b"1" * 16, algorithm=CryptoAlgorithm.AES_128_CBC)
    EncryptionConfig(key=b"1" * 24, algorithm=CryptoAlgorithm.AES_192_CBC)
    EncryptionConfig(key=b"1" * 32, algorithm=CryptoAlgorithm.AES_256_CBC)
    EncryptionConfig(key=b"1" * 32, algorithm=CryptoAlgorithm.AES_256_GCM)

    # Invalid configurations
    with pytest.raises(BarkCryptoError):
        EncryptionConfig(key=b"1" * 15, algorithm=CryptoAlgorithm.AES_128_CBC)

    with pytest.raises(BarkCryptoError):
        EncryptionConfig(key=b"1" * 31, algorithm=CryptoAlgorithm.AES_256_GCM)


def test_encryption_aes_gcm():
    key = os.urandom(32)
    config = EncryptionConfig(key=key, algorithm=CryptoAlgorithm.AES_256_GCM)
    data = '{"body": "secret message"}'

    ciphertext, iv = CryptoProvider.encrypt(data, config)

    # Verify IV is correct length (12 bytes for GCM)
    assert len(iv) == 12
    assert isinstance(iv, str)

    # Ciphertext should be base64
    raw_ciphertext = base64.b64decode(ciphertext)
    assert len(raw_ciphertext) > 0
    # In GCM, ciphertext length = plaintext length + 16 (tag)
    assert len(raw_ciphertext) == len(data.encode("utf-8")) + 16


def test_encryption_aes_cbc():
    key = os.urandom(16)
    config = EncryptionConfig(key=key, algorithm=CryptoAlgorithm.AES_128_CBC)
    data = '{"body": "secret message"}'

    ciphertext, iv = CryptoProvider.encrypt(data, config)

    assert len(iv) == 16

    raw_ciphertext = base64.b64decode(ciphertext)
    assert len(raw_ciphertext) > 0
    # In CBC, ciphertext length is a multiple of 16 (padding)
    assert len(raw_ciphertext) % 16 == 0

import base64
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import BarkCryptoError


class CryptoAlgorithm(Enum):
    AES_128_CBC = "AES_128_CBC"
    AES_192_CBC = "AES_192_CBC"
    AES_256_CBC = "AES_256_CBC"
    AES_256_GCM = "AES_256_GCM"


@dataclass
class EncryptionConfig:
    key: bytes
    algorithm: CryptoAlgorithm = CryptoAlgorithm.AES_256_GCM
    iv: Optional[bytes] = None  # Optional static IV. If None, a random one is generated.

    def __post_init__(self):
        # Validate key lengths
        if self.algorithm == CryptoAlgorithm.AES_128_CBC and len(self.key) != 16:
            raise BarkCryptoError("AES_128_CBC requires a 16-byte key")
        elif self.algorithm == CryptoAlgorithm.AES_192_CBC and len(self.key) != 24:
            raise BarkCryptoError("AES_192_CBC requires a 24-byte key")
        elif (
            self.algorithm in [CryptoAlgorithm.AES_256_CBC, CryptoAlgorithm.AES_256_GCM]
            and len(self.key) != 32
        ):
            raise BarkCryptoError(f"{self.algorithm.value} requires a 32-byte key")

        if self.iv is not None and len(self.iv) != 16:
            raise BarkCryptoError("Static IV must be exactly 16 bytes")


def _generate_iv(algorithm: CryptoAlgorithm) -> bytes:
    """Generate a random IV as the ASCII hex of random bytes.

    The Bark iOS app reads the IV as a string of a fixed length: 12 characters for
    GCM and 16 for CBC. We therefore hex-encode 6 / 8 random bytes respectively and
    send that hex string (not the raw bytes).
    """
    if algorithm == CryptoAlgorithm.AES_256_GCM:
        return os.urandom(6).hex().encode("utf-8")
    return os.urandom(8).hex().encode("utf-8")


class CryptoProvider:
    @staticmethod
    def encrypt(data: str, config: EncryptionConfig) -> Tuple[str, str]:
        """Encrypt a payload string for the Bark app.

        Returns ``(ciphertext_base64, iv_string)``. When no static IV is configured a
        random one is generated (see ``_generate_iv``). For GCM the authentication tag
        is appended to the ciphertext before base64-encoding, which is the layout the
        Bark iOS app expects when decrypting.
        """
        try:
            iv = config.iv if config.iv else _generate_iv(config.algorithm)
            data_bytes = data.encode("utf-8")
            backend = default_backend()

            if config.algorithm == CryptoAlgorithm.AES_256_GCM:
                gcm = Cipher(algorithms.AES(config.key), modes.GCM(iv), backend=backend).encryptor()
                ciphertext = gcm.update(data_bytes) + gcm.finalize() + gcm.tag
            else:
                cbc = Cipher(algorithms.AES(config.key), modes.CBC(iv), backend=backend).encryptor()
                padder = padding.PKCS7(128).padder()
                padded_data = padder.update(data_bytes) + padder.finalize()
                ciphertext = cbc.update(padded_data) + cbc.finalize()

            return base64.b64encode(ciphertext).decode("utf-8"), iv.decode("utf-8")

        except Exception as e:
            raise BarkCryptoError(f"Encryption failed: {e}")

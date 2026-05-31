import base64
import os
from dataclasses import dataclass
from enum import Enum

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
    iv: bytes = None  # Optional static IV. If None, a random one is generated.

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


class CryptoProvider:
    @staticmethod
    def encrypt(data: str, config: EncryptionConfig) -> tuple[str, str]:
        """
        Encrypts data using the specified config.
        Returns a tuple of (ciphertext_base64, iv_hex).
        Note: The Bark iOS app uses base64 for ciphertext, and hex for IV in some docs,
        Wait, standard Bark docs use `ciphertext` (often hex or base64) and `iv` (hex string usually).
        Actually, let's stick to the iOS app's expected format. Bark iOS expects
        the ciphertext to be base64-encoded or hex encoded. Usually base64.
        Wait, in the original iOS client, they base64 encode the ciphertext, and the IV can be any string.
        We'll use hex for IV since it's exactly 16 bytes. Wait, let's use a 16-byte random hex string (32 hex chars)
        or 16 bytes encoded as hex string (so 32 chars).
        Let's look at the standard. The IV needs to be 16 characters string or hex?
        Actually, iOS Swift Crypto usually takes a 16-byte IV.
        We will generate 16 random bytes and pass its hex representation, or base64.
        Let's pass 16-byte IV as hex string (32 chars) or standard string. The safest is 16 alphanumeric chars.
        Wait, iOS Bark expects the iv parameter to be a string.
        Let's generate a 16-character alphanumeric IV.
        """
        try:
            if config.iv:
                iv = config.iv
            else:
                # Generate a 16-character alphanumeric string as IV
                iv = os.urandom(12).hex()[:16].encode("utf-8")

            if config.algorithm == CryptoAlgorithm.AES_256_GCM:
                cipher = Cipher(
                    algorithms.AES(config.key), modes.GCM(iv), backend=default_backend()
                )
                encryptor = cipher.encryptor()
                ciphertext = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
                # Bark iOS App for GCM: it expects the tag to be appended to the ciphertext.
                ciphertext += encryptor.tag
            else:
                cipher = Cipher(
                    algorithms.AES(config.key), modes.CBC(iv), backend=default_backend()
                )
                encryptor = cipher.encryptor()
                padder = padding.PKCS7(128).padder()
                padded_data = padder.update(data.encode("utf-8")) + padder.finalize()
                ciphertext = encryptor.update(padded_data) + encryptor.finalize()

            return base64.b64encode(ciphertext).decode("utf-8"), iv.decode("utf-8")

        except Exception as e:
            raise BarkCryptoError(f"Encryption failed: {e}")

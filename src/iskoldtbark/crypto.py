import base64
import secrets
import string
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import BarkCryptoError, BarkSecurityWarning

# Alphanumeric alphabet for generated keys/IVs. Every character is one ASCII byte,
# so an N-character string is exactly N bytes (matching the iOS app, which uses the
# string's bytes directly). 62 symbols give ~5.95 bits of entropy per character,
# far more than the 4 bits/char of a hex alphabet.
_TOKEN_ALPHABET = string.ascii_letters + string.digits


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
            raise BarkCryptoError(f"AES_128_CBC requires a 16-byte key (got {len(self.key)} bytes)")
        elif self.algorithm == CryptoAlgorithm.AES_192_CBC and len(self.key) != 24:
            raise BarkCryptoError(f"AES_192_CBC requires a 24-byte key (got {len(self.key)} bytes)")
        elif (
            self.algorithm in [CryptoAlgorithm.AES_256_CBC, CryptoAlgorithm.AES_256_GCM]
            and len(self.key) != 32
        ):
            raise BarkCryptoError(
                f"{self.algorithm.value} requires a 32-byte key (got {len(self.key)} bytes)"
            )

        if self.iv is not None and len(self.iv) != 16:
            raise BarkCryptoError(f"Static IV must be exactly 16 bytes (got {len(self.iv)} bytes)")

        # A static IV with GCM reuses the same nonce on every message, which is
        # catastrophic for GCM (it leaks plaintext XOR and lets an attacker forge
        # tags). We keep accepting it for backward compatibility but warn loudly;
        # for GCM the IV should be left unset so a fresh nonce is generated per call.
        if self.iv is not None and self.algorithm == CryptoAlgorithm.AES_256_GCM:
            warnings.warn(
                "Using a static IV with AES-256-GCM reuses the GCM nonce on every "
                "message, breaking GCM confidentiality and integrity. Leave iv unset "
                "for GCM (a fresh nonce is generated per message); a static IV is only "
                "appropriate for CBC.",
                BarkSecurityWarning,
                stacklevel=2,
            )


def _generate_iv(algorithm: CryptoAlgorithm) -> bytes:
    """Generate a random IV as a fixed-length alphanumeric ASCII string.

    The Bark iOS app reads the IV as a string of a fixed length: 12 characters for
    GCM and 16 for CBC, and uses the string's bytes directly as the IV/nonce. We
    draw each character from a 62-symbol alphabet with a CSPRNG, so a 12-char GCM
    nonce carries ~71 bits of entropy and a 16-char CBC IV ~95 bits (vs 48 / 64 with
    the previous hex encoding), while keeping the exact lengths the app expects.
    """
    length = 12 if algorithm == CryptoAlgorithm.AES_256_GCM else 16
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length)).encode("utf-8")


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

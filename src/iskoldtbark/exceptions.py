class BarkError(Exception):
    """Base exception for all Bark related errors."""

    pass


class BarkAPIError(BarkError):
    """Raised when the Bark API returns an error response."""

    pass


class BarkCryptoError(BarkError):
    """Raised when encryption or decryption fails."""

    pass


class BarkValidationError(BarkError):
    """Raised when the payload parameters are invalid."""

    pass


class BarkConfigError(BarkError):
    """Raised when the multi-user configuration is missing or invalid.

    Covers unknown users/groups, a missing default user, failed migration,
    and invalid encryption settings.
    """

    pass


class BarkSecurityWarning(UserWarning):
    """Warns about a configuration that is accepted but cryptographically unsafe.

    Emitted for footguns we keep accepting for backward compatibility, e.g. a
    static IV with AES-256-GCM (which reuses the GCM nonce across messages).
    """

    pass

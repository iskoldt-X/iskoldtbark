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

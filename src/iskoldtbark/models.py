import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .exceptions import BarkValidationError


@dataclass
class BarkPayload:
    """Represents a Bark push notification payload following API V2 specs."""

    body: str
    title: Optional[str] = None
    subtitle: Optional[str] = None
    device_key: Optional[str] = None
    device_keys: Optional[List[str]] = None
    level: Optional[str] = None
    volume: Optional[int] = None
    badge: Optional[int] = None
    call: Optional[str] = None
    autoCopy: Optional[str] = None
    copy: Optional[str] = None
    sound: Optional[str] = None
    icon: Optional[str] = None
    group: Optional[str] = None
    isArchive: Optional[str] = None
    ttl: Optional[int] = None
    url: Optional[str] = None
    action: Optional[str] = None
    ciphertext: Optional[str] = None
    iv: Optional[str] = None

    def validate(self) -> None:
        """Validates payload parameters."""
        if not self.device_key and not self.device_keys:
            raise BarkValidationError("Either 'device_key' or 'device_keys' must be provided.")

        if self.level and self.level not in ["active", "timeSensitive", "passive", "critical"]:
            raise BarkValidationError(
                "Invalid 'level'. Must be active, timeSensitive, passive, or critical."
            )

        if self.volume is not None and not (0 <= self.volume <= 10):
            raise BarkValidationError("Volume must be an integer between 0 and 10.")

        if self.call and self.call != "1":
            raise BarkValidationError("call must be '1' if provided.")

        if self.autoCopy and self.autoCopy != "1":
            raise BarkValidationError("autoCopy must be '1' if provided.")

        if self.isArchive and self.isArchive != "1":
            raise BarkValidationError("isArchive must be '1' if provided.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, dropping None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

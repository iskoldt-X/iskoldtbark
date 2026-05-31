import json
from typing import Any, Dict, List, Optional

import requests

from .config import ConfigManager
from .crypto import CryptoProvider, EncryptionConfig
from .exceptions import BarkAPIError
from .models import BarkPayload


class BarkClient:
    """A highly secure Python client for the Bark Push Notification service."""

    def __init__(
        self,
        device_key: str,
        server_url: str = "https://api.day.app",
        encryption: Optional[EncryptionConfig] = None,
    ):
        """
        Initialize the Bark client.

        Args:
            device_key: Your device's unique key.
            server_url: The Bark server URL. Defaults to the official server.
            encryption: Optional E2E encryption config; enables encryption in one step
                (equivalent to calling set_encryption afterwards).
        """
        self.device_key = device_key
        self.server_url = server_url.rstrip("/")
        self.encryption_config: Optional[EncryptionConfig] = encryption
        self.session = requests.Session()

    @classmethod
    def from_config(cls) -> "BarkClient":
        """Create a BarkClient from the resolved default user in the 3-tier config."""
        config = ConfigManager.load()
        return cls(
            device_key=config.device_key,
            server_url=config.server_url,
            encryption=config.encryption_config,
        )

    def set_encryption(self, config: EncryptionConfig) -> None:
        """Configure E2E encryption for the client."""
        self.encryption_config = config

    def push(
        self,
        body: str,
        *,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        markdown: Optional[str] = None,
        device_keys: Optional[List[str]] = None,
        level: Optional[str] = None,
        volume: Optional[int] = None,
        badge: Optional[int] = None,
        call: Optional[str] = None,
        autoCopy: Optional[str] = None,
        copy: Optional[str] = None,
        sound: Optional[str] = None,
        icon: Optional[str] = None,
        image: Optional[str] = None,
        group: Optional[str] = None,
        isArchive: Optional[str] = None,
        ttl: Optional[int] = None,
        url: Optional[str] = None,
        action: Optional[str] = None,
        id: Optional[str] = None,
        delete: Optional[str] = None,
        ciphertext: Optional[str] = None,
        iv: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a push notification to this client's device.

        Every keyword argument maps to a Bark API V2 payload field. ``group`` is the
        iOS notification-grouping field; ``markdown`` overrides the rendered body;
        ``id`` (with optional ``delete="1"``) updates or removes a delivered
        notification. When encryption is configured the payload is encrypted
        transparently before sending.

        Raises:
            BarkValidationError: If the parameters are invalid.
            BarkCryptoError: If encryption fails.
            BarkAPIError: If the API request fails or returns an error.
        """
        payload = BarkPayload(
            body=body,
            device_key=self.device_key,
            title=title,
            subtitle=subtitle,
            markdown=markdown,
            device_keys=device_keys,
            level=level,
            volume=volume,
            badge=badge,
            call=call,
            autoCopy=autoCopy,
            copy=copy,
            sound=sound,
            icon=icon,
            image=image,
            group=group,
            isArchive=isArchive,
            ttl=ttl,
            url=url,
            action=action,
            id=id,
            delete=delete,
            ciphertext=ciphertext,
            iv=iv,
        )
        payload.validate()

        if self.encryption_config:
            # Encrypt the full payload JSON, excluding the routing-only device key(s).
            encrypt_payload = payload.to_dict()
            encrypt_payload.pop("device_key", None)
            encrypt_payload.pop("device_keys", None)

            json_str = json.dumps(encrypt_payload, ensure_ascii=False)
            ciphertext, iv = CryptoProvider.encrypt(json_str, self.encryption_config)
            request_data = {"device_key": self.device_key, "ciphertext": ciphertext, "iv": iv}
        else:
            request_data = payload.to_dict()

        try:
            response = self.session.post(f"{self.server_url}/push", json=request_data, timeout=30)

            try:
                data = response.json()
            except ValueError:
                data = {}

            if "code" in data and data["code"] != 200:
                raise BarkAPIError(f"Bark API Error: {data.get('message', 'Unknown error')}")

            response.raise_for_status()
            return data

        except requests.exceptions.RequestException as e:
            raise BarkAPIError(f"Request failed: {e}")

    def _get(self, path: str) -> requests.Response:
        """Issue a GET to a server utility endpoint, raising BarkAPIError on failure."""
        try:
            response = self.session.get(f"{self.server_url}{path}", timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise BarkAPIError(f"Request failed: {e}")

    def ping(self) -> Dict[str, Any]:
        """Check server connectivity (GET /ping)."""
        return self._get("/ping").json()

    def info(self) -> Dict[str, Any]:
        """Return server information such as version and build (GET /info)."""
        return self._get("/info").json()

    def healthz(self) -> str:
        """Return the server health status string (GET /healthz)."""
        return self._get("/healthz").text.strip()

    def close(self) -> None:
        """Close the underlying requests session."""
        self.session.close()

    def __enter__(self) -> "BarkClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def send(
    body: str,
    device_key: Optional[str] = None,
    *,
    server_url: str = "https://api.day.app",
    encryption: Optional[EncryptionConfig] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Send a single notification in one call.

    With ``device_key`` it builds an ad-hoc client (optionally encrypted via
    ``encryption``). Without it, it loads the default user from config, where any
    configured encryption is applied automatically. Remaining keyword arguments are
    forwarded to BarkClient.push.
    """
    if device_key is None:
        client = BarkClient.from_config()
    else:
        client = BarkClient(device_key, server_url, encryption=encryption)
    try:
        return client.push(body=body, **kwargs)
    finally:
        client.close()

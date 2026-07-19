import json
import warnings
from typing import Any, Dict, List, Optional

import requests

from .config import ConfigManager
from .crypto import CryptoProvider, EncryptionConfig
from .exceptions import BarkAPIError, BarkSecurityWarning, BarkValidationError
from .models import BarkPayload


class BarkClient:
    """A highly secure Python client for the Bark Push Notification service."""

    def __init__(
        self,
        device_key: str,
        server_url: str = "https://api.day.app",
        encryption: Optional[EncryptionConfig] = None,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize the Bark client.

        Args:
            device_key: Your device's unique key.
            server_url: The Bark server URL. Defaults to the official server.
            encryption: Optional E2E encryption config; enables encryption in one step
                (equivalent to calling set_encryption afterwards).
            timeout: Request timeout in seconds (default 30).
        """
        self.device_key = device_key
        self.server_url = server_url.rstrip("/")
        if not self.server_url.lower().startswith("https://"):
            # The device key is used for routing and is sent unencrypted; over plain
            # HTTP it (and all traffic metadata) is exposed on the wire.
            warnings.warn(
                f"server_url {self.server_url!r} is not HTTPS; the device key and "
                "traffic metadata are sent in cleartext.",
                BarkSecurityWarning,
                stacklevel=2,
            )
        self.encryption_config: Optional[EncryptionConfig] = encryption
        self.session = session or requests.Session()
        self._owns_session = session is None
        self.timeout = timeout

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

        if self.encryption_config and (ciphertext is not None or iv is not None):
            raise BarkValidationError(
                "Cannot pass pre-encrypted ciphertext/iv to a client that has encryption "
                "configured: the payload would be double-encrypted and unusable. Send "
                "pre-encrypted payloads through a client without encryption configured."
            )

        if self.encryption_config:
            # Encrypt the full payload JSON, excluding the routing-only device key(s).
            encrypt_payload = payload.to_dict()
            encrypt_payload.pop("device_key", None)
            encrypt_payload.pop("device_keys", None)

            json_str = json.dumps(encrypt_payload, ensure_ascii=False)
            ciphertext, iv = CryptoProvider.encrypt(json_str, self.encryption_config)
            request_data: Dict[str, Any] = {"ciphertext": ciphertext, "iv": iv}
            # Route on the multicast list when one was supplied, otherwise the single
            # device key. (Previously device_keys was silently dropped on this path.)
            if device_keys:
                request_data["device_keys"] = device_keys
            else:
                request_data["device_key"] = self.device_key
            # Server-side control fields must travel in plaintext. The Bark server sets
            # the APNs apns-collapse-id from `id` (and acts on `delete`) BEFORE the app
            # ever decrypts the payload; if they live only inside the ciphertext the
            # server cannot see them, so same-`id` pushes stack instead of updating in
            # place. These are non-sensitive routing keys, safe to send in the clear.
            if id is not None:
                request_data["id"] = id
            if delete is not None:
                request_data["delete"] = delete
        else:
            request_data = payload.to_dict()
            # For an unencrypted multicast, device_keys is the routing field; drop the
            # redundant single device_key so the server gets one unambiguous target.
            if device_keys:
                request_data.pop("device_key", None)

        try:
            response = self.session.post(
                f"{self.server_url}/push", json=request_data, timeout=self.timeout
            )
        except requests.exceptions.RequestException as e:
            raise BarkAPIError(f"Request failed: {e}") from e

        try:
            data = response.json()
        except ValueError:
            data = {}

        # Bark signals application-level errors with a non-200 "code" in a JSON body.
        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            raise BarkAPIError(f"Bark API Error: {data.get('message', 'Unknown error')}")

        # An HTTP error with no usable JSON "code": surface the status and body text
        # rather than returning an empty dict as though the request had succeeded.
        if not response.ok:
            detail = data if data else (response.text or "").strip()
            raise BarkAPIError(f"Bark API request failed (HTTP {response.status_code}): {detail}")

        return data if isinstance(data, dict) else {}

    def _get(self, path: str) -> requests.Response:
        """Issue a GET to a server utility endpoint, raising BarkAPIError on failure."""
        try:
            response = self.session.get(f"{self.server_url}{path}", timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            raise BarkAPIError(f"Request failed: {e}") from e

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
        """Close the underlying requests session if owned by this client."""
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> "BarkClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def send(
    body: str,
    device_key: Optional[str] = None,
    *,
    server_url: Optional[str] = None,
    encryption: Optional[EncryptionConfig] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Send a single notification in one call.

    With ``device_key`` it builds an ad-hoc client (optionally encrypted via
    ``encryption``). Without it, it loads the default user from config, where any
    configured encryption is applied automatically. Remaining keyword arguments are
    forwarded to BarkClient.push.

    Raises BarkValidationError when ``server_url`` or ``encryption`` is supplied
    without ``device_key``, since those parameters would be silently ignored
    (the from_config path has its own values).
    """
    if device_key is None:
        if server_url is not None or encryption is not None:
            raise BarkValidationError(
                "server_url and encryption are only effective when device_key is also "
                "provided. Without device_key the default user from the configuration "
                "file is used (with its own server_url and encryption). Either supply "
                "device_key or remove server_url/encryption."
            )
        client = BarkClient.from_config()
    else:
        client = BarkClient(device_key, server_url or "https://api.day.app", encryption=encryption)
    try:
        return client.push(body=body, **kwargs)
    finally:
        client.close()

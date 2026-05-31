from typing import Any, Dict, List, Optional, Union

import requests

from .crypto import CryptoProvider, EncryptionConfig
from .exceptions import BarkAPIError
from .models import BarkPayload


class BarkClient:
    """A highly secure Python client for the Bark Push Notification service."""

    def __init__(self, device_key: str, server_url: str = "https://api.day.app"):
        """
        Initialize the Bark client.

        Args:
            device_key (str): Your device's unique key.
            server_url (str, optional): The Bark server URL. Defaults to the official server.
        """
        self.device_key = device_key
        self.server_url = server_url.rstrip("/")
        self.encryption_config: Optional[EncryptionConfig] = None
        self.session = requests.Session()

    def set_encryption(self, config: EncryptionConfig) -> None:
        """
        Configure E2E encryption for the client.

        Args:
            config (EncryptionConfig): The encryption configuration.
        """
        self.encryption_config = config

    def push(self, body: str, **kwargs) -> Dict[str, Any]:
        """
        Send a push notification.

        Args:
            body (str): The main content of the notification.
            **kwargs: Additional Bark API V2 parameters (e.g., title, badge, level, etc.)

        Returns:
            Dict[str, Any]: The JSON response from the server.

        Raises:
            BarkValidationError: If the parameters are invalid.
            BarkCryptoError: If encryption fails.
            BarkAPIError: If the API request fails or returns an error.
        """
        payload = BarkPayload(body=body, device_key=self.device_key, **kwargs)
        payload.validate()

        payload_dict = payload.to_dict()

        if self.encryption_config:
            # We encrypt the whole original JSON
            json_str = payload.to_json()
            ciphertext, iv = CryptoProvider.encrypt(json_str, self.encryption_config)

            # The API V2 expects device_key, ciphertext, and iv
            request_data = {"device_key": self.device_key, "ciphertext": ciphertext, "iv": iv}
        else:
            request_data = payload_dict

        try:
            response = self.session.post(f"{self.server_url}/push", json=request_data, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 200:
                raise BarkAPIError(f"Bark API Error: {data.get('message', 'Unknown error')}")

            return data

        except requests.exceptions.RequestException as e:
            raise BarkAPIError(f"Request failed: {e}")

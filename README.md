# iskoldtbark

A secure, fully compliant Python client for the [Bark](https://github.com/Finb/Bark) push notification service.

## Features

- **Full API V2 Compliance**: Uses the official `POST /push` REST API with structured JSON payloads.
- **Maximum Security**: Supports E2E encryption using AES-256-GCM and AES-256-CBC.
- **Dynamic IV Generation**: Generates a secure, random Initialization Vector (IV) for every request to prevent replay attacks and ensure cryptographic best practices.
- **Strict Validation**: Validates all payload parameters before sending.

## Installation

```bash
pip install iskoldtbark
```
*(Note: If not published, you can install via `pip install .` in this directory)*

## Quick Start

### Basic Notification

```python
from iskoldtbark import BarkClient

client = BarkClient("YOUR_DEVICE_KEY")
client.push(
    title="Hello",
    body="This is a test notification.",
    level="active",
    badge=1,
)
```

### Encrypted Notification (AES-256-GCM)

Ensure you have configured AES-256-GCM in your Bark App (Servers -> Encryption Settings).

```python
from iskoldtbark import BarkClient, EncryptionConfig, CryptoAlgorithm

client = BarkClient("YOUR_DEVICE_KEY")

# 16, 24, or 32 byte key.
config = EncryptionConfig(
    key=b"12345678901234567890123456789012", 
    algorithm=CryptoAlgorithm.AES_256_GCM
)
client.set_encryption(config)

client.push(
    title="Top Secret",
    body="This payload is fully encrypted.",
)
```

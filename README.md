# iskoldtbark

A secure, fully compliant Python client for the [Bark](https://github.com/Finb/Bark) push notification service.

## Features

- **Full API V2 Compliance**: Uses the official `POST /push` REST API with structured JSON payloads.
- **Maximum Security**: Supports E2E encryption using AES-256-GCM and AES-256-CBC.
- **Dynamic IV Generation**: Generates a secure, random Initialization Vector (IV) for every request to prevent replay attacks and ensure cryptographic best practices.
- **Strict Validation**: Validates all payload parameters before sending.
- **Multi-User & Groups**: Manage many named recipient devices, each with its own
  per-user encryption key, organize them into recipient groups, and broadcast to a
  whole group in one command.

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

### One-liner

```python
import iskoldtbark

# Uses the default user from ~/.iskoldtbark/config.json (encryption applied automatically)
iskoldtbark.send("Deploy finished", title="CI", level="timeSensitive")

# Or supply a device key directly
iskoldtbark.send("Hello", "YOUR_DEVICE_KEY", title="Hi")
```

### Encrypted Notification (AES-256-GCM)

Ensure you have configured AES-256-GCM in your Bark App (Servers → Encryption Settings).

```python
from iskoldtbark import BarkClient, EncryptionConfig, CryptoAlgorithm

# Pass encryption directly in the constructor — no separate set_encryption() call needed.
client = BarkClient(
    "YOUR_DEVICE_KEY",
    encryption=EncryptionConfig(
        key=b"12345678901234567890123456789012",  # 32 bytes for AES-256
        algorithm=CryptoAlgorithm.AES_256_GCM,
    ),
)
client.push(body="This payload is fully encrypted.", title="Top Secret")
```

### All payload parameters

```python
client.push(
    body="Deployment finished.",      # required
    title="CI",
    subtitle="main branch",
    markdown="**bold** _italic_",     # overrides rendered body
    level="timeSensitive",            # active | timeSensitive | passive | critical
    volume=5,                         # 0–10, for critical alerts
    badge=3,
    sound="minuet.caf",
    icon="https://example.com/icon.png",
    image="https://example.com/screenshot.png",
    group="Deploys",                  # iOS notification group (UI grouping)
    url="https://github.com/run/123",
    call="1",                         # repeat sound for 30 s
    autoCopy="1",
    copy="text to copy",
    isArchive="1",
    ttl=3600,                         # seconds until archived message is deleted
    action="none",                    # tap does nothing
    id="deploy-42",                   # stable ID for update/delete
    delete="1",                       # remove notification with id="deploy-42"
)
```

### Utility endpoints

```python
client.ping()     # GET /ping  — connectivity check
client.info()     # GET /info  — server version / build info
client.healthz()  # GET /healthz — health status string
```

## Multi-User CLI

Each **user** is a named recipient Bark device with its own device key and (optional)
per-user encryption. Users can belong to many **recipient groups**, and you can
broadcast to a whole group at once.

```bash
# Set up your primary device (a nickname is required) — generates an AES-256-GCM key
iskoldtbark init --nickname phone --device-key YOUR_DEVICE_KEY

# Add more recipients
iskoldtbark user add --nickname laptop --device-key OTHER_KEY
iskoldtbark user list

# Create a recipient group and add members (a user may join many groups)
iskoldtbark group create work --description "work devices"
iskoldtbark group add-user work phone
iskoldtbark group add-user work laptop

# Send to the default user, a specific user, or broadcast to a group
iskoldtbark send "Hello"                            # -> default user
iskoldtbark send "Hello" --user laptop              # -> one user
iskoldtbark send "Build finished" --user-group work # -> every member of "work"

iskoldtbark set-default laptop   # change the default recipient
iskoldtbark config               # show the resolved configuration
```

Group broadcasts encrypt and send to each recipient independently and **continue on
individual failures**, printing a per-recipient summary (`N succeeded, M failed`). The
command exits non-zero only when *every* recipient fails.

### `--user-group` vs `--group`

These are two unrelated things and are fully orthogonal:

- **`--user-group <name>`** selects the **recipients** to broadcast to (a group of users).
- **`--group <string>`** is the unchanged Bark field that groups notifications in the iOS
  app UI (`BarkPayload.group`).

```bash
# Broadcast to recipient-group "work"; each message uses iOS UI grouping "Alerts"
iskoldtbark send "Deploy done" --user-group work --group Alerts
```

### Config & migration

Configuration lives at `~/.iskoldtbark/config.json`. An existing single-user config is
**auto-migrated** to the new multi-user format on first use (wrapped as one `default`
user, with no data loss); run `iskoldtbark migrate` to rewrite the file explicitly. The
`BARK_DEVICE_KEY` / `BARK_SERVER_URL` / `BARK_ENCRYPTION_*` environment variables still
override the **default** user.

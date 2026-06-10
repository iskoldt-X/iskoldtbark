# iskoldtbark

[![PyPI](https://img.shields.io/pypi/v/iskoldtbark)](https://pypi.org/project/iskoldtbark/)
[![Python](https://img.shields.io/pypi/pyversions/iskoldtbark)](https://pypi.org/project/iskoldtbark/)
[![Tests](https://github.com/iskoldt-X/iskoldtbark/actions/workflows/test.yml/badge.svg)](https://github.com/iskoldt-X/iskoldtbark/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Push notifications from anywhere to your iPhone — from your terminal, your scripts, your CI pipeline — with optional end-to-end encryption.**

[Bark](https://github.com/Finb/Bark) is a free, open-source iOS app that turns simple HTTP requests into native push notifications. `iskoldtbark` is a secure, fully API-V2-compliant Python client and command-line tool for it:

- 🖥️ **A powerful CLI** — send rich notifications with one command: Markdown, critical alerts that break through silence, live-updating progress notifications, remote deletion, clipboard delivery, and more.
- 👨‍👩‍👧 **Multi-device & broadcast groups** — manage many named devices, each with its own encryption key, and broadcast to all of them concurrently.
- 🔐 **Real end-to-end encryption** — AES-256-GCM with a fresh nonce per message; the server only ever stores ciphertext, and your phone decrypts on-device.
- 🐍 **A clean, fully typed Python library** — for when a shell command isn't enough.

---

## Table of Contents

- [Getting started](#getting-started)
- **Part 1 — The CLI**
  - [Your first notification in 60 seconds](#your-first-notification-in-60-seconds)
  - [The cool stuff](#the-cool-stuff)
    - [Markdown notifications](#markdown-notifications)
    - [Critical alerts that break through silence](#critical-alerts-that-break-through-silence)
    - [Live-updating notifications](#live-updating-notifications)
    - [Remotely delete a notification](#remotely-delete-a-notification)
    - [Send text straight to the clipboard](#send-text-straight-to-the-clipboard)
    - [Ring for 30 seconds](#ring-for-30-seconds)
    - [Images, icons and sounds](#images-icons-and-sounds)
    - [Control what a tap does](#control-what-a-tap-does)
    - [Grouping, badges and subtitles](#grouping-badges-and-subtitles)
    - [History control: archiving and TTL](#history-control-archiving-and-ttl)
  - [Recipes](#recipes)
  - [Multiple devices and broadcast groups](#multiple-devices-and-broadcast-groups)
  - [End-to-end encryption](#end-to-end-encryption)
  - [Configuration](#configuration)
  - [CLI reference](#cli-reference)
- **Part 2 — The Python library**
  - [The one-liner](#the-one-liner)
  - [BarkClient](#barkclient)
  - [Multicast to several devices in one request](#multicast-to-several-devices-in-one-request)
  - [Programmatic users, groups and broadcasts](#programmatic-users-groups-and-broadcasts)
  - [Encryption in code](#encryption-in-code)
  - [Error handling](#error-handling)
  - [Server utilities](#server-utilities)
  - [Advanced: sessions, timeouts and typing](#advanced-sessions-timeouts-and-typing)
  - [How the encryption works](#how-the-encryption-works)
- [Security notes](#security-notes)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Development](#development)
- [License](#license)

---

## Getting started

You need three things:

1. **The Bark app** on your iPhone — install it from the App Store ([Bark on GitHub](https://github.com/Finb/Bark)).
2. **Your device key** — shown on the app's main screen (the random string in your personal URL, e.g. `https://api.day.app/QX8X…/`).
3. **This package**:

```bash
pip install iskoldtbark
```

Python 3.8+. Installing the package also installs the `iskoldtbark` command.

---

# Part 1 — The CLI

## Your first notification in 60 seconds

```bash
# One-time setup: register your phone (also generates an AES-256-GCM key for you)
iskoldtbark init --nickname phone --device-key YOUR_DEVICE_KEY

# Send!
iskoldtbark send "Hello from my terminal 👋" --title "It works"
```

`init` prints the exact encryption settings (algorithm, mode, key) to type into the Bark app under **Servers → Encryption Settings**. Do that once and every notification you send is end-to-end encrypted. Don't want encryption? That's fine too — it just works either way.

## The cool stuff

Everything below is a single flag or two on `iskoldtbark send`. Mix and match freely.

### Markdown notifications

Send formatted text — bold, italics, lists, links, code — rendered by the Bark app:

```bash
iskoldtbark send "fallback text" --markdown "## Deploy report
**Status:** ✅ success
- build: \`3m 12s\`
- tests: \`418 passed\`
[Open dashboard](https://ci.example.com/run/123)"
```

The `--markdown` content overrides the rendered body; the plain body acts as fallback text.

### Critical alerts that break through silence

A `critical` notification sounds **even when the phone is muted or in Do Not Disturb** — and you can set its volume:

```bash
iskoldtbark send "Database is DOWN" --title "🚨 PROD ALERT" --level critical --volume 10
```

The four importance levels:

| `--level` | Behavior |
|---|---|
| `active` (default) | Normal notification, lights up the screen |
| `timeSensitive` | Breaks through Focus modes |
| `passive` | Silently added to the notification list — no wake, no sound |
| `critical` | Bypasses mute and Do Not Disturb; `--volume 0–10` controls loudness |

`passive` is great for low-priority logs you want on the phone but never want to be disturbed by.

### Live-updating notifications

Give a notification a stable `--id` and every subsequent send with the same id **replaces it in place** — one notification that acts like a progress bar:

```bash
iskoldtbark send "Starting deploy…"            --id deploy-42 --title "Deploy"
iskoldtbark send "Building… (1/3)"             --id deploy-42 --title "Deploy"
iskoldtbark send "Running migrations… (2/3)"   --id deploy-42 --title "Deploy"
iskoldtbark send "✅ Live in production (3/3)"  --id deploy-42 --title "Deploy"
```

Your phone shows a single notification that updates four times — not four stacked banners.

### Remotely delete a notification

Sent something that's no longer relevant (or never should have left)? Remove it from the phone remotely using its id:

```bash
iskoldtbark send "cleanup" --id deploy-42 --delete
```

The notification with id `deploy-42` disappears from the device.

### Send text straight to the clipboard

Push a value and have it ready to paste — perfect for verification codes, tokens, IDs:

```bash
# Attach text to the notification's copy action
iskoldtbark send "Your login code arrived" --copy "839 217"

# Or copy automatically on delivery (where iOS allows)
iskoldtbark send "API key rotated" --copy "sk-new-key-…" --auto-copy
```

Without `--copy`, the copy action uses the notification body itself.

### Ring for 30 seconds

For alerts that must not be missed, repeat the notification sound for 30 seconds:

```bash
iskoldtbark send "Server room temperature critical" --call
```

### Images, icons and sounds

```bash
iskoldtbark send "New release published" \
  --icon  "https://example.com/logo.png" \
  --image "https://example.com/screenshot.png" \
  --sound minuet.caf
```

`--icon` replaces the notification icon, `--image` attaches a picture, `--sound` picks any of the ringtones listed in the Bark app.

### Control what a tap does

```bash
# Open a URL when tapped
iskoldtbark send "Build #123 failed" --url "https://ci.example.com/run/123"

# Or make the tap do nothing at all (no app launch)
iskoldtbark send "FYI only" --action none
```

### Grouping, badges and subtitles

```bash
iskoldtbark send "Deploy finished" \
  --title "CI" --subtitle "main branch" \
  --group Deploys \
  --badge 3
```

`--group` stacks related notifications together in Notification Center and in the app's history (this is the *iOS UI* group — not to be confused with broadcast groups below). `--badge` sets the app icon's badge number.

### History control: archiving and TTL

```bash
iskoldtbark send "keep this"        --is-archive            # force-save to app history
iskoldtbark send "ephemeral ping"   --no-archive            # never saved to history
iskoldtbark send "self-destructing" --is-archive --ttl 3600 # delete from history after 1 h
```

## Recipes

Real-world combinations, ready to paste.

**CI/CD notifier** — quiet on success, impossible to miss on failure:

```bash
if make deploy; then
  iskoldtbark send "✅ ${CI_COMMIT_SHA:0:8} live" --title "Deploy" --group CI --level passive
else
  iskoldtbark send "❌ Deploy FAILED" --title "Deploy" --group CI \
    --level critical --volume 8 --url "$CI_PIPELINE_URL" --call
fi
```

**Long task with a live progress bar, then clean up after itself:**

```bash
iskoldtbark send "0%  — downloading"  --id job7 --title "Backup"
iskoldtbark send "60% — compressing"  --id job7 --title "Backup"
iskoldtbark send "100% — done ✅"      --id job7 --title "Backup"
sleep 300
iskoldtbark send x --id job7 --delete        # remove it 5 minutes later
```

**One-time code to your hand:**

```bash
iskoldtbark send "Your 2FA code" --copy "$(generate_totp)" --auto-copy --no-archive
```

**Tell the whole team the build is green** (see [broadcast groups](#multiple-devices-and-broadcast-groups)):

```bash
iskoldtbark send "v2.4.0 released 🎉" --user-group team --group Releases --markdown "$(cat RELEASE_NOTES.md)"
```

**Different notification targets per project** — drop a `.iskoldtbark.json` into a project directory (see [Configuration](#configuration)) and every `iskoldtbark send` run from that directory targets that project's device/server instead of your global default.

## Multiple devices and broadcast groups

Every **user** is a named recipient device with its own device key, its own server, and (optionally) its own encryption key. Users can be organized into **recipient groups** and a group can be broadcast to with one command.

```bash
# Register devices
iskoldtbark init --nickname phone  --device-key KEY_PHONE     # first device = default
iskoldtbark user add --nickname ipad    --device-key KEY_IPAD
iskoldtbark user add --nickname partner --device-key KEY_P --no-encryption
iskoldtbark user list
iskoldtbark user remove ipad

# Choose who gets plain `iskoldtbark send "..."`
iskoldtbark set-default phone

# Build a group (a user may belong to many groups)
iskoldtbark group create family --description "home devices"
iskoldtbark group add-user family phone
iskoldtbark group add-user family partner
iskoldtbark group list
iskoldtbark group remove-user family partner
iskoldtbark group delete family

# Target: default user, one user, or a whole group
iskoldtbark send "Hello"                          # -> default user
iskoldtbark send "Hello" --user partner           # -> one user
iskoldtbark send "Dinner is ready 🍜" --user-group family   # -> broadcast
```

Broadcast semantics:

- Each member is sent to **concurrently**, with that member's own server and encryption key.
- One failing member **never** blocks the others; you get a per-recipient summary (`N succeeded, M failed`).
- Exit code is non-zero only when **every** recipient fails (or the group is empty).

> **`--user-group` vs `--group`** — two unrelated things:
> `--user-group work` selects **who receives** the message (a recipient group).
> `--group Alerts` is the Bark payload field that visually groups notifications **on the phone**.
> They compose: `iskoldtbark send "hi" --user-group work --group Alerts`.

## End-to-end encryption

With encryption configured, the Bark server never sees your message — it stores ciphertext and your phone decrypts on-device.

`iskoldtbark init` generates a high-entropy AES-256-GCM key automatically and prints the exact values to enter in the Bark app (**Servers → Encryption Settings**). For additional users:

```bash
# Auto-generate a key with the chosen algorithm
iskoldtbark user add --nickname phone2 --device-key KEY --algo AES_256_GCM

# Bring your own key (length must match the algorithm)
iskoldtbark user add --nickname phone3 --device-key KEY \
  --algo AES_128_CBC --encryption-key "0123456789abcdef" --iv "abcdef9876543210"

# Or skip encryption for this user
iskoldtbark user add --nickname tv --device-key KEY --no-encryption
```

| `--algo` | Key length | Static `--iv` (optional) |
|---|---|---|
| `AES_256_GCM` *(recommended, default)* | 32 bytes | 12 or 16 bytes — **discouraged**, emits a security warning |
| `AES_256_CBC` | 32 bytes | 16 bytes |
| `AES_192_CBC` | 24 bytes | 16 bytes |
| `AES_128_CBC` | 16 bytes | 16 bytes |

Leave `--iv` unset (recommended): a fresh random IV/nonce is generated **per message**. Keys are ASCII strings, so a 32-character key is exactly the 32 bytes AES-256 requires — the same string you type into the app.

## Configuration

Configuration lives in three tiers; later tiers override earlier ones **for the default user**:

1. **Global** — `~/.iskoldtbark/config.json` (created with `0600`, owner-only; written atomically).
2. **Local** — `./.iskoldtbark.json` in the current directory. Use it for per-project targets: either a flat override of the default user, or a full multi-user file whose users/groups are merged on top of the global ones.
3. **Environment variables**:

| Variable | Overrides |
|---|---|
| `BARK_DEVICE_KEY` | default user's device key |
| `BARK_SERVER_URL` | default user's server URL |
| `BARK_ENCRYPTION_KEY` | default user's encryption key |
| `BARK_ENCRYPTION_ALGO` | default user's algorithm (e.g. `AES_256_GCM`) |
| `BARK_ENCRYPTION_IV` | default user's static IV |
| `BARK_USER_NICKNAME` | nickname assigned when a default user is created from a legacy/env-only config (default: `default`) |

Overrides are merged per-field, so e.g. setting only `BARK_ENCRYPTION_KEY` keeps the stored algorithm. **Overrides are never written back to disk** — commands that modify configuration (`user add`, `group create`, …) read and write only the persistent global file.

Inspect the fully resolved view at any time:

```bash
iskoldtbark config
```

Older single-user configs are migrated automatically in memory; run `iskoldtbark migrate` to rewrite the file in the new format explicitly. A config file that exists but cannot be parsed is **reported as an error and never overwritten**, so a corrupt file can't silently destroy your keys.

## CLI reference

| Command | Purpose |
|---|---|
| `iskoldtbark init` | Register your primary device, generate an encryption key |
| `iskoldtbark send BODY [flags]` | Send a notification |
| `iskoldtbark user add / list / remove` | Manage recipient devices |
| `iskoldtbark group create / list / add-user / remove-user / delete` | Manage recipient groups |
| `iskoldtbark set-default NICKNAME` | Change the default recipient |
| `iskoldtbark config` | Show the resolved configuration (keys masked) |
| `iskoldtbark migrate` | Persist a legacy config in the multi-user format |

All `send` flags:

| Flag | Payload field | Description |
|---|---|---|
| `--title` | `title` | Notification title |
| `--subtitle` | `subtitle` | Notification subtitle |
| `--markdown` | `markdown` | Markdown content (overrides rendered body) |
| `--level` | `level` | `active` \| `timeSensitive` \| `passive` \| `critical` |
| `--volume` | `volume` | 0–10, for `critical` level |
| `--badge` | `badge` | App icon badge number |
| `--sound` | `sound` | Ringtone name (e.g. `minuet.caf`) |
| `--icon` | `icon` | Custom icon URL |
| `--image` | `image` | Image URL shown in the notification |
| `--url` | `url` | URL opened on tap |
| `--copy` | `copy` | Text for the copy action |
| `--auto-copy` | `autoCopy` | Copy automatically on delivery |
| `--call` | `call` | Repeat the sound for 30 seconds |
| `--is-archive` / `--no-archive` | `isArchive` | Force-save / never save to app history |
| `--ttl` | `ttl` | Seconds until the archived message is deleted |
| `--id` | `id` | Stable id — resend to update in place |
| `--delete` | `delete` | Remove the notification with `--id` from the device |
| `--action` | `action` | `none` = tapping does nothing |
| `--group` | `group` | iOS notification grouping (UI) |
| `--user` | — | Target one named user |
| `--user-group` | — | Broadcast to a recipient group |
| `--device-key` | — | Override the resolved target's device key (single target only) |

Exit codes: `0` success (including partial broadcast success), `1` error / empty group / every recipient failed, `2` usage error.

---

# Part 2 — The Python library

Everything the CLI does is available as a typed Python API.

## The one-liner

```python
import iskoldtbark

# Uses the default user from your config — encryption applied automatically
iskoldtbark.send("Deploy finished", title="CI", level="timeSensitive")

# Or fully ad-hoc with an explicit device key
iskoldtbark.send("Hello", "YOUR_DEVICE_KEY", title="Hi")
```

All `push()` keyword arguments (below) are forwarded. Note: `server_url=` and `encryption=` are only valid together with an explicit `device_key` — without it the configured default user (including its own server and encryption) is used, and passing them raises `BarkValidationError` rather than being silently ignored.

## BarkClient

```python
from iskoldtbark import BarkClient

client = BarkClient(
    "YOUR_DEVICE_KEY",
    server_url="https://api.day.app",   # or your self-hosted server
    encryption=None,                     # see "Encryption in code"
    session=None,                        # bring your own requests.Session
    timeout=30.0,                        # seconds, per request
)

client.push(
    body="Deployment finished.",      # required; everything else optional
    title="CI",
    subtitle="main branch",
    markdown="**bold** _italic_",
    level="timeSensitive",
    volume=5,
    badge=3,
    sound="minuet.caf",
    icon="https://example.com/icon.png",
    image="https://example.com/screenshot.png",
    group="Deploys",
    url="https://ci.example.com/run/123",
    call="1",
    autoCopy="1",
    copy="text to copy",
    isArchive="1",                    # or "0" to skip history
    ttl=3600,
    action="none",
    id="deploy-42",
    delete="1",                       # with id: remove that notification
)
```

`push()` validates every field locally before sending (`BarkValidationError` on bad input) and returns the server's JSON response as a `dict`.

Clients are context managers — the underlying HTTP session is closed on exit (only if the client created it):

```python
with BarkClient("KEY") as client:
    client.push(body="hello")
```

Build a client straight from your saved configuration (default user, including encryption):

```python
client = BarkClient.from_config()
```

## Multicast to several devices in one request

`device_keys` sends one request that the server fans out to many devices:

```python
client = BarkClient("PRIMARY_KEY")
client.push(body="Maintenance at 22:00", device_keys=["KEY_A", "KEY_B", "KEY_C"])
```

With encryption configured, the encrypted payload is shared — so **all recipients must use the same key**. For per-device keys, use [`UserNotifier`](#programmatic-users-groups-and-broadcasts) instead, which performs independent per-recipient sends.

## Programmatic users, groups and broadcasts

The same registry the CLI manages is available in code:

```python
from iskoldtbark import ConfigManager, UserNotifier

notifier = UserNotifier(ConfigManager.load_multi())

notifier.send_to_default("Hello")
notifier.send_to_user("partner", "Dinner 🍜", level="timeSensitive")

result = notifier.send_to_group("team", "v2.4.0 released", group="Releases")
print(f"{result.success_count}/{result.total} delivered")
for nickname, outcome in result.per_user_results.items():
    if not outcome["ok"]:
        print(f"  {nickname} failed: {outcome['error']}")
if result.all_failed:
    raise SystemExit(1)
```

Group sends run concurrently with each member's own server and encryption key; individual failures are captured in `BarkSendResult` (`total`, `success_count`, `failure_count`, `all_failed`, `per_user_results`) instead of raising.

## Encryption in code

```python
from iskoldtbark import BarkClient, EncryptionConfig, CryptoAlgorithm

client = BarkClient(
    "YOUR_DEVICE_KEY",
    encryption=EncryptionConfig(
        key=b"12345678901234567890123456789012",   # 32 bytes for AES-256
        algorithm=CryptoAlgorithm.AES_256_GCM,
        # iv: leave unset — a fresh nonce is generated per message
    ),
)
client.push(body="This payload is fully encrypted.", title="Top Secret")
```

From stored string values (the format used by the config file):

```python
from iskoldtbark import make_encryption_config
enc = make_encryption_config("12345678901234567890123456789012", "AES_256_GCM")
```

Key lengths are validated at construction time (`BarkCryptoError` on mismatch); the algorithm/IV rules are the same as the [CLI table](#end-to-end-encryption).

## Error handling

All exceptions derive from `BarkError`, so one `except` catches everything:

```python
from iskoldtbark import (
    BarkError,            # base class
    BarkAPIError,         # network failure or error response from the server
    BarkValidationError,  # invalid payload parameters (raised before sending)
    BarkCryptoError,      # bad key/IV length, encryption failure
    BarkConfigError,      # missing/corrupt config, unknown user or group
)

try:
    client.push(body="x", level="critical", volume=10)
except BarkValidationError as e:
    print("bad parameters:", e)
except BarkAPIError as e:
    print("delivery failed:", e)
except BarkError as e:
    print("anything else bark-related:", e)
```

Security footguns that are *accepted* for compatibility (static IV with GCM, plain-HTTP server URLs) emit a `BarkSecurityWarning` (a `UserWarning` subclass) instead of raising. Make them fatal in strict environments:

```python
import warnings
from iskoldtbark import BarkSecurityWarning
warnings.simplefilter("error", BarkSecurityWarning)
```

## Server utilities

Handy for monitoring a self-hosted [bark-server](https://github.com/Finb/bark-server):

```python
client.ping()     # GET /ping    -> dict
client.info()     # GET /info    -> dict (version, build, …)
client.healthz()  # GET /healthz -> "ok"
```

All three raise `BarkAPIError` on failure, which makes them easy to wire into health checks.

## Advanced: sessions, timeouts and typing

Inject your own `requests.Session` for retries, proxies, or connection pooling — when you pass a session, you own its lifecycle (`client.close()` won't touch it):

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=0.5)))

client = BarkClient("KEY", session=session, timeout=10.0)
```

The package ships a `py.typed` marker — mypy/pyright will type-check your calls against the real signatures.

## How the encryption works

```
payload JSON ──AES (your key, fresh IV)──▶ {ciphertext, iv} ──HTTPS──▶ Bark server ──APNs──▶ 📱 decrypts on-device
```

- The **entire payload** (body, title, all fields) is serialized to JSON and encrypted. Only the routing fields — `device_key` / `device_keys` — stay in plaintext, because the server needs them to deliver.
- For **GCM**, a random 12-character nonce is generated per message and the authentication tag is appended to the ciphertext before base64 encoding — exactly the layout the Bark app expects. For **CBC**, a random 16-character IV is generated per message (PKCS7 padding).
- Generated keys and IVs are alphanumeric ASCII drawn from a CSPRNG (`secrets`), so a 32-character key is exactly 32 bytes with ~190 bits of entropy — and is the literal string you type into the app.

---

## Security notes

- Encryption keys are stored **in cleartext** in `~/.iskoldtbark/config.json` (created `0600`, owner-only, written atomically). Treat that file as a secret: don't commit it, sync it to cloud storage, or include it in backups that leave your machine.
- For AES-256-GCM, **leave the IV unset** so a fresh nonce is generated per message. A static IV with GCM reuses the nonce, which breaks both confidentiality and integrity; the client emits a `BarkSecurityWarning` if you configure one. Static IVs are only appropriate for CBC — and even there, per-message random IVs (the default) are better.
- Use an `https://` server URL. Over plain `http://`, the device key (used for routing, never encrypted) and traffic metadata travel in cleartext; the client warns in that case.
- The device key authorizes sending to your phone — anyone who has it can notify (or spam) you. Rotate it in the Bark app if it leaks.

## Troubleshooting / FAQ

**My phone shows gibberish / nothing arrives after enabling encryption.**
The key, algorithm, or mode in the Bark app doesn't match your config. Compare `iskoldtbark config` (key is masked; check length and algorithm) against **Servers → Encryption Settings** in the app. After `iskoldtbark init`, enter exactly the printed values.

**`Config file at … is corrupted` — what now?**
The file exists but isn't valid. iskoldtbark deliberately refuses to touch it (a rewrite would destroy your stored keys). Inspect and fix the JSON by hand, or remove the file and run `iskoldtbark init` again.

**A critical alert didn't break through silence.**
Check that the Bark app has notification (and critical-alert) permission in iOS Settings, and that you sent `--level critical`. `--volume` only applies to critical alerts.

**`BarkSecurityWarning: … static IV with AES-256-GCM …`**
You configured a fixed IV for GCM. Remove the IV from your config (or the `--iv` flag) so a fresh nonce is generated per message.

**Group broadcast exits 0 even though one device failed.**
That's by design: partial delivery is success. The exit code is non-zero only when *every* recipient fails. Parse the per-recipient summary if you need stricter behavior, or use `UserNotifier` in Python and check `result.failure_count`.

**Can I use my own Bark server?**
Yes — pass `--server-url https://bark.example.com` to `init`/`user add`, set `BARK_SERVER_URL`, or pass `server_url=` to `BarkClient`. Monitor it with `ping()`/`healthz()`.

## Development

```bash
git clone https://github.com/iskoldt-X/iskoldtbark
cd iskoldtbark
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

pytest                       # test suite
black src tests && isort src tests   # formatting (line length 100)
mypy src                     # type check
```

CI runs the full matrix (Python 3.8–3.13) plus formatting and type checks on every push and pull request.

## License

[MIT](LICENSE)

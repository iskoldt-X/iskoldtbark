import argparse
import os
import random
import string
import sys
from typing import Optional

from .client import BarkClient
from .config import ConfigManager


def generate_random_string(length: int) -> str:
    """Generate a cryptographically secure random string."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


def init_command(args):
    """Handles the `iskoldtbark init` command."""
    print("🚀 Initializing iskoldtbark security configuration...\n")

    device_key = args.device_key
    if not device_key:
        device_key = input("Enter your Bark Device Key (e.g., QX8X...): ").strip()
        if not device_key:
            print("❌ Device Key is required. Exiting.")
            sys.exit(1)

    print("\n🔐 Generating maximum security AES-256-GCM keys...")
    # AES-256 requires 32 bytes
    encryption_key = generate_random_string(32)

    # We will let the IV be generated dynamically per request for maximum security.
    # We don't save a static IV unless the user specifically wants one.

    ConfigManager.save_global(
        device_key=device_key, encryption_key=encryption_key, algorithm="AES_256_GCM", iv=None
    )

    print("\n✅ Configuration saved globally to `~/.iskoldtbark/config.json`.")
    print("\n" + "=" * 60)
    print("🚨 ACTION REQUIRED: Configure your Bark App 🚨")
    print("=" * 60)
    print("Open the Bark App on your phone and go to 'Encryption Settings':")
    print("  1. Algorithm : AES256")
    print("  2. Mode      : GCM")
    print(f"  3. Key       : {encryption_key}")
    print(
        "  4. Iv        : 000000000000 (Enter any 12 characters to bypass UI, we override it dynamically)"
    )
    print("=" * 60)
    print("\nAfter saving on your phone, test it immediately by running:")
    print(
        '  iskoldtbark send "Hello from CLI! Encryption is fully operational." --title "Secure System"'
    )


def send_command(args):
    """Handles the `iskoldtbark send` command."""
    try:
        # Always attempt to load from standard config (env -> local -> global)
        client = BarkClient.from_config()

        # Override device key if provided
        if args.device_key:
            client.device_key = args.device_key

        print("📡 Sending notification...")
        res = client.push(
            body=args.body,
            title=args.title,
            level=args.level,
            badge=args.badge,
            group=args.group,
            url=args.url,
        )
        print("✅ Success:", res)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="iskoldtbark: Highly secure Bark client.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init Command
    parser_init = subparsers.add_parser("init", help="Initialize and generate secure keys.")
    parser_init.add_argument("--device-key", type=str, help="Your Bark Device Key")

    # Send Command
    parser_send = subparsers.add_parser("send", help="Send a notification.")
    parser_send.add_argument("body", type=str, help="Notification body")
    parser_send.add_argument("--title", type=str, help="Notification title")
    parser_send.add_argument("--device-key", type=str, help="Override device key")
    parser_send.add_argument(
        "--level", type=str, choices=["active", "timeSensitive", "passive", "critical"]
    )
    parser_send.add_argument("--badge", type=int, help="App badge number")
    parser_send.add_argument("--group", type=str, help="Notification group")
    parser_send.add_argument("--url", type=str, help="URL to open on tap")

    args = parser.parse_args()

    if args.command == "init":
        init_command(args)
    elif args.command == "send":
        send_command(args)


if __name__ == "__main__":
    main()

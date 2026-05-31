import argparse
import random
import string
import sys

from .config import DEFAULT_SERVER_URL, ConfigManager, UserConfig, make_encryption_config
from .exceptions import BarkConfigError, BarkError
from .notifier import UserNotifier

ALGO_CHOICES = ["AES_128_CBC", "AES_192_CBC", "AES_256_CBC", "AES_256_GCM"]
ALGO_KEY_LENGTHS = {
    "AES_128_CBC": 16,
    "AES_192_CBC": 24,
    "AES_256_CBC": 32,
    "AES_256_GCM": 32,
}


def generate_random_string(length: int) -> str:
    """Generate a cryptographically secure random string."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


def _mask(secret: str, keep: int = 4) -> str:
    if not secret:
        return secret
    if len(secret) <= keep:
        return "*" * len(secret)
    return secret[:keep] + "*" * (len(secret) - keep)


def _print_bark_setup(key: str, algorithm: str) -> None:
    mode = "GCM" if algorithm.endswith("GCM") else "CBC"
    print("\n" + "=" * 60)
    print("🚨 ACTION REQUIRED: Configure your Bark App 🚨")
    print("=" * 60)
    print("Open the Bark App on your phone and go to 'Encryption Settings':")
    print(f"  1. Algorithm : {algorithm.split('_')[0]}{algorithm.split('_')[1]}")
    print(f"  2. Mode      : {mode}")
    print(f"  3. Key       : {key}")
    if mode == "GCM":
        print("  4. Iv        : 000000000000 (any 12 chars; we override it per message)")
    print("=" * 60)


def init_command(args):
    """Handles `iskoldtbark init` - sets up your primary recipient device."""
    print("🚀 Initializing iskoldtbark security configuration...\n")
    config = ConfigManager.load_multi()

    nickname = args.nickname or input("Enter a nickname for this device (e.g., phone): ").strip()
    if not nickname:
        print("❌ A nickname is required. Exiting.")
        sys.exit(1)

    device_key = args.device_key
    if not device_key:
        device_key = input("Enter your Bark Device Key (e.g., QX8X...): ").strip()
    if not device_key:
        print("❌ Device Key is required. Exiting.")
        sys.exit(1)

    print("\n🔐 Generating maximum security AES-256-GCM key...")
    encryption_key = generate_random_string(32)
    user = UserConfig(
        nickname=nickname,
        device_key=device_key,
        server_url=args.server_url or DEFAULT_SERVER_URL,
        encryption=make_encryption_config(encryption_key, "AES_256_GCM"),
    )

    try:
        config.add_user(user, make_default=True)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    print(f"\n✅ Saved user '{nickname}' (now the default) to ~/.iskoldtbark/config.json.")
    _print_bark_setup(encryption_key, "AES_256_GCM")
    print('\nTest it now:  iskoldtbark send "Encryption is operational." --title "Secure System"')


def user_add_command(args):
    """Handles `iskoldtbark user add`."""
    config = ConfigManager.load_multi()
    nickname = args.nickname or input("Enter a nickname: ").strip()
    device_key = args.device_key or input("Enter the Bark device key: ").strip()
    if not nickname or not device_key:
        print("❌ Both a nickname and a device key are required.")
        sys.exit(1)

    encryption = None
    generated_key = None
    if not args.no_encryption:
        key = args.encryption_key
        if not key:
            key = generate_random_string(ALGO_KEY_LENGTHS[args.algo])
            generated_key = key
        try:
            encryption = make_encryption_config(key, args.algo, args.iv)
        except BarkConfigError as exc:
            print(f"❌ Error: {exc}")
            sys.exit(1)

    user = UserConfig(
        nickname=nickname,
        device_key=device_key,
        server_url=args.server_url or DEFAULT_SERVER_URL,
        encryption=encryption,
    )
    try:
        config.add_user(user, make_default=args.default)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    print(f"✅ Added user '{nickname}'.")
    if generated_key:
        _print_bark_setup(generated_key, args.algo)


def user_list_command(args):
    config = ConfigManager.load_multi()
    users = config.list_users()
    if not users:
        print("No users configured. Run `iskoldtbark init` to add one.")
        return
    for user in users:
        marker = " (default)" if user.nickname == config.default_user else ""
        algo = user.encryption.algorithm.value if user.encryption else "none"
        groups = [g.name for g in config.list_groups() if user.nickname in g.members]
        print(
            f"- {user.nickname}{marker}: key={_mask(user.device_key)} "
            f"server={user.server_url} enc={algo} groups={groups or '[]'}"
        )


def user_remove_command(args):
    config = ConfigManager.load_multi()
    try:
        config.remove_user(args.nickname)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Removed user '{args.nickname}'.")


def group_create_command(args):
    config = ConfigManager.load_multi()
    try:
        config.create_group(args.name, description=args.description or "")
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Created recipient group '{args.name}'.")


def group_list_command(args):
    config = ConfigManager.load_multi()
    groups = config.list_groups()
    if not groups:
        print("No recipient groups configured.")
        return
    for group in groups:
        desc = f" - {group.description}" if group.description else ""
        print(f"- {group.name}{desc}: members={group.members or '[]'}")


def group_add_user_command(args):
    config = ConfigManager.load_multi()
    try:
        config.add_user_to_group(args.nickname, args.group)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Added '{args.nickname}' to recipient group '{args.group}'.")


def group_remove_user_command(args):
    config = ConfigManager.load_multi()
    try:
        config.remove_user_from_group(args.nickname, args.group)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Removed '{args.nickname}' from recipient group '{args.group}'.")


def group_delete_command(args):
    config = ConfigManager.load_multi()
    try:
        config.delete_group(args.name)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Deleted recipient group '{args.name}'.")


def set_default_command(args):
    config = ConfigManager.load_multi()
    try:
        config.set_default_user(args.nickname)
        ConfigManager.save_multi(config)
    except BarkConfigError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)
    print(f"✅ Default user is now '{args.nickname}'.")


def migrate_command(args):
    if not ConfigManager.is_legacy_on_disk():
        print("Config is already in the multi-user (v1) format; nothing to migrate.")
        return
    config = ConfigManager.load_multi()
    if not config.users:
        print("No configuration found to migrate.")
        return
    ConfigManager.save_multi(config)
    print("✅ Migrated configuration to the multi-user (v1) format.")


def config_show_command(args):
    config = ConfigManager.load_multi()
    print(f"default_user: {config.default_user}")
    print("users:")
    for user in config.list_users():
        algo = user.encryption.algorithm.value if user.encryption else "none"
        print(
            f"  {user.nickname}: key={_mask(user.device_key)} server={user.server_url} enc={algo}"
        )
    print("groups:")
    for group in config.list_groups():
        print(f"  {group.name}: members={group.members} desc={group.description!r}")


def _build_push_kwargs(args) -> dict:
    kwargs = {}
    if args.title:
        kwargs["title"] = args.title
    if args.level:
        kwargs["level"] = args.level
    if args.badge is not None:
        kwargs["badge"] = args.badge
    if args.url:
        kwargs["url"] = args.url
    # --group is the unchanged iOS notification grouping field (BarkPayload.group),
    # distinct from --user-group, which selects the recipients to broadcast to.
    if args.group:
        kwargs["group"] = args.group
    return kwargs


def send_command(args):
    """Handles `iskoldtbark send`."""
    try:
        config = ConfigManager.load_multi()
        notifier = UserNotifier(config)
        kwargs = _build_push_kwargs(args)

        # --device-key overrides the single resolved target (user or default);
        # it is meaningless for a group broadcast and ignored there.
        if args.device_key and not args.user_group:
            target = args.user or config.default_user
            if target and target in config.users:
                config.users[target].device_key = args.device_key

        if args.user_group:
            result = notifier.send_to_group(args.user_group, args.body, **kwargs)
            print(f"📡 Sending to recipient group '{args.user_group}' ({result.total} users)...")
            for nickname, outcome in result.per_user_results.items():
                if outcome["ok"]:
                    code = (outcome["response"] or {}).get("code", "?")
                    print(f"  - {nickname}: OK (code {code})")
                else:
                    print(f"  - {nickname}: FAILED ({outcome['error']})")
            print(f"Summary: {result.success_count} succeeded, {result.failure_count} failed.")
            if result.all_failed:
                sys.exit(1)
        elif args.user:
            print(f"📡 Sending to '{args.user}'...")
            res = notifier.send_to_user(args.user, args.body, **kwargs)
            print("✅ Success:", res)
        else:
            print("📡 Sending to default user...")
            res = notifier.send_to_default(args.body, **kwargs)
            print("✅ Success:", res)
    except BarkError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)


def _add_encryption_args(parser):
    parser.add_argument("--algo", choices=ALGO_CHOICES, default="AES_256_GCM")
    parser.add_argument("--encryption-key", help="Encryption key (generated if omitted)")
    parser.add_argument(
        "--iv", help="Static IV, 16 bytes (recommended for CBC; GCM normally uses a per-message IV)"
    )
    parser.add_argument(
        "--no-encryption", action="store_true", help="Add the user without encryption"
    )
    parser.add_argument("--server-url", help=f"Bark server URL (default {DEFAULT_SERVER_URL})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="iskoldtbark: Highly secure multi-user Bark client."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Initialize and add your primary device.")
    p_init.add_argument("--nickname", help="A nickname for this device (prompted if omitted)")
    p_init.add_argument("--device-key", help="Your Bark Device Key")
    p_init.add_argument("--server-url", help=f"Bark server URL (default {DEFAULT_SERVER_URL})")
    p_init.set_defaults(func=init_command)

    p_send = subparsers.add_parser("send", help="Send a notification.")
    p_send.add_argument("body", help="Notification body")
    target = p_send.add_mutually_exclusive_group()
    target.add_argument("--user", help="Send to a single user by nickname")
    target.add_argument(
        "--user-group",
        dest="user_group",
        help="Broadcast to a recipient group (who receives); orthogonal to --group",
    )
    p_send.add_argument("--group", help="iOS notification grouping (BarkPayload.group)")
    p_send.add_argument("--title")
    p_send.add_argument("--level", choices=["active", "timeSensitive", "passive", "critical"])
    p_send.add_argument("--badge", type=int, help="App badge number")
    p_send.add_argument("--url", help="URL to open on tap")
    p_send.add_argument("--device-key", help="Override device key for the single target")
    p_send.set_defaults(func=send_command)

    p_user = subparsers.add_parser("user", help="Manage recipient users.")
    user_sub = p_user.add_subparsers(dest="user_command", required=True)
    p_user_add = user_sub.add_parser("add", help="Add a recipient user.")
    p_user_add.add_argument("--nickname")
    p_user_add.add_argument("--device-key")
    p_user_add.add_argument("--default", action="store_true", help="Mark as the default user")
    _add_encryption_args(p_user_add)
    p_user_add.set_defaults(func=user_add_command)
    user_sub.add_parser("list", help="List users.").set_defaults(func=user_list_command)
    p_user_rm = user_sub.add_parser("remove", help="Remove a user.")
    p_user_rm.add_argument("nickname")
    p_user_rm.set_defaults(func=user_remove_command)

    p_group = subparsers.add_parser("group", help="Manage recipient groups.")
    group_sub = p_group.add_subparsers(dest="group_command", required=True)
    p_group_create = group_sub.add_parser("create", help="Create a recipient group.")
    p_group_create.add_argument("name")
    p_group_create.add_argument("--description")
    p_group_create.set_defaults(func=group_create_command)
    group_sub.add_parser("list", help="List recipient groups.").set_defaults(
        func=group_list_command
    )
    p_group_add = group_sub.add_parser("add-user", help="Add a user to a group.")
    p_group_add.add_argument("group")
    p_group_add.add_argument("nickname")
    p_group_add.set_defaults(func=group_add_user_command)
    p_group_rm = group_sub.add_parser("remove-user", help="Remove a user from a group.")
    p_group_rm.add_argument("group")
    p_group_rm.add_argument("nickname")
    p_group_rm.set_defaults(func=group_remove_user_command)
    p_group_del = group_sub.add_parser("delete", help="Delete a recipient group.")
    p_group_del.add_argument("name")
    p_group_del.set_defaults(func=group_delete_command)

    p_default = subparsers.add_parser("set-default", help="Set the default user.")
    p_default.add_argument("nickname")
    p_default.set_defaults(func=set_default_command)

    subparsers.add_parser(
        "migrate", help="Persist a legacy single-user config in the new format."
    ).set_defaults(func=migrate_command)
    subparsers.add_parser("config", help="Show the resolved configuration.").set_defaults(
        func=config_show_command
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

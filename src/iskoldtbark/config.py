import json
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .crypto import CryptoAlgorithm, EncryptionConfig
from .exceptions import BarkConfigError, BarkCryptoError, BarkValidationError

DEFAULT_SERVER_URL = "https://api.day.app"
CONFIG_VERSION = 1
NICKNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def make_encryption_config(
    key: str, algorithm: str = CryptoAlgorithm.AES_256_GCM.value, iv: Optional[str] = None
) -> EncryptionConfig:
    """Build an EncryptionConfig from stored string values.

    The key and IV are stored as UTF-8 strings in the config and encoded back to
    bytes here, matching the format the single-user config has always used. The
    only static-IV constraint is the one crypto.py has always enforced (exactly
    16 bytes); GCM normally uses a per-message IV (leave the IV unset).
    """
    algo = CryptoAlgorithm(algorithm)
    key_bytes = key.encode("utf-8")
    try:
        if iv:
            return EncryptionConfig(key=key_bytes, algorithm=algo, iv=iv.encode("utf-8"))
        return EncryptionConfig(key=key_bytes, algorithm=algo)
    except BarkCryptoError as exc:
        raise BarkConfigError(str(exc))


def _encryption_to_dict(enc: EncryptionConfig) -> Dict[str, Any]:
    return {
        "key": enc.key.decode("utf-8"),
        "algorithm": enc.algorithm.value,
        "iv": enc.iv.decode("utf-8") if enc.iv else None,
    }


@dataclass
class BarkConfig:
    """Holds the resolved single-recipient configuration for the Bark client."""

    device_key: str
    server_url: str
    encryption_config: Optional[EncryptionConfig] = None


@dataclass
class UserConfig:
    """A single named recipient Bark device."""

    nickname: str
    device_key: str
    server_url: str = DEFAULT_SERVER_URL
    encryption: Optional[EncryptionConfig] = None

    def to_client(self, session: Optional[Any] = None):
        """Build a single-recipient BarkClient configured for this user."""
        # Imported lazily to avoid a config <-> client import cycle.
        from .client import BarkClient

        return BarkClient(
            self.device_key, self.server_url, encryption=self.encryption, session=session
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "device_key": self.device_key,
            "server_url": self.server_url,
            "encryption": _encryption_to_dict(self.encryption) if self.encryption else None,
        }
        return data


@dataclass
class RecipientGroup:
    """A named set of recipient nicknames. Not the BarkPayload.group iOS field."""

    name: str
    members: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"description": self.description, "members": list(self.members)}


@dataclass
class MultiUserConfig:
    """The full multi-user registry: users, recipient groups, and a default user."""

    version: int = CONFIG_VERSION
    users: Dict[str, UserConfig] = field(default_factory=dict)
    groups: Dict[str, RecipientGroup] = field(default_factory=dict)
    default_user: Optional[str] = None

    # --- user management ------------------------------------------------
    def get_user(self, nickname: str) -> UserConfig:
        user = self.users.get(nickname)
        if user is None:
            raise BarkConfigError(f"Unknown user '{nickname}'.")
        return user

    def list_users(self) -> List[UserConfig]:
        return list(self.users.values())

    def add_user(self, user: UserConfig, make_default: bool = False) -> None:
        if not NICKNAME_RE.match(user.nickname):
            raise BarkConfigError(
                f"Invalid nickname '{user.nickname}'. Use 1-32 chars of [A-Za-z0-9_-]."
            )
        if user.nickname in self.users:
            raise BarkConfigError(f"User '{user.nickname}' already exists.")
        self.users[user.nickname] = user
        if make_default or self.default_user is None:
            self.default_user = user.nickname

    def remove_user(self, nickname: str) -> None:
        self.get_user(nickname)
        del self.users[nickname]
        for group in self.groups.values():
            if nickname in group.members:
                group.members.remove(nickname)
        if self.default_user == nickname:
            self.default_user = next(iter(self.users), None)

    def set_default_user(self, nickname: str) -> None:
        self.get_user(nickname)
        self.default_user = nickname

    # --- group management -----------------------------------------------
    def get_group(self, name: str) -> RecipientGroup:
        group = self.groups.get(name)
        if group is None:
            raise BarkConfigError(f"Unknown recipient group '{name}'.")
        return group

    def list_groups(self) -> List[RecipientGroup]:
        return list(self.groups.values())

    def create_group(self, name: str, description: str = "") -> RecipientGroup:
        if name in self.groups:
            raise BarkConfigError(f"Recipient group '{name}' already exists.")
        group = RecipientGroup(name=name, description=description)
        self.groups[name] = group
        return group

    def delete_group(self, name: str) -> None:
        self.get_group(name)
        del self.groups[name]

    def add_user_to_group(self, nickname: str, group_name: str) -> None:
        self.get_user(nickname)
        group = self.get_group(group_name)
        if nickname not in group.members:
            group.members.append(nickname)

    def remove_user_from_group(self, nickname: str, group_name: str) -> None:
        group = self.get_group(group_name)
        if nickname in group.members:
            group.members.remove(nickname)

    def get_group_members(self, group_name: str) -> List[UserConfig]:
        group = self.get_group(group_name)
        return [self.users[n] for n in group.members if n in self.users]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "default_user": self.default_user,
            "users": {nick: user.to_dict() for nick, user in self.users.items()},
            "groups": {name: group.to_dict() for name, group in self.groups.items()},
        }


class ConfigManager:
    GLOBAL_CONFIG_DIR = Path.home() / ".iskoldtbark"
    GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"
    # Resolved at read time (see _local_config_file) so the path tracks the current
    # working directory instead of freezing whatever cwd was active at import time.
    # Tests override this attribute directly; a non-None value takes precedence.
    LOCAL_CONFIG_FILE: Optional[Path] = None

    # --- low-level helpers ----------------------------------------------
    @classmethod
    def _local_config_file(cls) -> Path:
        if cls.LOCAL_CONFIG_FILE is not None:
            return Path(cls.LOCAL_CONFIG_FILE)
        return Path.cwd() / ".iskoldtbark.json"

    @classmethod
    def _read_json(cls, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            # Never silently treat a corrupt file as "no config": a later save_*()
            # would atomically overwrite it and permanently destroy the real data.
            raise BarkConfigError(
                f"Config file at {path} is corrupted and could not be parsed ({exc}). "
                "Fix or remove the file before continuing."
            )
        except OSError as exc:
            raise BarkConfigError(f"Could not read config file at {path}: {exc}")

    @staticmethod
    def _is_multi(raw: Dict[str, Any]) -> bool:
        return bool(raw) and ("users" in raw or raw.get("version") == CONFIG_VERSION)

    @classmethod
    def _parse_multi(cls, raw: Dict[str, Any]) -> MultiUserConfig:
        config = MultiUserConfig(version=CONFIG_VERSION, default_user=raw.get("default_user"))
        for nick, u in (raw.get("users") or {}).items():
            if not NICKNAME_RE.match(nick):
                raise BarkConfigError(f"Invalid nickname '{nick}' in config.")
            enc = u.get("encryption")
            config.users[nick] = UserConfig(
                nickname=nick,
                device_key=u["device_key"],
                server_url=u.get("server_url", DEFAULT_SERVER_URL),
                encryption=cls._build_encryption(enc) if enc else None,
            )
        for gname, g in (raw.get("groups") or {}).items():
            config.groups[gname] = RecipientGroup(
                name=gname,
                members=list(g.get("members", [])),
                description=g.get("description", ""),
            )
        cls._prune_dangling(config)
        if config.default_user and config.default_user not in config.users:
            config.default_user = None
        return config

    @classmethod
    def _migrate_flat(cls, raw: Dict[str, Any]) -> MultiUserConfig:
        """Wrap a legacy single-user (v0) config into a one-user MultiUserConfig.

        Preserves every legacy field (device_key, server_url, encryption_*) with
        no data loss. Returns an empty registry if there is no device_key.
        """
        config = MultiUserConfig()
        device_key = raw.get("device_key")
        if not device_key:
            return config
        nickname = os.environ.get("BARK_USER_NICKNAME", "default")
        encryption = None
        if raw.get("encryption_key"):
            encryption = cls._build_encryption(
                {
                    "key": raw["encryption_key"],
                    "algorithm": raw.get("encryption_algo", CryptoAlgorithm.AES_256_GCM.value),
                    "iv": raw.get("encryption_iv"),
                }
            )
        config.users[nickname] = UserConfig(
            nickname=nickname,
            device_key=device_key,
            server_url=raw.get("server_url", DEFAULT_SERVER_URL),
            encryption=encryption,
        )
        config.default_user = nickname
        return config

    @classmethod
    def _build_encryption(cls, enc: Dict[str, Any]) -> EncryptionConfig:
        return make_encryption_config(
            enc["key"], enc.get("algorithm", CryptoAlgorithm.AES_256_GCM.value), enc.get("iv")
        )

    @staticmethod
    def _prune_dangling(config: MultiUserConfig) -> None:
        for group in config.groups.values():
            dangling = [n for n in group.members if n not in config.users]
            if dangling:
                warnings.warn(
                    f"Recipient group '{group.name}' references unknown users {dangling}; "
                    "dropping them.",
                    stacklevel=2,
                )
                group.members = [n for n in group.members if n in config.users]

    @classmethod
    def _overlay_default_user(cls, config: MultiUserConfig, source: Dict[str, Any]) -> None:
        """Apply flat v0-style keys from `source` onto the default user.

        Used for the local-file and environment-variable tiers so the historical
        env -> local -> global cascade keeps working for the default recipient.
        """
        device_key = source.get("device_key")
        nickname = config.default_user or os.environ.get("BARK_USER_NICKNAME", "default")
        user = config.users.get(nickname)
        if user is None:
            if not device_key:
                return
            user = UserConfig(nickname=nickname, device_key=device_key)
            config.users[nickname] = user
            if config.default_user is None:
                config.default_user = nickname
        elif device_key:
            user.device_key = device_key

        if source.get("server_url"):
            user.server_url = source["server_url"]

        # Overlay encryption per-field so a tier that supplies only some keys (e.g.
        # just encryption_key, or just encryption_iv) inherits the rest from the
        # lower tier, matching the original flat env -> local -> global cascade.
        if any(k in source for k in ("encryption_key", "encryption_algo", "encryption_iv")):
            existing = user.encryption
            key = source.get("encryption_key")
            if key is None and existing is not None:
                key = existing.key.decode("utf-8")
            if key is not None:
                algorithm = source.get("encryption_algo")
                if not algorithm:
                    algorithm = (
                        existing.algorithm.value if existing else CryptoAlgorithm.AES_256_GCM.value
                    )
                if "encryption_iv" in source:
                    iv = source.get("encryption_iv")
                elif existing is not None and existing.iv is not None:
                    iv = existing.iv.decode("utf-8")
                else:
                    iv = None
                user.encryption = cls._build_encryption(
                    {"key": key, "algorithm": algorithm, "iv": iv}
                )

    @classmethod
    def _env_overrides(cls) -> Dict[str, Any]:
        keys = {
            "device_key": "BARK_DEVICE_KEY",
            "server_url": "BARK_SERVER_URL",
            "encryption_key": "BARK_ENCRYPTION_KEY",
            "encryption_algo": "BARK_ENCRYPTION_ALGO",
            "encryption_iv": "BARK_ENCRYPTION_IV",
        }
        return {field: os.environ[env] for field, env in keys.items() if env in os.environ}

    # --- public API -----------------------------------------------------
    @classmethod
    def load_multi(cls) -> MultiUserConfig:
        """Load the multi-user registry, auto-migrating a legacy config in memory.

        Reads the global store (v1, or a migrated v0 file), then overlays the
        local file and environment variables onto the default user. This never
        writes to disk; persistence happens only through save_multi().
        """
        global_raw = cls._read_json(cls.GLOBAL_CONFIG_FILE)
        if cls._is_multi(global_raw):
            config = cls._parse_multi(global_raw)
        else:
            config = cls._migrate_flat(global_raw)

        local_raw = cls._read_json(cls._local_config_file())
        if cls._is_multi(local_raw):
            local_config = cls._parse_multi(local_raw)
            config.users.update(local_config.users)
            config.groups.update(local_config.groups)
            if local_config.default_user:
                config.default_user = local_config.default_user
        elif local_raw:
            cls._overlay_default_user(config, local_raw)

        env = cls._env_overrides()
        if env:
            cls._overlay_default_user(config, env)

        return config

    @classmethod
    def load(cls) -> BarkConfig:
        """Resolve the default user into a single-recipient BarkConfig.

        Kept for backward compatibility: BarkClient.from_config() relies on it.
        The historical env -> local -> global cascade still targets the default
        user, and the "device key is missing" error is preserved.
        """
        config = cls.load_multi()
        if not config.default_user or config.default_user not in config.users:
            raise BarkValidationError(
                "Bark device key is missing. Please set BARK_DEVICE_KEY or run `iskoldtbark init`."
            )
        user = config.users[config.default_user]
        return BarkConfig(
            device_key=user.device_key,
            server_url=user.server_url,
            encryption_config=user.encryption,
        )

    @classmethod
    def _validate(cls, config: MultiUserConfig) -> None:
        if config.default_user is not None and config.default_user not in config.users:
            raise BarkConfigError(f"Default user '{config.default_user}' does not exist.")
        if config.default_user is None and config.users:
            raise BarkConfigError("A default user must be set when users exist.")
        for nick in config.users:
            if not NICKNAME_RE.match(nick):
                raise BarkConfigError(f"Invalid nickname '{nick}'.")
        for group in config.groups.values():
            for member in group.members:
                if member not in config.users:
                    raise BarkConfigError(
                        f"Recipient group '{group.name}' references unknown user '{member}'."
                    )

    @classmethod
    def save_multi(cls, config: MultiUserConfig) -> None:
        """Persist the registry as v1, validating first and writing atomically."""
        cls._validate(config)
        cls.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cls.GLOBAL_CONFIG_DIR, 0o700)
        except OSError:
            pass

        tmp_path = cls.GLOBAL_CONFIG_FILE.parent / (cls.GLOBAL_CONFIG_FILE.name + ".tmp")
        try:
            fd = os.open(tmp_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(config.to_dict(), f, indent=4)
            os.replace(tmp_path, cls.GLOBAL_CONFIG_FILE)
        except Exception as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise BarkConfigError(f"Failed to save config: {exc}")

    @classmethod
    def is_legacy_on_disk(cls) -> bool:
        """True if the global config file exists in the legacy (v0) flat format."""
        raw = cls._read_json(cls.GLOBAL_CONFIG_FILE)
        return bool(raw) and not cls._is_multi(raw)

    @classmethod
    def save_global(
        cls, device_key: str, encryption_key: str, algorithm: str, iv: Optional[str] = None
    ):
        """Save a legacy single-user configuration (retained for compatibility)."""
        cls.GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(cls.GLOBAL_CONFIG_DIR, 0o700)
        except OSError:
            pass

        data = {
            "device_key": device_key,
            "encryption_key": encryption_key,
            "encryption_algo": algorithm,
        }
        if iv:
            data["encryption_iv"] = iv

        # Create with 0600 from the start (like save_multi) so the plaintext key is
        # never briefly world-readable at the process umask; enforce it for an
        # existing file too, since O_CREAT only sets the mode on creation.
        fd = os.open(cls.GLOBAL_CONFIG_FILE, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=4)
        try:
            os.chmod(cls.GLOBAL_CONFIG_FILE, 0o600)
        except OSError:
            pass

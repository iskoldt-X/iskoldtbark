import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Dict

from .config import MultiUserConfig
from .exceptions import BarkConfigError


@dataclass
class BarkSendResult:
    """Aggregated outcome of a group broadcast.

    per_user_results maps each nickname to {"ok": bool, "response": dict|None,
    "error": str|None}.
    """

    group_name: str
    total: int
    success_count: int
    per_user_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def failure_count(self) -> int:
        return self.total - self.success_count

    @property
    def all_failed(self) -> bool:
        return self.total > 0 and self.success_count == 0


class UserNotifier:
    """Orchestrates sending to a single user, the default user, or a whole group.

    Sits above the single-recipient BarkClient. Each recipient gets its own
    BarkClient (built from that user's per-user encryption), so a group with
    mixed keys is delivered as independent per-recipient sends.
    """

    def __init__(self, config: MultiUserConfig):
        self.config = config

    def send_to_user(self, nickname: str, body: str, **kwargs: Any) -> Dict[str, Any]:
        user = self.config.get_user(nickname)
        client = user.to_client()
        try:
            return client.push(body=body, **kwargs)
        finally:
            client.close()

    def send_to_default(self, body: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.config.default_user:
            raise BarkConfigError(
                "No default user set. Use --user or --group, or run `iskoldtbark set-default`."
            )
        return self.send_to_user(self.config.default_user, body, **kwargs)

    def send_to_group(self, group_name: str, body: str, **kwargs: Any) -> BarkSendResult:
        group = self.config.get_group(group_name)
        results: Dict[str, Dict[str, Any]] = {}
        success_count = 0

        def _send_to_member(nickname: str) -> tuple:
            # Each recipient gets its own client with its own requests.Session: a
            # single Session is not guaranteed thread-safe across the pool below.
            try:
                user = self.config.get_user(nickname)
                client = user.to_client()
            except Exception as exc:
                return nickname, {"ok": False, "response": None, "error": str(exc)}
            try:
                response = client.push(body=body, **kwargs)
                return nickname, {"ok": True, "response": response, "error": None}
            except Exception as exc:
                # Record any per-recipient failure and keep going, so one bad
                # recipient never aborts delivery to the rest of the group.
                return nickname, {"ok": False, "response": None, "error": str(exc)}
            finally:
                client.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_send_to_member, nick) for nick in group.members]
            for future in concurrent.futures.as_completed(futures):
                nickname, outcome = future.result()
                results[nickname] = outcome
                if outcome["ok"]:
                    success_count += 1

        return BarkSendResult(
            group_name=group_name,
            total=len(group.members),
            success_count=success_count,
            per_user_results=results,
        )

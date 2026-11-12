"""Framework-independent errors and the shared clock contract."""

from dataclasses import dataclass, field
import time
from typing import Protocol


class Clock(Protocol):
    def now_epoch(self) -> int: ...


class SystemClock:
    def now_epoch(self) -> int:
        return int(time.time())


@dataclass
class DomainError(Exception):
    code: str
    message: str
    fields: dict[str, str] = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)


def auth_required() -> DomainError:
    return DomainError("AUTH_REQUIRED", "登录已失效，请重新打开登录页并登录。")


USERNAME_MAX_BYTES = 256
PASSWORD_MAX_BYTES = 1024


def validate_credentials(username, password) -> tuple[str, str]:
    """Shared initialization/login bounds; passwords are never normalized."""
    fields = {}
    username = username.strip() if isinstance(username, str) else username
    for name, value, label, limit in (
        ("username", username, "账号", USERNAME_MAX_BYTES),
        ("password", password, "密码", PASSWORD_MAX_BYTES),
    ):
        if not isinstance(value, str) or not value:
            fields[name] = f"请输入{label}。"
            continue
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError:
            fields[name] = f"{label}包含无效 Unicode 字符。"
            continue
        if size > limit:
            fields[name] = f"{label}不能超过 {limit} 个 UTF-8 字节。"
    if fields:
        raise DomainError("INVALID_INPUT", "请检查账号和密码。", fields)
    return username, password

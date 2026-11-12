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


# Shared pure query rules. Input bounds are checked before int/SQLite conversion.
SQLITE_ID_MAX = 9223372036854775807


def resource_id(value, field_name: str = "room_id") -> int:
    if type(value) is int:
        valid = 1 <= value <= SQLITE_ID_MAX
    elif isinstance(value, str):
        limit = str(SQLITE_ID_MAX)
        valid = (1 <= len(value) <= len(limit) and value[0] != "0"
                 and all("0" <= char <= "9" for char in value)
                 and (len(value) < len(limit) or value <= limit))
    else:
        valid = False
    if not valid:
        raise DomainError("INVALID_INPUT", "请检查会议室编号。",
                          {field_name: "请选择有效的会议室。"})
    return int(value)


def beijing_day(value) -> tuple[int, int]:
    from datetime import date, datetime, time as daytime, timedelta
    import re
    from zoneinfo import ZoneInfo

    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        day = date.fromisoformat(value)
        following = day + timedelta(days=1)
        zone = ZoneInfo("Asia/Shanghai")
        return (int(datetime.combine(day, daytime.min, zone).timestamp()),
                int(datetime.combine(following, daytime.min, zone).timestamp()))
    except (ValueError, OverflowError, OSError):
        raise DomainError("INVALID_INPUT", "请检查查询日期。",
                          {"date": "请输入有效的北京时间日期（YYYY-MM-DD），且不晚于 9999-12-30。"}) from None


def local_time(epoch: int) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(epoch, ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def active_status(start_at: int, end_at: int, now: int) -> str:
    if now < start_at:
        return "pending"
    return "in_progress" if now < end_at else "ended"


def beijing_datetime(value, field_name: str) -> int:
    """Parse one strict half-hour local input; also reusable for future blocks."""
    from datetime import datetime
    import re
    from zoneinfo import ZoneInfo

    try:
        if (not isinstance(value, str) or len(value) != 16
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:(00|30)", value)):
            raise ValueError
        local = datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return int(local.timestamp())
    except (ValueError, OverflowError, OSError):
        raise DomainError("INVALID_INPUT", "请检查查询时间。", {
            field_name: "请输入有效的北京时间（YYYY-MM-DDTHH:MM），分钟仅限 00 或 30。",
        }) from None


def validate_booking_window(start_at: int, end_at: int, now: int) -> None:
    """Pure shared query/booking rule; callers provide one captured server time."""
    fields = {}
    if start_at <= now:
        fields["start"] = "开始时间必须晚于当前北京时间。"
    if end_at <= start_at:
        fields["end"] = "结束时间必须晚于开始时间。"
    elif end_at - start_at < 1800 or end_at - start_at > 14400:
        fields["end"] = "时长须为 30 分钟至 4 小时。"
    if end_at > now + 30 * 86400:
        fields["end"] = "结束时间不能超过当前时刻起 30 天。"
    if fields:
        raise DomainError("INVALID_INPUT", "请检查起止时间。", fields)
    # Reject out-of-window dates before formatting: year 0001 Beijing can map
    # to UTC year 0000, which datetime.fromtimestamp cannot represent.
    if local_time(start_at)[:10] != local_time(end_at)[:10]:
        raise DomainError("INVALID_INPUT", "请检查起止时间。", {
            "end": "起止时间须在同一北京时间日期内，次日 00:00 也算跨日。",
        })


def booking_interval(start, end, now: int) -> tuple[int, int]:
    fields, parsed = {}, {}
    for name, value in (("start", start), ("end", end)):
        try:
            parsed[name] = beijing_datetime(value, name)
        except DomainError as error:
            fields.update(error.fields)
    if fields:
        raise DomainError("INVALID_INPUT", "请检查起止时间。", fields)
    validate_booking_window(parsed["start"], parsed["end"], now)
    return parsed["start"], parsed["end"]


def positive_integer(value, field_name: str = "attendees") -> int:
    """Strict JSON/service integer rule: bool, float and numeric text are invalid."""
    if type(value) is not int or value < 1:
        raise DomainError("INVALID_INPUT", "请检查预计人数。", {field_name: "预计人数须为正整数。"})
    return value


def query_attendees(value) -> int:
    """Canonical URL integer, capped at 1001 (the no-matching-room sentinel).

    Never convert unbounded text to int or bind an unbounded integer to SQLite.
    Future JSON commands must use positive_integer rather than this URL adapter.
    """
    if isinstance(value, str):
        if not value or value[0] == "0" or not all("0" <= char <= "9" for char in value):
            raise DomainError("INVALID_INPUT", "请检查预计人数。", {"attendees": "预计人数须为无前导零的正整数。"})
        if len(value) > 4 or (len(value) == 4 and value > "1000"):
            return 1001
        return int(value)
    return min(positive_integer(value), 1001)

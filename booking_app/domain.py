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
        label = {"booking_id": "预约", "block_id": "停用"}.get(field_name, "会议室")
        raise DomainError("INVALID_INPUT", f"请检查{label}编号。",
                          {field_name: f"请选择有效的{label}。"})
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


def normalized_text(value, field_name: str, limit: int) -> str:
    if isinstance(value, str):
        value = value.strip()
        try:
            valid = 1 <= len(value) <= limit and "\x00" not in value
            value.encode("utf-8")
        except UnicodeEncodeError:
            valid = False
        if valid:
            return value
    raise DomainError("INVALID_INPUT", "请检查活动内容。", {
        field_name: f"请输入 1—{limit} 个有效字符，不含空字符。",
    })


def normalize_booking_payload(payload) -> tuple[dict, str]:
    """Static normalization only; current time/capacity require the write snapshot."""
    import re

    if not isinstance(payload, dict):
        raise DomainError("INVALID_INPUT", "请求内容必须是一个对象。")
    fields, normalized = {}, {}
    validators = {
        "room_id": lambda value: resource_id(value) if type(value) is int else resource_id(None),
        "title": lambda value: normalized_text(value, "title", 80),
        "purpose": lambda value: normalized_text(value, "purpose", 500),
        "attendees": positive_integer,
        "start": lambda value: beijing_datetime(value, "start"),
        "end": lambda value: beijing_datetime(value, "end"),
    }
    for name, validate in validators.items():
        try:
            normalized[name + "_at" if name in ("start", "end") else name] = validate(payload.get(name))
        except DomainError as error:
            fields.update(error.fields)
    key = payload.get("intent_key")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", key):
        fields["intent_key"] = "提交标识无效，请重新选择会议室填写活动。"
    if fields:
        raise DomainError("INVALID_INPUT", "请检查预约信息。", fields)
    return normalized, key


def normalize_room_payload(payload) -> dict:
    """Room writes always validate a complete object before changing any field."""
    if not isinstance(payload, dict):
        raise DomainError("INVALID_INPUT", "请求内容必须是一个对象。")
    fields, values = {}, {}
    for name, limit in (("name", 80), ("location", 120)):
        try:
            values[name] = normalized_text(payload.get(name), name, limit)
        except DomainError as error:
            fields.update(error.fields)
    capacity = payload.get("capacity")
    if type(capacity) is not int or not 1 <= capacity <= 1000:
        fields["capacity"] = "容量须为 1—1000 的整数。"
    else:
        values["capacity"] = capacity
    if fields:
        raise DomainError("INVALID_INPUT", "请检查会议室资料。", fields)
    return values


def normalize_block_payload(payload) -> dict:
    """Static block fields; the write transaction supplies the window's clock."""
    if not isinstance(payload, dict):
        raise DomainError("INVALID_INPUT", "请求内容必须是一个对象。")
    fields, values = {}, {}
    validators = {
        "room_id": lambda value: resource_id(value) if type(value) is int else resource_id(None),
        "start": lambda value: beijing_datetime(value, "start"),
        "end": lambda value: beijing_datetime(value, "end"),
        "reason": lambda value: normalized_text(value, "reason", 500),
    }
    for name, validate in validators.items():
        try:
            values[name + "_at" if name in ("start", "end") else name] = validate(payload.get(name))
        except DomainError as error:
            fields.update(error.fields)
    if fields:
        raise DomainError("INVALID_INPUT", "请检查停用信息。", fields)
    return values


def validate_block_window(start_at: int, end_at: int, now: int) -> None:
    fields = {}
    if start_at <= now:
        fields["start"] = "开始时间必须晚于当前北京时间。"
    if end_at <= start_at:
        fields["end"] = "结束时间必须晚于开始时间。"
    if end_at > now + 30 * 86400:
        fields["end"] = "结束时间不能超过当前时刻起 30 天。"
    if fields:
        raise DomainError("INVALID_INPUT", "请检查停用起止时间。", fields)


def normalize_revoke_payload(payload) -> str:
    if not isinstance(payload, dict):
        raise DomainError("INVALID_INPUT", "请求内容必须是一个对象。")
    try:
        return normalized_text(payload.get("reason"), "reason", 500)
    except DomainError as error:
        raise DomainError("INVALID_INPUT", "请检查撤销原因。", error.fields) from None


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

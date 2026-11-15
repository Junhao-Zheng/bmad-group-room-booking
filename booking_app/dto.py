"""Explicit public allowlists; storage rows are never serialized wholesale."""

import json

from .domain import active_status, local_time


_SNAPSHOT_KEYS = {
    "cancellation_request": {"id", "booking_id", "requester_id", "supervisor_id", "created_at", "status", "decided_at", "decided_by", "reason"},
    "application": {"id", "owner_id", "owner_display_name", "supervisor_id", "supervisor_display_name", "room_id", "title", "purpose", "attendees", "start_at", "end_at", "weeks", "status", "created_at", "decided_at", "decided_by", "decision_reason"},
    "room": {"id", "name", "location", "capacity"},
    "booking": {"id", "room_id", "owner_id", "title", "purpose", "attendees", "start_at", "end_at", "created_at", "cancelled_at", "cancelled_by_id", "cancel_reason"},
    "block": {"id", "room_id", "creator_id", "reason", "start_at", "end_at", "created_at", "revoked_at", "revoked_by_id", "revoke_reason"},
}
_AUDIT_ACTION_TYPES = {
    **{f"cancellation_request.{action}": "cancellation_request" for action in ("created", "approved", "rejected", "superseded")},
    **{f"application.{action}": "application" for action in ("created", "approved", "rejected", "withdrawn")},
    "room.created": "room", "room.updated": "room", "booking.created": "booking",
    "booking.cancelled_by_member": "booking", "booking.cancelled_by_supervisor": "booking", "booking.cancelled_by_admin": "booking",
    "block.created": "block", "block.revoked": "block",
}


def audit_event(row) -> dict:
    before = json.loads(row["before_json"]) if row["before_json"] is not None else None
    after = json.loads(row["after_json"])
    # Malformed stored facts fail the whole read; never omit an event or leak raw JSON.
    if (_AUDIT_ACTION_TYPES.get(row["action"]) != row["target_type"]
            or row["action"].endswith(".created") != (before is None)):
        raise ValueError("Inconsistent audit action or previous snapshot")
    expected = _SNAPSHOT_KEYS[row["target_type"]]
    for index, snapshot in enumerate((before, after)):
        if snapshot is None and index == 0:
            continue
        if not isinstance(snapshot, dict) or set(snapshot) != expected:
            raise ValueError("Invalid audit snapshot")
        if snapshot["id"] != row["target_id"]:
            raise ValueError("Inconsistent audit target")
        for key, value in snapshot.items():
            nullable = key in {"cancelled_at", "cancelled_by_id", "cancel_reason", "revoked_at", "revoked_by_id", "revoke_reason", "decided_at", "decided_by", "decision_reason", "reason"} and row["target_type"] == "cancellation_request" or key in {"cancelled_at", "cancelled_by_id", "cancel_reason", "revoked_at", "revoked_by_id", "revoke_reason", "decided_at", "decided_by", "decision_reason"}
            if value is None and nullable:
                continue
            kind = str if key in {"name", "location", "title", "purpose", "reason", "cancel_reason", "revoke_reason", "owner_display_name", "supervisor_display_name", "status", "decision_reason"} else int
            if type(value) is not kind:
                raise ValueError("Invalid audit snapshot field")
            if ((key == "id" or key.endswith("_id")) and not 1 <= value <= 2**63 - 1
                    or key in {"capacity", "attendees"} and not 1 <= value <= 1000):
                raise ValueError("Invalid audit positive domain value")
    return {
        "id": row["id"], "actor_id": row["actor_id"], "actor_display_name": row["actor_display_name"],
        "action": row["action"], "target_type": row["target_type"], "target_id": row["target_id"],
        "occurred_at": row["occurred_at"], "occurred_local": local_time(row["occurred_at"]),
        "before": before, "after": after, "reason": row["reason"],
    }


def room(row) -> dict:
    return {"id": row["id"], "name": row["name"], "location": row["location"],
            "capacity": row["capacity"]}


def schedule_item(row, now: int) -> dict:
    record = {"room_id": row["room_id"], "room_name": row["room_name"],
              "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
              "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
              "status": active_status(row["start_at"], row["end_at"], now)}
    if row["kind"] == "booking":
        record.update(title=row["title"], owner_display_name=row["owner_display_name"],
                      supervisor_display_name=row["supervisor_display_name"], supervisor_source=row["supervisor_source"] or "legacy")
    else:
        record.update(id=row["id"], reason=row["reason"])
    return {"kind": row["kind"], "record": record}


def list_result(items: list) -> dict:
    return {"items": items, "total": len(items)}


def booking_full(row, room_row, now: int) -> dict:
    return {
        "supervisor_id": row["supervisor_id"], "supervisor_display_name": row["supervisor_display_name"],
        "supervisor_source": row["supervisor_source"] or "legacy",
        "application_id": row["application_id"], "approved_at": row["approved_at"], "approved_by": row["approved_by"],
        "id": row["id"], "room": room(room_row), "title": row["title"], "purpose": row["purpose"],
        "attendees": row["attendees"], "owner_id": row["user_id"], "owner_display_name": row["owner_display_name"],
        "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
        "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
        "status": "cancelled" if row["cancelled_at"] is not None else active_status(row["start_at"], row["end_at"], now),
        "created_at": row["created_at"], "created_local": local_time(row["created_at"]),
        "cancelled_at": row["cancelled_at"],
        "cancelled_local": local_time(row["cancelled_at"]) if row["cancelled_at"] is not None else None,
        "cancelled_by_id": row["cancelled_by"], "cancelled_by_display_name": row["cancelled_by_display_name"],
        "cancel_reason": row["cancel_reason"],
    }


def booking_snapshot(row) -> dict:
    return {"id": row["id"], "room_id": row["room_id"], "owner_id": row["user_id"],
            "title": row["title"], "purpose": row["purpose"], "attendees": row["attendees"],
            "start_at": row["start_at"], "end_at": row["end_at"], "created_at": row["created_at"],
            "cancelled_at": row["cancelled_at"], "cancelled_by_id": row["cancelled_by"],
            "cancel_reason": row["cancel_reason"]}


def block_full(row, room_row, now: int) -> dict:
    return {
        "id": row["id"], "room": room(room_row), "creator_id": row["user_id"],
        "creator_display_name": row["owner_display_name"], "reason": row["reason"],
        "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
        "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
        "status": "revoked" if row["cancelled_at"] is not None else active_status(row["start_at"], row["end_at"], now),
        "created_at": row["created_at"], "created_local": local_time(row["created_at"]),
        "revoked_at": row["cancelled_at"],
        "revoked_local": local_time(row["cancelled_at"]) if row["cancelled_at"] is not None else None,
        "revoked_by_id": row["cancelled_by"], "revoked_by_display_name": row["cancelled_by_display_name"],
        "revoke_reason": row["cancel_reason"],
    }


def block_snapshot(row) -> dict:
    return {"id": row["id"], "room_id": row["room_id"], "creator_id": row["user_id"],
            "reason": row["reason"], "start_at": row["start_at"], "end_at": row["end_at"],
            "created_at": row["created_at"], "revoked_at": row["cancelled_at"],
            "revoked_by_id": row["cancelled_by"], "revoke_reason": row["cancel_reason"]}


def conflict(row, now: int, *, admin: bool) -> dict:
    result = {"type": row["kind"], "room_id": row["room_id"],
              "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
              "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
              "status": active_status(row["start_at"], row["end_at"], now)}
    if admin:
        result.update(id=row["id"], attendees=row["attendees"], reason=row["reason"])
    return result


def application_snapshot(row):
    return {key: row[key] for key in _SNAPSHOT_KEYS["application"]}


def application_full(row, now):
    return dict(application_snapshot(row), room=room({"id":row["room_id"], "name":row["room_name"], "location":row["room_location"], "capacity":row["room_capacity"]}),
                start_local=local_time(row["start_at"]), end_local=local_time(row["end_at"]),
                expired=row["status"] == "awaiting_approval" and row["start_at"] <= now,
                reservation_id=row["reservation_id"])


def cancellation_snapshot(row):
    return {key: row[key] for key in _SNAPSHOT_KEYS["cancellation_request"]}


def cancellation_full(row, now):
    return dict(cancellation_snapshot(row), title=row["title"], owner_display_name=row["owner_display_name"],
                supervisor_display_name=row["supervisor_display_name"], room_name=row["room_name"],
                start_at=row["start_at"], start_local=local_time(row["start_at"]),
                end_at=row["end_at"], end_local=local_time(row["end_at"]),
                expired=row["status"] == "awaiting_approval" and now >= row["start_at"])

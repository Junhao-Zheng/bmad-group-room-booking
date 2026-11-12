"""Explicit public allowlists; storage rows are never serialized wholesale."""

from .domain import active_status, local_time


def room(row) -> dict:
    return {"id": row["id"], "name": row["name"], "location": row["location"],
            "capacity": row["capacity"]}


def schedule_item(row, now: int) -> dict:
    record = {"room_id": row["room_id"], "room_name": row["room_name"],
              "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
              "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
              "status": active_status(row["start_at"], row["end_at"], now)}
    if row["kind"] == "booking":
        record.update(title=row["title"], owner_display_name=row["owner_display_name"])
    else:
        record.update(id=row["id"], reason=row["reason"])
    return {"kind": row["kind"], "record": record}


def list_result(items: list) -> dict:
    return {"items": items, "total": len(items)}


def booking_full(row, room_row, now: int) -> dict:
    return {
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


def conflict(row, now: int, *, admin: bool) -> dict:
    result = {"type": row["kind"], "room_id": row["room_id"],
              "start_at": row["start_at"], "start_local": local_time(row["start_at"]),
              "end_at": row["end_at"], "end_local": local_time(row["end_at"]),
              "status": active_status(row["start_at"], row["end_at"], now)}
    if admin:
        result.update(id=row["id"], attendees=row["attendees"], reason=row["reason"])
    return result

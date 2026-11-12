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

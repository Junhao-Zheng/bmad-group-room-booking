"""Authenticated read services shared by HTML and JSON adapters."""

from flask import current_app

from . import auth, db, dto
from .domain import DomainError, auth_required, beijing_day, booking_interval, query_attendees, resource_id


def _require_actor(conn, actor: auth.Actor, now: int) -> None:
    # A stale/forged Actor alone cannot authorize a service call.
    if not isinstance(actor, auth.Actor):
        raise auth_required()
    session = auth.read_session(conn, actor.session_token_hash, now)
    if session is None or session["user_id"] is None or session["user_id"] != actor.id:
        raise auth_required()


def list_rooms(actor: auth.Actor) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        _require_actor(conn, actor, now)
        rows = conn.execute("SELECT id,name,location,capacity FROM rooms ORDER BY name,location,id").fetchall()
        return dto.list_result([dto.room(row) for row in rows])


def availability(actor: auth.Actor, start, end, attendees) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        _require_actor(conn, actor, now)
        start_at, end_at = booking_interval(start, end, now)
        count = query_attendees(attendees)
        if count > 1000:
            return dto.list_result([])
        rows = conn.execute(
            "SELECT room.id,room.name,room.location,room.capacity FROM rooms room "
            "WHERE room.capacity>=? AND NOT EXISTS ("
            "SELECT 1 FROM occupancy_slots s JOIN reservations r ON r.id=s.reservation_id "
            "AND r.room_id=s.room_id WHERE s.room_id=room.id AND r.cancelled_at IS NULL "
            "AND s.slot_start>=? AND s.slot_start<?) ORDER BY room.name,room.location,room.id",
            (count, start_at, end_at),
        ).fetchall()
        return dto.list_result([dto.room(row) for row in rows])


def schedule(actor: auth.Actor, room_id, date) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        _require_actor(conn, actor, now)
        normalized_id = resource_id(room_id)
        day_start, day_end = beijing_day(date)
        if conn.execute("SELECT id FROM rooms WHERE id=?", (normalized_id,)).fetchone() is None:
            raise DomainError("NOT_FOUND", "会议室不存在，请重新选择。")
        rows = conn.execute(
            "SELECT r.id,r.kind,r.room_id,room.name AS room_name,r.title,"
            "u.display_name AS owner_display_name,r.reason,r.start_at,r.end_at "
            "FROM reservations r JOIN rooms room ON room.id=r.room_id JOIN users u ON u.id=r.user_id "
            "WHERE r.room_id=? AND r.cancelled_at IS NULL AND r.start_at<? AND ?<r.end_at "
            "ORDER BY r.start_at,r.id", (normalized_id, day_end, day_start),
        ).fetchall()
        return dto.list_result([dto.schedule_item(row, now) for row in rows])

"""Authenticated services; business writes and audit share one transaction."""

import json
import sqlite3

from flask import current_app

from . import auth, db, dto
from .domain import DomainError, auth_required, beijing_day, booking_interval, query_attendees, resource_id
from .domain import normalize_booking_payload, validate_booking_window


def _require_actor(conn, actor: auth.Actor, now: int) -> auth.Actor:
    # A stale/forged Actor alone cannot authorize a service call.
    if not isinstance(actor, auth.Actor):
        raise auth_required()
    session = auth.read_session(conn, actor.session_token_hash, now)
    if session is None or session["user_id"] is None or session["user_id"] != actor.id:
        raise auth_required()
    return auth.Actor(session["user_id"], session["display_name"], session["role"], session["token_hash"])


def create_booking(actor: auth.Actor, payload: dict) -> dict:
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = _require_actor(conn, actor, now)
        values, intent_key = normalize_booking_payload(payload)
        previous = conn.execute(
            "SELECT r.*,u.display_name AS owner_display_name,c.display_name AS cancelled_by_display_name "
            "FROM reservations r JOIN users u ON u.id=r.user_id LEFT JOIN users c ON c.id=r.cancelled_by "
            "WHERE r.kind='booking' AND r.user_id=? AND r.intent_key=?", (actor.id, intent_key),
        ).fetchone()
        if previous is not None:
            if json.loads(previous["request_payload"]) != values:
                raise DomainError("IDEMPOTENCY_MISMATCH", "此提交标识已用于不同预约内容，请核对原预约或开始新预约。")
            room = conn.execute("SELECT id,name,location,capacity FROM rooms WHERE id=?", (previous["room_id"],)).fetchone()
            # Rebuild current facts, before any new-booking time/capacity/occupancy rules.
            # Exiting the transaction commits even this read-only replay; no audit is emitted.
            return {"booking": dto.booking_full(previous, room, now), "replayed": True}
        room = conn.execute("SELECT id,name,location,capacity FROM rooms WHERE id=?", (values["room_id"],)).fetchone()
        if room is None:
            raise DomainError("NOT_FOUND", "会议室不存在，请重新选择。")
        validate_booking_window(values["start_at"], values["end_at"], now)
        if values["attendees"] > room["capacity"]:
            raise DomainError("CAPACITY_CONFLICT", "预计人数超过会议室当前容量，请调整人数或重新选择会议室。")
        conflicts = conn.execute(
            "SELECT r.id,r.kind,r.room_id,r.start_at,r.end_at,r.attendees,r.reason FROM reservations r "
            "WHERE r.room_id=? AND r.cancelled_at IS NULL AND r.start_at<? AND ?<r.end_at ORDER BY r.start_at,r.id",
            (values["room_id"], values["end_at"], values["start_at"]),
        ).fetchall()
        if conflicts:
            raise DomainError("OCCUPANCY_CONFLICT", "该会议室的时段已被占用，请重新查询可用会议室。",
                              conflicts=[dto.conflict(row, now, admin=actor.role == "admin") for row in conflicts])
        canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        try:
            inserted = conn.execute(
                "INSERT INTO reservations(kind,room_id,user_id,title,purpose,attendees,start_at,end_at,"
                "intent_key,request_payload,created_at) VALUES('booking',?,?,?,?,?,?,?,?,?,?)",
                (values["room_id"], actor.id, values["title"], values["purpose"], values["attendees"],
                 values["start_at"], values["end_at"], intent_key, canonical, now),
            )
        except sqlite3.IntegrityError as error:
            if (error.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and str(error) ==
                    "UNIQUE constraint failed: reservations.user_id, reservations.intent_key"):
                raise DomainError("IDEMPOTENCY_MISMATCH", "此提交标识已使用，请先核对已提交的安排。") from None
            raise
        booking_id = inserted.lastrowid
        try:
            conn.executemany("INSERT INTO occupancy_slots(room_id,slot_start,reservation_id) VALUES(?,?,?)",
                             [(values["room_id"], slot, booking_id)
                              for slot in range(values["start_at"], values["end_at"], 1800)])
        except sqlite3.IntegrityError as error:
            if (error.sqlite_errorcode in (sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY, sqlite3.SQLITE_CONSTRAINT_UNIQUE)
                    and str(error) == "UNIQUE constraint failed: occupancy_slots.room_id, occupancy_slots.slot_start"):
                raise DomainError("OCCUPANCY_CONFLICT", "该会议室的时段已被占用，请重新查询可用会议室。") from None
            raise
        row = conn.execute(
            "SELECT r.*,u.display_name AS owner_display_name,c.display_name AS cancelled_by_display_name "
            "FROM reservations r JOIN users u ON u.id=r.user_id LEFT JOIN users c ON c.id=r.cancelled_by WHERE r.id=?",
            (booking_id,),
        ).fetchone()
        current_app.config["AUDIT_WRITER"](conn, {
            "actor_id": actor.id, "actor_display_name": actor.display_name, "action": "booking.created",
            "target_type": "booking", "target_id": booking_id, "occurred_at": now,
            "before": None, "after": dto.booking_snapshot(row), "reason": None,
        })
        result = {"booking": dto.booking_full(row, room, now), "replayed": False}
    return result


def list_rooms(actor: auth.Actor) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        _require_actor(conn, actor, now)
        rows = conn.execute("SELECT id,name,location,capacity FROM rooms ORDER BY name,location,id").fetchall()
        return dto.list_result([dto.room(row) for row in rows])


_BOOKING_DETAIL_SELECT = (
    "SELECT r.*,u.display_name AS owner_display_name,c.display_name AS cancelled_by_display_name,"
    "room.name AS room_name,room.location AS room_location,room.capacity AS room_capacity "
    "FROM reservations r JOIN users u ON u.id=r.user_id "
    "LEFT JOIN users c ON c.id=r.cancelled_by JOIN rooms room ON room.id=r.room_id "
)


def _full_booking(row, now: int) -> dict:
    return dto.booking_full(row, {"id": row["room_id"], "name": row["room_name"],
                                 "location": row["room_location"], "capacity": row["room_capacity"]}, now)


def member_cancel_booking(actor: auth.Actor, booking_id) -> dict:
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = _require_actor(conn, actor, now)
        normalized_id = resource_id(booking_id, "booking_id")
        row = conn.execute(
            _BOOKING_DETAIL_SELECT + "WHERE r.kind='booking' AND r.id=? AND r.user_id=?",
            (normalized_id, actor.id),
        ).fetchone()
        if row is None:
            raise DomainError("NOT_FOUND", "预约不存在或无权访问。")
        # Ownership precedes idempotence, including for administrators using this entry point.
        if row["cancelled_at"] is not None:
            return _full_booking(row, now)
        if now >= row["start_at"]:
            raise DomainError("TRANSITION_CLOSED", "预约已开始或结束，不能通过本人取消入口取消。")
        before = dto.booking_snapshot(row)
        conn.execute("UPDATE reservations SET cancelled_at=?,cancelled_by=?,cancel_reason=NULL WHERE id=?",
                     (now, actor.id, normalized_id))
        conn.execute("DELETE FROM occupancy_slots WHERE reservation_id=?", (normalized_id,))
        row = conn.execute(_BOOKING_DETAIL_SELECT + "WHERE r.id=?", (normalized_id,)).fetchone()
        current_app.config["AUDIT_WRITER"](conn, {
            "actor_id": actor.id, "actor_display_name": actor.display_name,
            "action": "booking.cancelled_by_member", "target_type": "booking", "target_id": normalized_id,
            "occurred_at": now, "before": before, "after": dto.booking_snapshot(row), "reason": None,
        })
        result = _full_booking(row, now)
    return result


def my_bookings(actor: auth.Actor, status=None) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = _require_actor(conn, actor, now)
        conditions = {
            "pending": ("r.cancelled_at IS NULL AND r.start_at>?", (now,)),
            "in_progress": ("r.cancelled_at IS NULL AND r.start_at<=? AND r.end_at>?", (now, now)),
            "ended": ("r.cancelled_at IS NULL AND r.end_at<=?", (now,)),
            "cancelled": ("r.cancelled_at IS NOT NULL", ()),
        }
        if status is not None and (not isinstance(status, str) or status not in conditions):
            raise DomainError("INVALID_INPUT", "请检查预约状态。", {"status": "请选择待开始、进行中、已结束或已取消。"})
        query = _BOOKING_DETAIL_SELECT + "WHERE r.kind='booking' AND r.user_id=?"
        parameters = (actor.id,)
        if status is not None:
            clause, values = conditions[status]
            query += " AND " + clause
            parameters += values
        rows = conn.execute(query + " ORDER BY r.start_at DESC,r.id DESC", parameters).fetchall()
        return dto.list_result([_full_booking(row, now) for row in rows])


def booking_detail(actor: auth.Actor, booking_id) -> dict:
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = _require_actor(conn, actor, now)
        normalized_id = resource_id(booking_id, "booking_id")
        row = conn.execute(
            _BOOKING_DETAIL_SELECT + "WHERE r.kind='booking' AND r.id=? AND (r.user_id=? OR ?)",
            (normalized_id, actor.id, actor.role == "admin"),
        ).fetchone()
        if row is None:
            raise DomainError("NOT_FOUND", "预约不存在或无权查看。")
        return _full_booking(row, now)


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

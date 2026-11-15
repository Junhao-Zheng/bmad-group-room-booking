"""Admin-bound previews for atomic cancellation and maintenance blocks."""

import hashlib
import json
import re
import secrets

from flask import current_app

from . import cancellations, db, dto, services
from .domain import DomainError, local_time, normalize_block_payload, validate_block_window


def _affected(conn, values):
    rows = conn.execute(services._BOOKING_DETAIL_SELECT +
        "WHERE r.kind='booking' AND r.room_id=? AND r.cancelled_at IS NULL AND r.start_at<? AND ?<r.end_at "
        "ORDER BY r.start_at,r.id", (values["room_id"], values["end_at"], values["start_at"])).fetchall()
    facts = [dict(id=row["id"], title=row["title"], owner_display_name=row["owner_display_name"],
        start_at=row["start_at"], start_local=local_time(row["start_at"]),
        end_at=row["end_at"], end_local=local_time(row["end_at"])) for row in rows]
    return rows, facts


def _block_conflicts(conn, values, now):
    rows = conn.execute("SELECT id,kind,room_id,start_at,end_at,attendees,reason FROM reservations "
        "WHERE kind='block' AND room_id=? AND cancelled_at IS NULL AND start_at<? AND ?<end_at "
        "ORDER BY start_at,id", (values["room_id"], values["end_at"], values["start_at"])).fetchall()
    if rows:
        raise DomainError("OCCUPANCY_CONFLICT", "该时段已有停用，请调整时间。",
            conflicts=[dto.conflict(row, now, admin=True) for row in rows])


def _block_full(row, now):
    room = dict(id=row["room_id"], name=row["room_name"],
                location=row["room_location"], capacity=row["room_capacity"])
    return dto.block_full(row, room, now)


def preview(actor, payload):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services.require_admin(services._require_actor(conn, actor, now))
        if not isinstance(payload, dict) or set(payload) != {"room_id", "start", "end", "reason"}:
            raise DomainError("INVALID_INPUT", "请提交完整停用信息。")
        values = normalize_block_payload(payload)
        room = conn.execute("SELECT id,name,location,capacity FROM rooms WHERE id=?", (values["room_id"],)).fetchone()
        if room is None:
            raise DomainError("NOT_FOUND", "会议室不存在。")
        validate_block_window(values["start_at"], values["end_at"], now)
        _block_conflicts(conn, values, now)
        _, affected = _affected(conn, values)
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO maintenance_previews(token_hash,actor_id,room_id,start_at,end_at,reason,"
            "affected_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), actor.id, values["room_id"],
             values["start_at"], values["end_at"], values["reason"],
             json.dumps(affected, ensure_ascii=False, separators=(",", ":")), now, now + 600))
        return dict(preview_token=token, room=dto.room(room), start_at=values["start_at"],
            start_local=local_time(values["start_at"]), end_at=values["end_at"],
            end_local=local_time(values["end_at"]), reason=values["reason"],
            affected=affected, expires_at=now + 600)


def confirm(actor, payload):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services.require_admin(services._require_actor(conn, actor, now))
        if not isinstance(payload, dict) or set(payload) != {"preview_token", "confirmed"} or payload["confirmed"] is not True:
            raise DomainError("INVALID_INPUT", "请明确确认预览内容。")
        token = payload["preview_token"]
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,80}", token):
            raise DomainError("INVALID_INPUT", "预览凭据无效，请重新预览。")
        row = conn.execute("SELECT * FROM maintenance_previews WHERE token_hash=? AND actor_id=?",
            (hashlib.sha256(token.encode()).hexdigest(), actor.id)).fetchone()
        if row is None:
            raise DomainError("NOT_FOUND", "预览不存在或不属于当前管理员。")
        affected = json.loads(row["affected_json"])
        if row["block_id"] is not None:
            block = conn.execute(services._BOOKING_DETAIL_SELECT + "WHERE r.kind='block' AND r.id=?",
                (row["block_id"],)).fetchone()
            return dict(block=_block_full(block, now), affected=affected, replayed=True)
        if now > row["expires_at"]:
            raise DomainError("TRANSITION_CLOSED", "预览已过期，请重新预览。")
        values = dict(room_id=row["room_id"], start_at=row["start_at"], end_at=row["end_at"], reason=row["reason"])
        validate_block_window(values["start_at"], values["end_at"], now)
        _block_conflicts(conn, values, now)
        bookings, current = _affected(conn, values)
        if current != affected:
            raise DomainError("TRANSITION_CLOSED", "受影响预约已变化，请重新预览确认。")
        for booking in bookings:
            services._cancel_booking_in_transaction(conn, actor, booking, now, values["reason"], "booking.cancelled_by_admin")
            cancellations.supersede_pending(conn, actor, booking["id"], now)
        inserted = conn.execute("INSERT INTO reservations(kind,room_id,user_id,reason,start_at,end_at,created_at) "
            "VALUES('block',?,?,?,?,?,?)", (values["room_id"], actor.id, values["reason"],
            values["start_at"], values["end_at"], now))
        block_id = inserted.lastrowid
        conn.executemany("INSERT INTO occupancy_slots VALUES(?,?,?)",
            [(values["room_id"], slot, block_id) for slot in range(values["start_at"], values["end_at"], 1800)])
        block = conn.execute(services._BOOKING_DETAIL_SELECT + "WHERE r.id=?", (block_id,)).fetchone()
        current_app.config["AUDIT_WRITER"](conn, dict(actor_id=actor.id, actor_display_name=actor.display_name,
            action="block.created", target_type="block", target_id=block_id, occurred_at=now,
            before=None, after=dto.block_snapshot(block), reason=values["reason"]))
        conn.execute("UPDATE maintenance_previews SET block_id=?,confirmed_at=? WHERE id=?", (block_id, now, row["id"]))
        return dict(block=_block_full(block, now), affected=affected, replayed=False)

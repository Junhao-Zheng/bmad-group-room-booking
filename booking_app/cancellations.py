"""Student cancellation requests and supervisor decisions."""

from flask import current_app

from . import db, dto, services
from .domain import DomainError, normalized_text, resource_id


_SELECT = (
    "SELECT c.*,r.title,r.start_at,r.end_at,room.name AS room_name,"
    "u.display_name AS owner_display_name,t.display_name AS supervisor_display_name "
    "FROM cancellation_requests c JOIN reservations r ON r.id=c.booking_id "
    "JOIN rooms room ON room.id=r.room_id JOIN users u ON u.id=c.requester_id "
    "JOIN users t ON t.id=c.supervisor_id "
)


def _audit(conn, actor, action, before, row, now):
    current_app.config["AUDIT_WRITER"](conn, dict(
        actor_id=actor.id, actor_display_name=actor.display_name,
        action="cancellation_request." + action, target_type="cancellation_request",
        target_id=row["id"], occurred_at=now, before=before,
        after=dto.cancellation_snapshot(row), reason=row["reason"],
    ))


def _owner_supervisor(conn, actor, row):
    owner = conn.execute("SELECT role,supervisor_id FROM users WHERE id=?", (row["requester_id"],)).fetchone()
    return (actor.role == "teacher" and row["supervisor_id"] == actor.id
            and owner is not None and owner["role"] == "member" and owner["supervisor_id"] == actor.id)


def create_request(actor, booking_id):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn, actor, now)
        booking_id = resource_id(booking_id, "booking_id")
        if actor.role != "member":
            raise DomainError("FORBIDDEN", "仅学生可申请由本人导师确认取消。")
        booking = conn.execute(services._BOOKING_DETAIL_SELECT +
            "WHERE r.kind='booking' AND r.id=? AND r.user_id=?", (booking_id, actor.id)).fetchone()
        if booking is None:
            raise DomainError("NOT_FOUND", "预约不存在或无权访问。")
        pending = conn.execute(_SELECT + "WHERE c.booking_id=? AND c.status='awaiting_approval'", (booking_id,)).fetchone()
        if pending is not None:
            return {"cancellation_request": dto.cancellation_full(pending, now), "replayed": True}
        if booking["cancelled_at"] is not None or now >= booking["start_at"]:
            raise DomainError("TRANSITION_CLOSED", "预约已取消或已开始，不能申请取消。")
        supervisor = conn.execute("SELECT t.id FROM users s JOIN users t ON t.id=s.supervisor_id "
                                  "WHERE s.id=? AND s.role='member' AND t.role='teacher'", (actor.id,)).fetchone()
        if supervisor is None or booking["supervisor_id"] != supervisor["id"]:
            raise DomainError("FORBIDDEN", "当前导师归属与预约不一致，请联系管理员。")
        inserted = conn.execute("INSERT INTO cancellation_requests(booking_id,requester_id,supervisor_id,created_at,status) "
                                "VALUES(?,?,?,?,'awaiting_approval')", (booking_id,actor.id,supervisor["id"],now))
        row = conn.execute(_SELECT + "WHERE c.id=?", (inserted.lastrowid,)).fetchone()
        _audit(conn,actor,"created",None,row,now)
        return {"cancellation_request":dto.cancellation_full(row,now),"replayed":False}


def list_requests(actor):
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn, actor, now)
        rows = conn.execute(_SELECT + "WHERE ? OR c.requester_id=? OR (? AND c.supervisor_id=? AND EXISTS "
            "(SELECT 1 FROM users u WHERE u.id=c.requester_id AND u.role='member' AND u.supervisor_id=?)) "
            "ORDER BY c.created_at DESC,c.id DESC", (actor.role=="admin",actor.id,actor.role=="teacher",actor.id,actor.id)).fetchall()
        return dto.list_result([dto.cancellation_full(row,now) for row in rows])


def decide_request(actor, request_id, action, payload):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn, actor, now)
        row = conn.execute(_SELECT + "WHERE c.id=?", (resource_id(request_id,"cancellation_request_id"),)).fetchone()
        if row is None or not _owner_supervisor(conn,actor,row):
            raise DomainError("NOT_FOUND", "取消申请不存在或无权处理。")
        expected = {"reason"} if action == "reject" else set()
        if not isinstance(payload,dict) or set(payload) != expected:
            raise DomainError("INVALID_INPUT", "请仅提交此操作要求的字段。")
        reason = normalized_text(payload.get("reason"),"reason",500) if action == "reject" else None
        target_status = "approved" if action == "approve" else "rejected"
        if row["status"] == target_status:
            return dto.cancellation_full(row,now)
        if row["status"] != "awaiting_approval":
            raise DomainError("TRANSITION_CLOSED", "取消申请已处理，原决定保持不变。")
        booking = conn.execute(services._BOOKING_DETAIL_SELECT + "WHERE r.kind='booking' AND r.id=?",(row["booking_id"],)).fetchone()
        if booking["cancelled_at"] is not None or (action == "approve" and now >= booking["start_at"]):
            raise DomainError("TRANSITION_CLOSED", "预约已取消或已开始，不能确认取消。")
        before = dto.cancellation_snapshot(row)
        if action == "approve":
            services._cancel_booking_in_transaction(conn,actor,booking,now,None,"booking.cancelled_by_supervisor")
        conn.execute("UPDATE cancellation_requests SET status=?,decided_at=?,decided_by=?,reason=? WHERE id=?",
                     (target_status,now,actor.id,reason,row["id"]))
        row = conn.execute(_SELECT + "WHERE c.id=?",(row["id"],)).fetchone()
        _audit(conn,actor,target_status,before,row,now)
        return dto.cancellation_full(row,now)


def supersede_pending(conn, actor, booking_id, now):
    row = conn.execute(_SELECT + "WHERE c.booking_id=? AND c.status='awaiting_approval'",(booking_id,)).fetchone()
    if row is None:
        return
    before = dto.cancellation_snapshot(row)
    conn.execute("UPDATE cancellation_requests SET status='superseded',decided_at=?,decided_by=? WHERE id=?",(now,actor.id,row["id"]))
    row = conn.execute(_SELECT + "WHERE c.id=?",(row["id"],)).fetchone()
    _audit(conn,actor,"superseded",before,row,now)

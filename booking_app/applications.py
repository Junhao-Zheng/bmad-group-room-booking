"""Student applications. Every conversion, occupancy slot and audit shares one lock."""
import json
import secrets
from flask import current_app
from . import auth, db, dto, services
from .domain import DomainError, normalize_booking_payload, normalized_text, resource_id, validate_booking_window

_SELECT = ("SELECT a.*,room.name AS room_name,room.location AS room_location,room.capacity AS room_capacity,"
           "o.reservation_id FROM applications a JOIN rooms room ON room.id=a.room_id "
           "LEFT JOIN application_occurrences o ON o.application_id=a.id ")


def _visible(conn, actor, row):
    if row is None:
        raise DomainError("NOT_FOUND", "申请不存在或无权查看。")
    if actor.role == "admin" or row["owner_id"] == actor.id:
        return
    owner = conn.execute("SELECT supervisor_id FROM users WHERE id=?", (row["owner_id"],)).fetchone()
    if actor.role == "teacher" and row["supervisor_id"] == actor.id and owner[0] == actor.id:
        return
    raise DomainError("NOT_FOUND", "申请不存在或无权查看。")


def _audit(conn, actor, action, before, row, now, reason=None):
    current_app.config["AUDIT_WRITER"](conn, dict(actor_id=actor.id, actor_display_name=actor.display_name,
        action=f"application.{action}", target_type="application", target_id=row["id"], occurred_at=now,
        before=before, after=dto.application_snapshot(row), reason=reason))


def create_application(actor, payload):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn, actor, now)
        if actor.role != "member":
            raise DomainError("FORBIDDEN", "仅学生提交申请；导师和管理员可直接预约。")
        if not isinstance(payload, dict) or set(payload) - {"room_id","title","purpose","attendees","start","end","intent_key","weeks"}:
            raise DomainError("INVALID_INPUT", "申请不接受身份或归属字段。")
        if type(payload.get("weeks", 1)) is not int or payload.get("weeks", 1) != 1:
            raise DomainError("INVALID_INPUT", "当前仅支持单次申请。")
        values, intent = normalize_booking_payload(payload)
        canonical = dict(values, weeks=1)
        previous = conn.execute(_SELECT + "WHERE a.owner_id=? AND a.intent_key=?", (actor.id,intent)).fetchone()
        if previous is not None:
            if json.loads(previous["request_payload"]) != canonical:
                raise DomainError("IDEMPOTENCY_MISMATCH", "原提交标识已用于不同申请内容。")
            return {"application":dto.application_full(previous,now), "replayed":True}
        supervisor = conn.execute("SELECT t.id,t.display_name FROM users s JOIN users t ON t.id=s.supervisor_id "
                                  "WHERE s.id=? AND t.role='teacher'", (actor.id,)).fetchone()
        if supervisor is None:
            raise DomainError("FORBIDDEN", "请先由管理员绑定本人导师。")
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (values["room_id"],)).fetchone()
        if room is None:
            raise DomainError("NOT_FOUND", "会议室不存在。")
        validate_booking_window(values["start_at"],values["end_at"],now)
        if values["attendees"] > room["capacity"]:
            raise DomainError("CAPACITY_CONFLICT", "预计人数超过会议室当前容量。")
        inserted = conn.execute("INSERT INTO applications(owner_id,owner_display_name,supervisor_id,supervisor_display_name,"
            "room_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'awaiting_approval',?)", (actor.id,actor.display_name,supervisor["id"],supervisor["display_name"],
            values["room_id"],values["title"],values["purpose"],values["attendees"],values["start_at"],values["end_at"],intent,
            json.dumps(canonical,sort_keys=True,ensure_ascii=False,separators=(",",":")),now))
        row = conn.execute(_SELECT + "WHERE a.id=?", (inserted.lastrowid,)).fetchone()
        _audit(conn,actor,"created",None,row,now)
        return {"application":dto.application_full(row,now), "replayed":False}


def list_applications(actor):
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn,actor,now)
        rows = conn.execute(_SELECT + "WHERE ? OR a.owner_id=? OR (? AND a.supervisor_id=? AND EXISTS "
            "(SELECT 1 FROM users u WHERE u.id=a.owner_id AND u.supervisor_id=?)) ORDER BY a.created_at DESC,a.id DESC",
            (actor.role=="admin",actor.id,actor.role=="teacher",actor.id,actor.id)).fetchall()
        return dto.list_result([dto.application_full(row,now) for row in rows])


def application_detail(actor, application_id):
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn,actor,now)
        row = conn.execute(_SELECT + "WHERE a.id=?", (resource_id(application_id,"application_id"),)).fetchone()
        _visible(conn,actor,row)
        return dto.application_full(row,now)


def decide_application(actor, application_id, action, payload):
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn,actor,now)
        row = conn.execute(_SELECT + "WHERE a.id=?", (resource_id(application_id,"application_id"),)).fetchone()
        _visible(conn,actor,row)
        if action not in ("approve","reject","withdraw"):
            raise DomainError("NOT_FOUND", "操作不存在。")
        if action == "withdraw":
            authorized = actor.role == "member" and row["owner_id"] == actor.id
        else:
            owner = conn.execute("SELECT role,supervisor_id FROM users WHERE id=?", (row["owner_id"],)).fetchone()
            authorized = actor.role == "teacher" and row["supervisor_id"] == actor.id and owner["role"] == "member" and owner["supervisor_id"] == actor.id
        if not authorized:
            raise DomainError("FORBIDDEN", "仅本人导师可审批，学生仅可撤回本人的待审申请。")
        expected = {"reason"} if action == "reject" else set()
        if not isinstance(payload,dict) or set(payload) != expected:
            raise DomainError("INVALID_INPUT", "请仅提交此操作要求的字段。")
        reason = normalized_text(payload.get("reason"),"reason",500) if action == "reject" else None
        status = {"approve":"approved","reject":"rejected","withdraw":"withdrawn"}[action]
        if row["status"] == status:
            return dto.application_full(row,now)
        if row["status"] != "awaiting_approval":
            raise DomainError("TRANSITION_CLOSED", "申请已处理，原决定保持不变。")
        before = dto.application_snapshot(row)
        if action == "approve":
            validate_booking_window(row["start_at"],row["end_at"],now)
            if row["attendees"] > row["room_capacity"]:
                raise DomainError("CAPACITY_CONFLICT", "会议室当前容量不足，申请仍待审批。")
            conflicts = conn.execute("SELECT id,kind,room_id,start_at,end_at,attendees,reason FROM reservations "
                "WHERE room_id=? AND cancelled_at IS NULL AND start_at<? AND ?<end_at", (row["room_id"],row["end_at"],row["start_at"])).fetchall()
            if conflicts:
                raise DomainError("OCCUPANCY_CONFLICT", "时段已被占用，申请仍待审批。", conflicts=[dto.conflict(r,now,admin=False) for r in conflicts])
            values = {key:row[key] for key in ("room_id","title","purpose","attendees","start_at","end_at")}
            intent = secrets.token_hex(32)
            inserted = conn.execute("INSERT INTO reservations(kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                "VALUES('booking',?,?,?,?,?,?,?,?,?,?)", (row["room_id"],row["owner_id"],row["title"],row["purpose"],row["attendees"],row["start_at"],row["end_at"],intent,
                json.dumps(values,sort_keys=True,ensure_ascii=False,separators=(",",":")),now))
            booking_id = inserted.lastrowid
            conn.executemany("INSERT INTO occupancy_slots VALUES(?,?,?)", [(row["room_id"],slot,booking_id) for slot in range(row["start_at"],row["end_at"],1800)])
            conn.execute("INSERT INTO booking_supervisors VALUES(?,?,?,'application')", (booking_id,row["supervisor_id"],row["supervisor_display_name"]))
            conn.execute("INSERT INTO application_occurrences VALUES(?,1,?)", (row["id"],booking_id))
            booking = conn.execute("SELECT * FROM reservations WHERE id=?", (booking_id,)).fetchone()
            current_app.config["AUDIT_WRITER"](conn, dict(actor_id=actor.id,actor_display_name=actor.display_name,action="booking.created",
                target_type="booking",target_id=booking_id,occurred_at=now,before=None,after=dto.booking_snapshot(booking),reason=None))
        conn.execute("UPDATE applications SET status=?,decided_at=?,decided_by=?,decision_reason=? WHERE id=?", (status,now,actor.id,reason,row["id"]))
        row = conn.execute(_SELECT + "WHERE a.id=?", (row["id"],)).fetchone()
        _audit(conn,actor,status,before,row,now,reason)
        return dto.application_full(row,now)

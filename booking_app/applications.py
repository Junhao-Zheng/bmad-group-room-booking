"""Student applications. Every conversion, occupancy slot and audit shares one lock."""
import json
import secrets
from flask import current_app
from . import auth, db, dto, services
from .domain import DomainError, local_time, normalize_booking_payload, normalized_text, resource_id, validate_booking_window

_SELECT = ("SELECT a.*,room.name AS room_name,room.location AS room_location,room.capacity AS room_capacity,"
           "o.reservation_id FROM applications a JOIN rooms room ON room.id=a.room_id "
           "LEFT JOIN application_occurrences o ON o.application_id=a.id AND o.occurrence=1 ")


def _weeks(payload):
    weeks = payload.get("weeks", 1)
    if type(weeks) is not int or not 1 <= weeks <= 8:
        raise DomainError("INVALID_INPUT", "连续预约须为 1—8 周。", {"weeks": "请选择 1—8 周。"})
    return weeks


def _dates(row):
    result = []
    for index in range(row["weeks"]):
        start, end = row["start_at"] + index * 7 * 86400, row["end_at"] + index * 7 * 86400
        try:
            start_local, end_local = local_time(start), local_time(end)
        except (OverflowError, ValueError, OSError):
            raise DomainError("INVALID_INPUT", "周期日期超出可用范围。", {"weeks": "请缩短连续周数。"}) from None
        if start_local[:10] != end_local[:10]:
            raise DomainError("INVALID_INPUT", "每周起止时间须在同一北京时间日期。")
        result.append((index + 1, start, end, start_local, end_local))
    return result


def _full(conn, row, now):
    result = dto.application_full(row, now)
    if row["weeks"] > 1:
        booked = {r["occurrence"]: r for r in conn.execute(
            "SELECT o.occurrence,o.reservation_id,r.cancelled_at FROM application_occurrences o "
            "JOIN reservations r ON r.id=o.reservation_id WHERE o.application_id=?", (row["id"],))}
        result["occurrences"] = [dict(occurrence=index, start_at=start, end_at=end,
            start_local=start_local, end_local=end_local,
            reservation_id=booked[index]["reservation_id"] if index in booked else None,
            status=("cancelled" if booked[index]["cancelled_at"] is not None else
                    dto.active_status(start, end, now)) if index in booked else None)
            for index, start, end, start_local, end_local in _dates(row)]
    return result


def _approve(conn, actor, row, now):
    validate_booking_window(row["start_at"], row["end_at"], now)
    if row["attendees"] > row["room_capacity"]:
        raise DomainError("CAPACITY_CONFLICT", "会议室当前容量不足，整组仍待审批。")
    dates = _dates(row)
    conflicts = []
    for _, start, end, _, _ in dates:
        found = conn.execute("SELECT id,kind,room_id,start_at,end_at,attendees,reason FROM reservations "
            "WHERE room_id=? AND cancelled_at IS NULL AND start_at<? AND ?<end_at ORDER BY start_at,id",
            (row["room_id"], end, start)).fetchall()
        conflicts.extend(dto.conflict(item, now, admin=actor.role == "admin") for item in found)
    if conflicts:
        raise DomainError("OCCUPANCY_CONFLICT", "部分周次已被占用，整组尚未生效；请查看冲突日期。", conflicts=conflicts)
    for index, start, end, _, _ in dates:
        values = {key: row[key] for key in ("room_id", "title", "purpose", "attendees")}
        values.update(start_at=start, end_at=end)
        inserted = conn.execute("INSERT INTO reservations(kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
            "VALUES('booking',?,?,?,?,?,?,?,?,?,?)", (row["room_id"], row["owner_id"], row["title"], row["purpose"],
            row["attendees"], start, end, secrets.token_hex(32),
            json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":")), now))
        booking_id = inserted.lastrowid
        conn.executemany("INSERT INTO occupancy_slots VALUES(?,?,?)",
            [(row["room_id"], slot, booking_id) for slot in range(start, end, 1800)])
        source = "application" if actor.role == "teacher" and actor.id != row["owner_id"] else actor.role
        conn.execute("INSERT INTO booking_supervisors VALUES(?,?,?,?)", (booking_id,
            row["supervisor_id"] if source != "admin" else None,
            row["supervisor_display_name"] if source != "admin" else None, source))
        conn.execute("INSERT INTO application_occurrences VALUES(?,?,?)", (row["id"], index, booking_id))
        booking = conn.execute("SELECT * FROM reservations WHERE id=?", (booking_id,)).fetchone()
        current_app.config["AUDIT_WRITER"](conn, dict(actor_id=actor.id, actor_display_name=actor.display_name,
            action="booking.created", target_type="booking", target_id=booking_id,
            occurred_at=now, before=None, after=dto.booking_snapshot(booking), reason=None))


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
        if not isinstance(payload, dict) or set(payload) - {"room_id","title","purpose","attendees","start","end","intent_key","weeks"}:
            raise DomainError("INVALID_INPUT", "申请不接受身份或归属字段。")
        weeks = _weeks(payload)
        values, intent = normalize_booking_payload(payload)
        canonical = dict(values, weeks=weeks)
        previous = conn.execute(_SELECT + "WHERE a.owner_id=? AND a.intent_key=?", (actor.id,intent)).fetchone()
        if previous is not None:
            if json.loads(previous["request_payload"]) != canonical:
                raise DomainError("IDEMPOTENCY_MISMATCH", "原提交标识已用于不同申请内容。")
            return {"application":_full(conn, previous, now), "replayed":True}
        if conn.execute("SELECT 1 FROM reservations WHERE kind='booking' AND user_id=? AND intent_key=?",
                        (actor.id, intent)).fetchone():
            raise DomainError("IDEMPOTENCY_MISMATCH", "提交标识已用于单次预约，请核对原记录。")
        if actor.role == "member":
            supervisor = conn.execute("SELECT t.id,t.display_name FROM users s JOIN users t ON t.id=s.supervisor_id "
                                      "WHERE s.id=? AND t.role='teacher'", (actor.id,)).fetchone()
            if supervisor is None:
                raise DomainError("FORBIDDEN", "请先由管理员绑定本人导师。")
            supervisor_id, supervisor_name = supervisor["id"], supervisor["display_name"]
        else:
            supervisor_id, supervisor_name = actor.id, actor.display_name
        room = conn.execute("SELECT * FROM rooms WHERE id=?", (values["room_id"],)).fetchone()
        if room is None:
            raise DomainError("NOT_FOUND", "会议室不存在。")
        validate_booking_window(values["start_at"],values["end_at"],now)
        if values["attendees"] > room["capacity"]:
            raise DomainError("CAPACITY_CONFLICT", "预计人数超过会议室当前容量。")
        _dates(dict(values, weeks=weeks))
        inserted = conn.execute("INSERT INTO applications(owner_id,owner_display_name,supervisor_id,supervisor_display_name,"
            "room_id,title,purpose,attendees,start_at,end_at,weeks,intent_key,request_payload,status,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'awaiting_approval',?)", (actor.id,actor.display_name,supervisor_id,supervisor_name,
            values["room_id"],values["title"],values["purpose"],values["attendees"],values["start_at"],values["end_at"],weeks,intent,
            json.dumps(canonical,sort_keys=True,ensure_ascii=False,separators=(",",":")),now))
        row = conn.execute(_SELECT + "WHERE a.id=?", (inserted.lastrowid,)).fetchone()
        _audit(conn,actor,"created",None,row,now)
        if actor.role != "member":
            before = dto.application_snapshot(row)
            _approve(conn, actor, row, now)
            conn.execute("UPDATE applications SET status='approved',decided_at=?,decided_by=? WHERE id=?",
                         (now, actor.id, row["id"]))
            row = conn.execute(_SELECT + "WHERE a.id=?", (row["id"],)).fetchone()
            _audit(conn,actor,"approved",before,row,now)
        return {"application":_full(conn, row, now), "replayed":False}


def list_applications(actor):
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn,actor,now)
        rows = conn.execute(_SELECT + "WHERE ? OR a.owner_id=? OR (? AND a.supervisor_id=? AND EXISTS "
            "(SELECT 1 FROM users u WHERE u.id=a.owner_id AND u.supervisor_id=?)) ORDER BY a.created_at DESC,a.id DESC",
            (actor.role=="admin",actor.id,actor.role=="teacher",actor.id,actor.id)).fetchall()
        return dto.list_result([_full(conn,row,now) for row in rows])


def application_detail(actor, application_id):
    with db.read_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        actor = services._require_actor(conn,actor,now)
        row = conn.execute(_SELECT + "WHERE a.id=?", (resource_id(application_id,"application_id"),)).fetchone()
        _visible(conn,actor,row)
        return _full(conn,row,now)


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
            return _full(conn,row,now)
        if row["status"] != "awaiting_approval":
            raise DomainError("TRANSITION_CLOSED", "申请已处理，原决定保持不变。")
        before = dto.application_snapshot(row)
        if action == "approve":
            _approve(conn, actor, row, now)
        conn.execute("UPDATE applications SET status=?,decided_at=?,decided_by=?,decision_reason=? WHERE id=?", (status,now,actor.id,reason,row["id"]))
        row = conn.execute(_SELECT + "WHERE a.id=?", (row["id"],)).fetchone()
        _audit(conn,actor,status,before,row,now,reason)
        return _full(conn,row,now)

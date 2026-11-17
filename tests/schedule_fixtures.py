"""Explicitly synthetic fixture writes, never exposed through an application route."""

from datetime import datetime
import json
from zoneinfo import ZoneInfo

from booking_app import db
from booking_app.domain import full_half_hour_slots

TITLE = '<img src=x onerror="window.fixtureXss=1">合成活动'
OWNER = '<script>window.fixtureXss=2</script>演示乙'
PRIVATE_PURPOSE = "PRIVATE_PURPOSE_NEVER_SHARED"
PRIVATE_CANCEL_REASON = "PRIVATE_CANCELLATION_NEVER_SHARED"


def epoch(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp())


NOW = epoch("2026-11-12T10:00")


def insert_record(conn, record_id, room_id, start, end, *, kind="booking", cancelled=False,
                  title="合成演示活动", owner_id=2):
    start_at, end_at = epoch(start), epoch(end)
    booking = kind == "booking"
    payload = json.dumps({"room_id": room_id, "title": title, "purpose": PRIVATE_PURPOSE,
                          "attendees": 5, "start_at": start_at, "end_at": end_at},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":")) if booking else None
    conn.execute(
        "INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,reason,start_at,end_at,"
        "intent_key,request_payload,created_at,cancelled_at,cancelled_by,cancel_reason) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (record_id, kind, room_id, owner_id if booking else 3, title if booking else None,
         PRIVATE_PURPOSE if booking else None, 5 if booking else None,
         "合成维护 <检查设备>" if not booking else None, start_at, end_at,
         f"synthetic_key_{record_id:08d}" if booking else None, payload,
         NOW - 86400 * 5, NOW - 86400 * 4 if cancelled else None, 3 if cancelled else None,
         PRIVATE_CANCEL_REASON if cancelled else None),
    )
    if not cancelled:
        conn.executemany("INSERT INTO occupancy_slots(room_id,slot_start,reservation_id) VALUES (?,?,?)",
                         [(room_id, slot, record_id) for slot in range(start_at, end_at, 1800)])


def seed_schedule_fixture(database):
    with db.write_transaction(database) as conn:
        conn.execute("UPDATE users SET display_name=? WHERE id=2", (OWNER,))
        conn.executemany("INSERT INTO rooms(id,name,location,capacity,created_at,updated_at) VALUES (?,?,?,?,?,?)", [
            (30, '合成 C <讨论室>', '演示楼 303', 30, NOW, NOW),
            (20, '合成 A', '演示楼 202', 20, NOW, NOW),
            (10, '合成 A', '演示楼 101', 10, NOW, NOW),
        ])
        insert_record(conn, 101, 10, "2026-11-11T23:00", "2026-11-12T01:00", kind="block")
        insert_record(conn, 103, 10, "2026-11-12T09:00", "2026-11-12T10:00", title="已结束合成活动")
        insert_record(conn, 105, 10, "2026-11-12T10:00", "2026-11-12T11:00", title=TITLE)
        insert_record(conn, 104, 10, "2026-11-12T10:00", "2026-11-12T11:00", cancelled=True)
        insert_record(conn, 107, 10, "2026-11-12T11:00", "2026-11-12T11:30", title="待开始合成活动")
        insert_record(conn, 108, 10, "2026-11-12T23:00", "2026-11-13T00:00", kind="block")
        insert_record(conn, 109, 10, "2026-11-13T00:00", "2026-11-13T01:00", kind="block")
        insert_record(conn, 110, 10, "2026-11-12T12:00", "2026-11-12T13:00", kind="block", cancelled=True)
        insert_record(conn, 111, 20, "2026-11-12T10:00", "2026-11-12T11:00", title="其他会议室同起点")


def assert_slot_integrity(test, database):
    conn = db.connect(database)
    try:
        test.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        for row in conn.execute("SELECT id,room_id,start_at,end_at,cancelled_at FROM reservations"):
            expected = [] if row["cancelled_at"] is not None else list(full_half_hour_slots(row["start_at"], row["end_at"]))
            actual = conn.execute("SELECT room_id,slot_start FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start", (row["id"],)).fetchall()
            test.assertEqual([(slot["room_id"], slot["slot_start"]) for slot in actual], [(row["room_id"], slot) for slot in expected])
    finally:
        conn.close()

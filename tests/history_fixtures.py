"""Independent synthetic history, including historical cancellations; no mutation API."""
import json
from booking_app import db
from tests.schedule_fixtures import NOW, epoch

TITLE = '<img src=x onerror="window.historyXss=1">' + '长' * 39
PURPOSE = '<script>window.historyXss=2</script>' + '用途无空格文本' * 60 + '长' * 44
CANCEL_REASON = '<svg onload="window.historyXss=3">合成管理员取消原因'
FULL_KEYS = {'id', 'room', 'title', 'purpose', 'attendees', 'owner_id', 'owner_display_name',
             'start_at', 'start_local', 'end_at', 'end_local', 'status', 'created_at', 'created_local',
             'cancelled_at', 'cancelled_local', 'cancelled_by_id', 'cancelled_by_display_name', 'cancel_reason'}

class FixedClock:
    def __init__(self): self.now, self.calls = NOW, 0
    def now_epoch(self):
        self.calls += 1
        return self.now


def seed_history_fixture(database):
    with db.write_transaction(database) as conn:
        conn.executemany('INSERT INTO rooms VALUES(?,?,?,?,?,?)', [
            (1, '合成历史甲 <会议室>', '合成位置' * 25, 10, NOW, NOW),
            (2, '合成历史乙', '演示楼 202', 20, NOW, NOW),
            (3, '合成历史丙', '演示楼 303', 30, NOW, NOW),
        ])
        for record_id, owner_id, room_id, start, end, cancelled_by in [
            (101, 1, 1, '09:00', '10:00', None), (102, 1, 1, '10:00', '11:00', None),
            (103, 1, 1, '12:00', '13:00', None), (104, 1, 2, '12:00', '13:00', None),
            (105, 1, 1, '14:00', '15:00', 3), (106, 1, 1, '15:00', '16:00', 1),
            (201, 2, 2, '10:00', '11:00', None), (301, 3, 3, '10:00', '11:00', None),
        ]:
            start_at, end_at = epoch('2026-11-12T' + start), epoch('2026-11-12T' + end)
            title = TITLE if record_id == 104 else f'合成历史活动 {record_id}'
            purpose = PURPOSE if record_id == 104 else f'本人私密用途 {record_id}'
            values = dict(room_id=room_id, title=title, purpose=purpose, attendees=5, start_at=start_at, end_at=end_at)
            conn.execute('INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,'
                         'intent_key,request_payload,created_at,cancelled_at,cancelled_by,cancel_reason) '
                         "VALUES(?,'booking',?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (record_id, room_id, owner_id, title, purpose, 5, start_at, end_at,
                          f'history-fixture-{record_id:04d}', json.dumps(values, ensure_ascii=False, sort_keys=True),
                          NOW-86400, NOW-3600 if cancelled_by else None, cancelled_by,
                          CANCEL_REASON if cancelled_by == 3 else None))
            if not cancelled_by:
                conn.executemany('INSERT INTO occupancy_slots VALUES(?,?,?)',
                                 [(room_id, slot, record_id) for slot in range(start_at, end_at, 1800)])
        conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,reason,start_at,end_at,created_at) "
                     "VALUES(401,'block',3,3,'合成停用',?,?,?)", (NOW+3600, NOW+5400, NOW-86400))
        conn.execute('INSERT INTO occupancy_slots VALUES(3,?,401)', (NOW+3600,))

"""Version 6 bookings and pending applications survive minute-precision migration."""
import json
from pathlib import Path
import tempfile
import unittest

from booking_app import db
from scripts.migrate_db import migrate_database
from tests.schedule_fixtures import epoch


class MinuteMigrationTests(unittest.TestCase):
    def test_v6_data_and_backup_survive_v7_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            source, backup = Path(directory) / "source.db", Path(directory) / "backup.db"
            conn = db.connect(source)
            try:
                conn.executescript(Path(db.__file__).with_name("schema_v6.sql").read_text() + "\nPRAGMA user_version=6;")
                start = epoch("2026-11-18T15:00")
                conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'teacher','导师','hash','teacher',?)", (start,))
                conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at,supervisor_id) VALUES(2,'student','学生','hash','member',?,1)", (start,))
                conn.execute("INSERT INTO rooms VALUES(1,'讨论室','407',10,?,?)", (start,start))
                conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) VALUES(1,'booking',1,1,'组会','讨论',3,?,?,?, ?,?)",
                             (start,start+3600,'old-minute-key-01',json.dumps({'title':'组会'}),start))
                conn.executemany("INSERT INTO occupancy_slots VALUES(1,?,1)", [(start,), (start+1800,)])
                conn.execute("INSERT INTO applications(id,owner_id,owner_display_name,supervisor_id,supervisor_display_name,room_id,title,purpose,attendees,start_at,end_at,weeks,intent_key,request_payload,status,created_at) VALUES(1,2,'学生',1,'导师',1,'申请','讨论',3,?,?,1,?,?,'awaiting_approval',?)",
                             (start+7200,start+10800,'old-app-key-0001',json.dumps({'title':'申请'}),start))
            finally:
                conn.close()
            migrate_database(source, backup)
            with db.connect(source) as upgraded, db.connect(backup) as saved:
                self.assertEqual(saved.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertEqual(upgraded.execute("PRAGMA user_version").fetchone()[0], 7)
                self.assertEqual(upgraded.execute("SELECT count(*) FROM occupancy_slots").fetchone()[0], 2)
                self.assertEqual(upgraded.execute("SELECT title FROM reservations WHERE id=1").fetchone()[0], '组会')
                self.assertEqual(upgraded.execute("SELECT status FROM applications WHERE id=1").fetchone()[0], 'awaiting_approval')
                upgraded.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) VALUES(2,'booking',1,1,'精确分钟','讨论',3,?,?,?, ?,?)",
                                 (start+60,start+1860,'new-minute-key-01',json.dumps({'title':'精确分钟'}),start))
                self.assertEqual(upgraded.execute("PRAGMA foreign_key_check").fetchall(), [])

"""Story 1.2: consistent authenticated queries, half-open dates, and exact privacy."""

from contextlib import contextmanager
from dataclasses import replace
import re
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.domain import DomainError, active_status, beijing_day, resource_id
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.seed_demo_rooms import seed_rooms
from tests.schedule_fixtures import (NOW, OWNER, TITLE, PRIVATE_PURPOSE, PRIVATE_CANCEL_REASON,
                                     assert_slot_integrity, epoch, seed_schedule_fixture)

ORIGIN = "http://127.0.0.1:8000"
PASSWORD = "Synthetic-query-only-passphrase"
ROOM_KEYS = {"id", "name", "location", "capacity"}
COMMON_KEYS = {"room_id", "room_name", "start_at", "start_local", "end_at", "end_local", "status"}
BOOKING_KEYS = COMMON_KEYS | {"title", "owner_display_name", "supervisor_display_name", "supervisor_source"}
BLOCK_KEYS = COMMON_KEYS | {"id", "reason"}


class FixedClock:
    def __init__(self):
        self.now = NOW
        self.calls = 0

    def now_epoch(self):
        self.calls += 1
        return self.now


class RoomScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / "seed.sqlite3"
        users = [{"username": username, "display_name": display, "role": role, "password": PASSWORD}
                 for username, display, role in DEMO_IDENTITIES]
        seed_users(cls.fixture_db, users, FixedClock())
        seed_schedule_fixture(cls.fixture_db)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "query.sqlite3"
        source, destination = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(destination)
        source.close()
        destination.close()
        self.clock = FixedClock()
        self.app = create_app({"TESTING": True, "DATABASE": str(self.database), "CLOCK": self.clock})
        self.client = self.app.test_client()
        self.login()
        self.addCleanup(assert_slot_integrity, self, self.database)

    def get(self, path, client=None, **kwargs):
        return (client or self.client).get(path, base_url=ORIGIN, **kwargs)

    def login(self, username="demo_member_a", client=None):
        client = client or self.client
        page = self.get("/login", client)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = client.post("/api/login", base_url=ORIGIN, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                               json={"username": username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        return response.json["data"]

    def schedule(self, room_id="10", date="2026-11-12", client=None):
        return self.get("/api/schedule", client, query_string={"room_id": room_id, "date": date})

    def actor(self):
        token = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        return auth.actor_for_token(token)

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json), {"ok", "error"})
        self.assertIs(type(response.json["ok"]), bool)
        self.assertFalse(response.json["ok"])
        self.assertEqual(set(response.json["error"]), {"code", "message", "fields", "conflicts"})
        self.assertEqual(response.json["error"]["code"], code)
        self.assertNotIn("Set-Cookie", response.headers)

    def assert_list_envelope(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json), {"ok", "data"})
        self.assertIs(type(response.json["ok"]), bool)
        self.assertIs(response.json["ok"], True)
        self.assertIs(type(response.json["data"]["items"]), list)
        self.assertIs(type(response.json["data"]["total"]), int)
        self.assertEqual(response.json["data"]["total"], len(response.json["data"]["items"]))

    def test_room_exact_contract_order_and_page_share_service(self):
        result = self.get("/api/rooms")
        self.assert_list_envelope(result)
        self.assertEqual(set(result.json), {"ok", "data"})
        self.assertEqual(set(result.json["data"]), {"items", "total"})
        self.assertEqual(result.json["data"]["total"], 3)
        self.assertEqual([row["id"] for row in result.json["data"]["items"]], [10, 20, 30])
        for room in result.json["data"]["items"]:
            self.assertEqual(set(room), ROOM_KEYS)
            for key, value in room.items():
                if key == "supervisor_display_name":
                    self.assertIsNone(value)  # 历史无绑定，不猜测导师
                    continue
                self.assertIs(type(value), int if key in {"id", "capacity"} else str)
        with self.app.app_context():
            self.assertEqual(services.list_rooms(self.actor()), result.json["data"])
        with patch("booking_app.web.services.list_rooms", wraps=services.list_rooms) as query:
            page = self.get("/")
            query.assert_called_once()
        self.assertIn('for="room_id"', page.text)
        self.assertIn('for="date"', page.text)
        self.assertIn('id="auth-feedback"', page.text)
        self.assertIn("查询日程需要启用 JavaScript", page.text)
        self.assertIn('type="submit" disabled>查看日程', page.text)
        self.assertIn("&lt;讨论室&gt;", page.text)
        self.assertNotIn("合成 C <讨论室>", page.text)
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    def test_empty_catalog_and_empty_schedule_are_successful(self):
        for response in [self.schedule("30"), self.schedule(date="2026-11-14")]:
            self.assert_list_envelope(response)
        self.assertEqual(self.schedule("30").json["data"], {"items": [], "total": 0})
        self.assertEqual(self.schedule(date="2026-11-14").json["data"], {"items": [], "total": 0})
        with db.write_transaction(self.database) as conn:
            conn.execute("DELETE FROM occupancy_slots")
            conn.execute("DELETE FROM reservations")
            conn.execute("DELETE FROM rooms")
        self.assert_list_envelope(self.get("/api/rooms"))
        self.assertEqual(self.get("/api/rooms").json["data"], {"items": [], "total": 0})
        self.assertIn("暂无会议室", self.get("/").text)

    def test_schedule_exact_contract_current_status_and_private_fields_absent(self):
        result = self.schedule()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.json["data"]), {"items", "total"})
        data = result.json["data"]
        self.assertIs(type(result.json["ok"]), bool)
        self.assertIs(result.json["ok"], True)
        self.assertIs(type(data["total"]), int)
        self.assertIs(type(data["items"]), list)
        self.assertEqual(data["total"], 5)
        self.assertEqual([item["record"]["status"] for item in data["items"]],
                         ["ended", "ended", "in_progress", "pending", "pending"])
        for item in data["items"]:
            self.assertEqual(set(item), {"kind", "record"})
            self.assertEqual(set(item["record"]), BOOKING_KEYS if item["kind"] == "booking" else BLOCK_KEYS)
            self.assertIs(type(item["kind"]), str)
            for key, value in item["record"].items():
                if key == "supervisor_display_name":
                    self.assertIsNone(value)  # 历史无绑定，不猜测导师
                    continue
                self.assertIs(type(value), int if key in {"id", "room_id", "start_at", "end_at"} else str)
            self.assertEqual(item["record"]["room_id"], 10)
            self.assertEqual(item["record"]["room_name"], "合成 A")
            if item["kind"] == "block":
                self.assertEqual(item["record"]["reason"], "合成维护 <检查设备>")
            self.assertRegex(item["record"]["start_local"], r"^2026-11-[0-9]{2}T[0-9]{2}:[0-9]{2}:00\+08:00$")
        self.assertEqual(data["items"][2]["record"]["title"], TITLE)
        self.assertEqual(data["items"][2]["record"]["owner_display_name"], OWNER)
        booking = data["items"][2]["record"]
        self.assertEqual((booking["start_at"], booking["end_at"]), (1794448800, 1794452400))
        self.assertEqual((booking["start_local"], booking["end_local"]),
                         ("2026-11-12T10:00:00+08:00", "2026-11-12T11:00:00+08:00"))
        for private in [PRIVATE_PURPOSE, PRIVATE_CANCEL_REASON, '"attendees"', '"user_id"', '"owner_id"', '"purpose"', '"username"', '"cancel_reason"', '"request_payload"', '"intent_key"']:
            self.assertNotIn(private, result.text)
        with self.app.app_context():
            self.assertEqual(services.schedule(self.actor(), "10", "2026-11-12"), data)

    def test_half_open_midnight_cross_day_and_historical_blocks(self):
        previous = self.schedule(date="2026-11-11").json["data"]["items"]
        today = self.schedule().json["data"]["items"]
        following = self.schedule(date="2026-11-13").json["data"]["items"]
        self.assertEqual([i["record"]["id"] for i in previous], [101])
        block = previous[0]["record"]
        self.assertEqual((block["start_at"], block["end_at"]), (1794409200, 1794416400))
        self.assertEqual((block["start_local"], block["end_local"]),
                         ("2026-11-11T23:00:00+08:00", "2026-11-12T01:00:00+08:00"))
        self.assertEqual([i["record"]["id"] for i in today if i["kind"] == "block"], [101, 108])
        self.assertEqual([i["record"]["id"] for i in following], [109])
        self.clock.now = epoch("2026-12-01T12:00")
        self.login()  # Fresh absolute session at the later clock.
        historical = self.schedule(date="2026-11-11").json["data"]["items"]
        self.assertEqual(historical[0]["record"]["id"], 101)
        self.assertEqual(historical[0]["record"]["status"], "ended")

    def test_stable_sort_with_same_start_cancellation_and_other_room(self):
        # Two active same-room/same-start records would violate the slot invariant.
        # Check reachable equal-start rows (cancelled/other room), and the SQL tie key.
        statements = []
        original = db.read_transaction
        @contextmanager
        def traced():
            with original() as conn:
                conn.set_trace_callback(statements.append)
                yield conn
        with patch("booking_app.services.db.read_transaction", traced):
            items = self.schedule().json["data"]["items"]
        starts = [item["record"]["start_at"] for item in items]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(sum(t == NOW for t in starts), 1)
        self.assertNotIn("其他会议室同起点", str(items))
        self.assertTrue(any("ORDER BY r.start_at,r.id" in sql for sql in statements))
        self.assertEqual(self.schedule("20").json["data"]["total"], 1)

    def test_ids_reject_noncanonical_out_of_range_and_huge_values(self):
        for value in ["", "0", "-1", "+1", "01", "1.0", "1e0", " 10", "10 ", "１０", "١٠", str(2**63), "9" * 10000]:
            with self.subTest(value=value[:30]):
                self.assert_error(self.schedule(value), 400, "INVALID_INPUT")
        for value in ["999", str(2**63 - 1)]:
            self.assert_error(self.schedule(value), 404, "NOT_FOUND")
        self.assert_error(self.get("/api/schedule", query_string={"date": "2026-11-12"}), 400, "INVALID_INPUT")
        for value in [None, True, False, 1.0, [], {}, 0, 2**63]:
            with self.subTest(value=value), self.assertRaises(DomainError):
                resource_id(value)
        self.assertEqual(resource_id(2**63 - 1), 2**63 - 1)

    def test_dates_reject_invalid_formats_and_overflow(self):
        for value in ["", "2026-2-01", "2026-02-29", "2026-13-01", "0000-01-01", "9999-12-31",
                      "2026-11-12T00:00", "2026-11-12Z", "２０２６-１１-１２", "2026-11-12 ", "9" * 10000]:
            with self.subTest(value=value[:30]):
                self.assert_error(self.schedule(date=value), 400, "INVALID_INPUT")
        for value in ["2024-02-29", "9999-12-30", "0001-01-01"]:
            self.assertEqual(self.schedule(date=value).status_code, 200)
        self.assert_error(self.get("/api/schedule", query_string={"room_id": "10"}), 400, "INVALID_INPUT")
        start, end = beijing_day("2026-11-12")
        self.assertEqual((start, end), (epoch("2026-11-12T00:00"), epoch("2026-11-13T00:00")))

    def test_authentication_precedes_validation_for_anonymous_temporary_expired_and_logout(self):
        anonymous = self.app.test_client()
        for client in [anonymous, self.app.test_client()]:
            if client is not anonymous:
                self.get("/login", client)
            self.assert_error(self.get("/api/rooms", client), 401, "AUTH_REQUIRED")
            self.assert_error(self.schedule("9" * 10000, "bad", client), 401, "AUTH_REQUIRED")
        self.clock.now += auth.SESSION_SECONDS
        self.assert_error(self.get("/api/rooms"), 401, "AUTH_REQUIRED")
        self.assert_error(self.schedule("bad", "bad"), 401, "AUTH_REQUIRED")
        user = self.login()
        old_token = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        self.client.post("/api/logout", base_url=ORIGIN, headers={"Origin": ORIGIN, "X-CSRF-Token": user["csrf_token"]}, json={})
        self.client.set_cookie(auth.COOKIE_NAME, old_token, domain="127.0.0.1")
        self.assert_error(self.get("/api/rooms"), 401, "AUTH_REQUIRED")
        self.assert_error(self.schedule(), 401, "AUTH_REQUIRED")

    def test_all_roles_only_receive_shared_schedule(self):
        expected = self.schedule().json["data"]
        for username in ["demo_member_b", "demo_admin"]:
            client = self.app.test_client()
            self.login(username, client)
            self.assertEqual(self.schedule(client=client).json["data"], expected)
            self.assertEqual(self.get("/api/rooms", client).status_code, 200)

    def test_service_rechecks_actor_session_before_invalid_input(self):
        with self.app.app_context():
            actor = self.actor()
            for invalid_actor in [None, replace(actor, id=2), replace(actor, session_token_hash="0" * 64)]:
                with self.assertRaises(DomainError) as caught:
                    services.schedule(invalid_actor, "bad", "bad")
                self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
            with db.write_transaction(self.database) as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (actor.session_token_hash,))
            for call in [lambda: services.list_rooms(actor), lambda: services.schedule(actor, "bad", "bad")]:
                with self.assertRaises(DomainError) as caught:
                    call()
                self.assertEqual(caught.exception.code, "AUTH_REQUIRED")

    def test_query_captures_clock_once_for_auth_and_status(self):
        with self.app.app_context():
            actor = self.actor()
            self.clock.calls = 0
            result = services.schedule(actor, 10, "2026-11-12")
            self.assertEqual(self.clock.calls, 1)
            self.assertEqual(result["items"][2]["record"]["status"], "in_progress")
            self.clock.calls = 0
            services.list_rooms(actor)
            self.assertEqual(self.clock.calls, 1)
        self.assertEqual(active_status(NOW, NOW + 1800, NOW - 1), "pending")
        self.assertEqual(active_status(NOW, NOW + 1800, NOW), "in_progress")
        self.assertEqual(active_status(NOW, NOW + 1800, NOW + 1800), "ended")

    def test_read_transaction_is_read_only_and_keeps_consistent_snapshot(self):
        with db.read_transaction(self.database) as conn:
            self.assertEqual(conn.execute("SELECT name FROM rooms WHERE id=10").fetchone()[0], "合成 A")
            with db.write_transaction(self.database) as writer:
                writer.execute("UPDATE rooms SET name='新名称' WHERE id=10")
            self.assertEqual(conn.execute("SELECT name FROM rooms WHERE id=10").fetchone()[0], "合成 A")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("UPDATE rooms SET name='不允许' WHERE id=20")
        self.assertEqual(self.get("/api/rooms").json["data"]["items"][-1]["name"], "新名称")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_seed_is_repeatable_and_preserves_existing_business(self):
        with db.read_transaction(self.database) as conn:
            before = [tuple(row) for row in conn.execute("SELECT * FROM reservations ORDER BY id")]
        self.assertEqual(seed_rooms(self.database, self.clock), 3)
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE rooms SET capacity=99 WHERE name='合成演示 · 讨论室 A'")
        self.assertEqual(seed_rooms(self.database, self.clock), 0)
        with db.read_transaction(self.database) as conn:
            self.assertEqual([tuple(row) for row in conn.execute("SELECT * FROM reservations ORDER BY id")], before)
            self.assertEqual(conn.execute("SELECT capacity FROM rooms WHERE name='合成演示 · 讨论室 A'").fetchone()[0], 99)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)

    def test_story_1_1_schema_upgrade_preserves_accounts_and_sessions(self):
        with db.write_transaction(self.database) as conn:
            users = [tuple(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]
            sessions = [tuple(row) for row in conn.execute("SELECT * FROM sessions ORDER BY token_hash")]
            conn.execute("DROP TABLE occupancy_slots")
            conn.execute("DROP TABLE reservations")
            conn.execute("DROP TABLE rooms")
        db.initialize_database(self.database)
        with db.read_transaction(self.database) as conn:
            self.assertEqual([tuple(row) for row in conn.execute("SELECT * FROM users ORDER BY id")], users)
            self.assertEqual([tuple(row) for row in conn.execute("SELECT * FROM sessions ORDER BY token_hash")], sessions)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        self.assert_list_envelope(self.get("/api/rooms"))
        self.assertEqual(self.get("/api/rooms").json["data"], {"items": [], "total": 0})

    def test_schema_enforces_branches_cancellation_and_slot_constraints(self):
        invalid_sql = [
            "UPDATE reservations SET kind='other' WHERE id=105",
            "UPDATE reservations SET reason='bad' WHERE id=105",
            "UPDATE reservations SET attendees=1.5 WHERE id=105",
            "UPDATE reservations SET title=NULL WHERE id=105",
            "UPDATE reservations SET user_id=NULL WHERE id=101",
            "UPDATE reservations SET title='bad' WHERE id=101",
            "UPDATE reservations SET reason='' WHERE id=101",
            "UPDATE reservations SET start_at=start_at+1 WHERE id=101",
            "UPDATE reservations SET end_at=start_at WHERE id=101",
            "UPDATE reservations SET cancelled_at=123 WHERE id=101",
            "UPDATE reservations SET cancel_reason='bad' WHERE id=101",
            "UPDATE reservations SET cancelled_at=123,cancelled_by=3 WHERE id=101",
            "UPDATE reservations SET cancel_reason=NULL WHERE id=110",
            "UPDATE reservations SET user_id=999 WHERE id=101",
            "UPDATE reservations SET intent_key=(SELECT intent_key FROM reservations WHERE id=105) WHERE id=107",
            "UPDATE rooms SET capacity=1001 WHERE id=30",
            "INSERT INTO occupancy_slots VALUES (30,1800000000,105)",
            "INSERT INTO occupancy_slots SELECT room_id,slot_start,reservation_id FROM occupancy_slots LIMIT 1",
        ]
        for sql in invalid_sql:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with db.write_transaction(self.database) as conn:
                    conn.execute(sql)
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE reservations SET cancel_reason=NULL WHERE id=104")  # member cancellation permitted

    def test_missing_query_schema_is_rejected_on_startup(self):
        with db.write_transaction(self.database) as conn:
            conn.execute("DROP TABLE occupancy_slots")
        with self.assertRaisesRegex(RuntimeError, "schema 不完整"):
            db.check_database(self.database)
        db.initialize_database(self.database)
        # Restore fixture slots so the same invariant remains true after startup check.
        with db.write_transaction(self.database) as conn:
            for row in conn.execute("SELECT id,room_id,start_at,end_at FROM reservations WHERE cancelled_at IS NULL").fetchall():
                conn.executemany("INSERT INTO occupancy_slots VALUES (?,?,?)", [(row["room_id"], t, row["id"]) for t in range(row["start_at"], row["end_at"], 1800)])


if __name__ == "__main__":
    unittest.main()

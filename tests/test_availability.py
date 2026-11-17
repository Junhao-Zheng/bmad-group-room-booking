"""Story 1.3: independent availability cases against complete synthetic slots."""

from dataclasses import replace
from pathlib import Path
import re
import tempfile
import unittest

from booking_app import auth, create_app, db, services
from booking_app.domain import DomainError, beijing_datetime, positive_integer, query_attendees
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from tests.schedule_fixtures import NOW, assert_slot_integrity, epoch, insert_record, seed_schedule_fixture

ORIGIN = "http://127.0.0.1:8000"
PASSWORD = "Synthetic-availability-passphrase"


class FixedClock:
    def __init__(self):
        self.now, self.calls = NOW, 0

    def now_epoch(self):
        self.calls += 1
        return self.now


class AvailabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / "seed.sqlite3"
        seed_users(cls.fixture_db, [
            {"username": username, "display_name": display, "role": role, "password": PASSWORD}
            for username, display, role in DEMO_IDENTITIES
        ], FixedClock())
        seed_schedule_fixture(cls.fixture_db)
        with db.write_transaction(cls.fixture_db) as conn:
            insert_record(conn, 201, 20, "2026-11-13T20:00", "2026-11-15T09:00", kind="block")
            insert_record(conn, 202, 10, "2026-11-12T12:00", "2026-11-12T13:00", cancelled=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "availability.sqlite3"
        source, destination = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(destination)
        source.close()
        destination.close()
        self.clock = FixedClock()
        self.app = create_app({"TESTING": True, "DATABASE": str(self.database), "CLOCK": self.clock})
        self.client = self.app.test_client()
        self.identity = self.login(self.client)
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, client, username="demo_member_a"):
        page = client.get("/login", base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = client.post("/api/login", base_url=ORIGIN,
                               headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                               json={"username": username, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        return response.json["data"]

    def query(self, start="2026-11-12T12:00", end="2026-11-12T12:30", attendees="10", client=None):
        response = (client or self.client).get("/api/availability", base_url=ORIGIN,
            query_string={"start": start, "end": end, "attendees": attendees})
        if response.status_code == 200:
            self.assert_success(response)
        return response

    def assert_success(self, response, expected_items=None):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json
        self.assertIs(type(body), dict)
        self.assertEqual(set(body), {"ok", "data"})
        self.assertIs(type(body["ok"]), bool)
        self.assertIs(body["ok"], True)
        data = body["data"]
        self.assertIs(type(data), dict)
        self.assertEqual(set(data), {"items", "total"})
        self.assertIs(type(data["items"]), list)
        self.assertIs(type(data["total"]), int)
        self.assertEqual(data["total"], len(data["items"]))
        for room in data["items"]:
            self.assertIs(type(room), dict)
            self.assertEqual(set(room), {"id", "name", "location", "capacity"})
            for name in ("id", "capacity"):
                self.assertIs(type(room[name]), int)
            for name in ("name", "location"):
                self.assertIs(type(room[name]), str)
        if expected_items is not None:
            self.assertEqual(body, {"ok": True, "data": {"items": expected_items, "total": len(expected_items)}})

    def actor(self):
        return auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value)

    def assert_error(self, response, code=400, field=None):
        self.assertEqual(response.status_code, code, response.text)
        self.assertEqual(set(response.json), {"ok", "error"})
        self.assertIs(type(response.json["ok"]), bool)
        self.assertIs(response.json["ok"], False)
        error = response.json["error"]
        self.assertEqual(set(error), {"code", "message", "fields", "conflicts"})
        self.assertEqual(error["code"], "AUTH_REQUIRED" if code == 401 else "INVALID_INPUT")
        if field:
            self.assertIn(field, error["fields"])
        self.assertNotIn("Set-Cookie", response.headers)

    def ids(self, **kwargs):
        response = self.query(**kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return [room["id"] for room in response.json["data"]["items"]]

    def test_exact_room_dto_capacity_equality_stable_sort_and_read_only(self):
        with db.read_transaction(self.database) as conn:
            before = list(conn.iterdump())
        response = self.query()
        self.assertEqual(set(response.json), {"ok", "data"})
        self.assertEqual(set(response.json["data"]), {"items", "total"})
        self.assertEqual(response.json["data"], {"items": [
            {"id": 10, "name": "合成 A", "location": "演示楼 101", "capacity": 10},
            {"id": 20, "name": "合成 A", "location": "演示楼 202", "capacity": 20},
            {"id": 30, "name": "合成 C <讨论室>", "location": "演示楼 303", "capacity": 30},
        ], "total": 3})
        self.assertEqual(self.ids(attendees="20"), [20, 30])
        self.assertEqual(self.ids(attendees="30"), [30])
        self.assertEqual(self.ids(attendees="31"), [])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        with self.app.app_context():
            self.assertEqual(services.availability(self.actor(), "2026-11-12T12:00", "2026-11-12T12:30", 10), response.json["data"])
        with db.read_transaction(self.database) as conn:
            self.assertEqual(list(conn.iterdump()), before)

    def test_half_open_booking_boundaries_overlap_and_cancelled_release(self):
        self.assertEqual(self.ids(start="2026-11-12T10:30", end="2026-11-12T11:00"), [30])
        self.assertEqual(self.ids(start="2026-11-12T11:00", end="2026-11-12T11:30"), [20, 30])
        self.assertEqual(self.ids(start="2026-11-12T11:30", end="2026-11-12T12:00"), [10, 20, 30])
        # Active bookings end at 11:30; cancelled booking and revoked block occupy 12:00.
        self.assertEqual(self.ids(), [10, 20, 30])
        self.assert_error(self.query(start="2026-11-12T22:30", end="2026-11-12T23:00"), field="end")

    def test_only_later_slots_occupied_by_booking_or_block_exclude_room(self):
        with db.write_transaction(self.database) as conn:
            insert_record(conn, 203, 10, "2026-11-12T13:00", "2026-11-12T13:30")
        expected = [
            {"id": 20, "name": "合成 A", "location": "演示楼 202", "capacity": 20},
            {"id": 30, "name": "合成 C <讨论室>", "location": "演示楼 303", "capacity": 30},
        ]
        for start, end in [("2026-11-12T12:30", "2026-11-12T13:30"),
                           ("2026-11-12T12:00", "2026-11-12T16:00"),
                           ("2026-11-12T12:30", "2026-11-12T14:30")]:
            with self.subTest(start=start, end=end):
                # The first slot is free; a later booking/block alone excludes room 10.
                self.assert_success(self.query(start, end), expected)

    def test_arbitrary_minute_booking_uses_exact_interval_not_coarse_slots(self):
        teacher_client = self.app.test_client()
        teacher = self.login(teacher_client, "demo_admin")
        payload = dict(room_id=30, title="分钟边界", purpose="讨论", attendees=3,
                       start="2026-11-12T12:10", end="2026-11-12T12:40",
                       intent_key="minute-interval-test-001")
        response = teacher_client.post("/api/bookings", base_url=ORIGIN,
            headers={"Origin": ORIGIN, "X-CSRF-Token": teacher["csrf_token"]}, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn(30, self.ids(start="2026-11-12T12:20", end="2026-11-12T12:50"))
        self.assertIn(30, self.ids(start="2026-11-12T12:40", end="2026-11-12T13:10"))
        self.assertIn(30, self.ids(start="2026-11-12T11:40", end="2026-11-12T12:10"))
        conflict = teacher_client.post("/api/bookings", base_url=ORIGIN,
            headers={"Origin": ORIGIN, "X-CSRF-Token": teacher["csrf_token"]},
            json=payload | {"start":"2026-11-12T12:35", "end":"2026-11-12T13:05",
                            "intent_key":"minute-interval-test-002"})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        with db.read_transaction(self.database) as conn:
            slots = [row[0] for row in conn.execute(
                "SELECT slot_start FROM occupancy_slots WHERE reservation_id=?",
                (response.json["data"]["booking"]["id"],))]
        self.assertEqual(slots, [])  # No complete half-hour lies inside 12:10—12:40.

    def test_name_location_sort_overrides_reverse_ids_with_exact_dto(self):
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE rooms SET name='合成 Z',location='演示楼 999' WHERE id=10")
            conn.execute("UPDATE rooms SET name='合成 A',location='演示楼 101' WHERE id=30")
        self.assert_success(self.query(), [
            {"id": 30, "name": "合成 A", "location": "演示楼 101", "capacity": 30},
            {"id": 20, "name": "合成 A", "location": "演示楼 202", "capacity": 20},
            {"id": 10, "name": "合成 Z", "location": "演示楼 999", "capacity": 10},
        ])

    def test_cross_day_block_excludes_every_covered_day_and_releases_at_end(self):
        for start, end in [("2026-11-13T20:00", "2026-11-13T20:30"),
                           ("2026-11-14T12:00", "2026-11-14T12:30"),
                           ("2026-11-15T08:30", "2026-11-15T09:00")]:
            self.assertEqual(self.ids(start=start, end=end), [10, 30])
        self.assertEqual(self.ids(start="2026-11-15T09:00", end="2026-11-15T09:30"), [10, 20, 30])

    def test_legal_30_minutes_4_hours_and_30_day_equality(self):
        for start, end in [("2026-11-12T12:00", "2026-11-12T12:30"),
                           ("2026-11-12T12:10", "2026-11-12T12:40"),
                           ("2026-11-12T12:00", "2026-11-12T16:00"),
                           ("2026-11-13T08:00", "2026-11-13T08:30"),
                           ("2026-11-13T21:30", "2026-11-13T22:00"),
                           ("2026-11-19T09:30", "2026-11-19T10:00")]:
            self.assertEqual(self.query(start, end).status_code, 200)

    def test_invalid_window_boundaries_have_field_errors(self):
        for start, end, field in [
            ("2026-11-12T10:00", "2026-11-12T10:30", "start"),
            ("2026-11-12T09:30", "2026-11-12T10:00", "start"),
            ("2026-11-12T12:00", "2026-11-12T12:00", "end"),
            ("2026-11-12T12:00", "2026-11-12T11:30", "end"),
            ("2026-11-12T12:00", "2026-11-12T16:30", "end"),
            ("2026-11-13T05:30", "2026-11-13T06:30", "start"),
            ("2026-11-13T07:30", "2026-11-13T08:00", "start"),
            ("2026-11-13T21:30", "2026-11-13T22:30", "end"),
            ("2026-11-19T10:00", "2026-11-19T10:30", "end"),
            ("2026-11-12T23:30", "2026-11-13T00:00", "end"),
            ("2026-11-12T23:30", "2026-11-13T00:30", "end"),
        ]:
            with self.subTest(start=start, end=end):
                self.assert_error(self.query(start, end), field=field)

    def test_strict_time_format_and_date_invalidity_never_500(self):
        for value in ["", "2026-2-01T12:00", "2026-11-12 12:00", "2026-11-12T1:00",
                      "2026-11-12T12:00:00", "2026-11-12T12:00+08:00",
                      "2026-11-12T12:00Z", "2026-11-12T12:00 ", "2026-11-12T24:00",
                      "2026-02-29T12:00", "2026-13-01T12:00", "0000-01-01T00:00",
                      "２０２６-１１-１２T１２:００", "9" * 10000]:
            for field in ("start", "end"):
                with self.subTest(value=value[:30], field=field):
                    self.assert_error(self.query(**{field: value}), field=field)
        for value in [None, True, 20261112, [], {}]:
            with self.assertRaises(DomainError):
                beijing_datetime(value, "start")
        self.assertEqual(beijing_datetime("2024-02-29T12:30", "start"), epoch("2024-02-29T12:30"))
        self.assert_error(self.query(start="0001-01-01T00:00"), field="start")
        self.assert_error(self.query(end="9999-12-31T23:30"), field="end")
        self.assert_error(self.client.get("/api/availability", base_url=ORIGIN), field="start")

    def test_attendees_canonical_validation_huge_values_and_json_separation(self):
        for value in ["", "0", "-1", "+1", "01", "1.0", "1e1", "true", "false", " 10", "10 ", "１０", "١٠", "9" * 10000 + "x"]:
            with self.subTest(value=value[:30]):
                self.assert_error(self.query(attendees=value), field="attendees")
        for value in ["1001", "9999", str(2**63), "9" * 10000]:
            with self.subTest(value=value[:30]):
                response = self.query(attendees=value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["data"], {"items": [], "total": 0})
        self.assert_error(self.query(start="bad", attendees="9" * 10000), field="start")
        for value in [None, True, False, 1.0, [], {}, 0, 1, 2, -1, "2"]:
            with self.assertRaises(DomainError):
                positive_integer(value)
        for value in [None, True, False, 1.0, [], {}, 0, -1]:
            with self.assertRaises(DomainError):
                query_attendees(value)
        self.assertEqual(positive_integer(10**10000), 10**10000)
        for count in ("1", "2"):
            self.assert_error(self.query(attendees=count), field="attendees")
        with self.app.app_context():
            actor = self.actor()
            self.assertEqual(services.availability(actor, "2026-11-12T12:00", "2026-11-12T12:30", 10**10000), {"items": [], "total": 0})
            for value in (True, False, 1.0):
                with self.assertRaises(DomainError):
                    services.availability(actor, "2026-11-12T12:00", "2026-11-12T12:30", value)

    def test_authentication_first_anonymous_temporary_expired_logout_and_all_roles(self):
        anonymous = self.app.test_client()
        self.assert_error(self.query("bad", "bad", "bad", anonymous), 401)
        anonymous.get("/login", base_url=ORIGIN)
        self.assert_error(self.query(client=anonymous), 401)
        for username in ("demo_member_b", "demo_admin"):
            client = self.app.test_client()
            self.login(client, username)
            self.assertEqual(self.ids(client=client), [10, 20, 30])
        self.clock.now = NOW + auth.SESSION_SECONDS
        self.assert_error(self.query("bad", "bad", "bad"), 401)
        self.identity = self.login(self.client)
        old_token = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        self.client.post("/api/logout", base_url=ORIGIN,
                         headers={"Origin": ORIGIN, "X-CSRF-Token": self.identity["csrf_token"]}, json={})
        self.client.set_cookie(auth.COOKIE_NAME, old_token, domain="127.0.0.1")
        self.assert_error(self.query(), 401)

    def test_service_rechecks_auth_and_uses_one_clock_for_auth_and_window(self):
        with self.app.app_context():
            actor = self.actor()
            self.clock.calls = 0
            self.assertEqual(services.availability(actor, "2026-11-12T12:00", "2026-11-12T12:30", 10)["total"], 3)
            self.assertEqual(self.clock.calls, 1)
            for invalid in (None, replace(actor, id=2), replace(actor, session_token_hash="0" * 64)):
                with self.assertRaises(DomainError) as caught:
                    services.availability(invalid, "bad", "bad", False)
                self.assertEqual(caught.exception.code, "AUTH_REQUIRED")
            self.clock.now = NOW + auth.SESSION_SECONDS
            with self.assertRaises(DomainError) as caught:
                services.availability(actor, "bad", "bad", False)
            self.assertEqual(caught.exception.code, "AUTH_REQUIRED")

    def test_no_rooms_is_empty_and_html_form_has_accessible_constraints(self):
        page = self.client.get("/", base_url=ORIGIN)
        for name in ("start", "end", "attendees"):
            self.assertIn(f'for="{name}"', page.text)
            self.assertIn(f'id="{name}-error"', page.text)
            self.assertRegex(page.text, rf'<input id="{name}"[^>]*\brequired\b')
        self.assertEqual(page.text.count('type="datetime-local" step="60"'), 2)
        self.assertIn('type="number" min="3" step="1"', page.text)
        self.assertIn("查询不锁定资源", page.text)
        with db.write_transaction(self.database) as conn:
            conn.execute("DELETE FROM occupancy_slots")
            conn.execute("DELETE FROM reservations")
            conn.execute("DELETE FROM rooms")
        self.assertEqual(self.ids(), [])


if __name__ == "__main__":
    unittest.main()

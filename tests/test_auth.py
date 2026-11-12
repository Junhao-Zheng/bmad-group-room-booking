"""Story 1.1: file-backed legal/rejected paths, expiry, concurrency and rollback."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

from booking_app import create_app, check_runtime
from booking_app import auth, db
from booking_app.domain import DomainError
from scripts.init_demo import DEMO_IDENTITIES, seed_users

ORIGIN = "http://127.0.0.1:8000"
PASSWORD = "Synthetic-only-passphrase-17"


class FixedClock:
    def __init__(self, now=1_800_000_000):
        self.now = now

    def now_epoch(self):
        return self.now


def accounts(password=PASSWORD):
    return [{"username": name, "display_name": display, "password": password, "role": role}
            for name, display, role in DEMO_IDENTITIES]


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / "seed.sqlite3"
        seed_users(cls.fixture_db, accounts(), FixedClock())

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "booking.sqlite3"
        source, destination = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(destination)
        source.close()
        destination.close()
        self.clock = FixedClock()
        self.app = create_app({"TESTING": True, "DATABASE": str(self.database), "CLOCK": self.clock})
        self.client = self.app.test_client()

    def rows(self, table):
        conn = db.connect(self.database)
        try:
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        finally:
            conn.close()

    def get(self, url, client=None):
        return (client or self.client).get(url, base_url=ORIGIN)

    def post(self, url, csrf, data=None, client=None, origin=ORIGIN, **kwargs):
        headers = {"X-CSRF-Token": csrf} if csrf is not None else {}
        if origin is not None:
            headers["Origin"] = origin
        return (client or self.client).post(url, base_url=ORIGIN, headers=headers,
                                           json={} if data is None else data, **kwargs)

    def prepare(self, client=None):
        client = client or self.client
        response = self.get("/login", client)
        self.assertEqual(response.status_code, 200)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)
        raw = client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        return csrf, raw, response

    def login(self, client=None, username="demo_member_a"):
        csrf, raw, _ = self.prepare(client)
        response = self.post("/api/login", csrf, {"username": username, "password": PASSWORD}, client)
        self.assertEqual(response.status_code, 200, response.json)
        return response, raw

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        body = response.json
        self.assertEqual(set(body), {"ok", "error"})
        self.assertFalse(body["ok"])
        self.assertEqual(set(body["error"]), {"code", "message", "fields", "conflicts"})
        self.assertEqual(body["error"]["code"], code)
        self.assertNotIn("Set-Cookie", response.headers)

    def test_empty_directory_initialization_and_repeat_preserves_accounts_and_sessions(self):
        fresh = Path(self.directory.name) / "new" / "demo.sqlite3"
        self.assertEqual(seed_users(fresh, accounts(), self.clock), 3)
        with db.write_transaction(fresh) as conn:
            conn.execute("UPDATE users SET display_name='保留身份', role='admin' WHERE id=1")
            conn.execute("INSERT INTO sessions VALUES (?,1,'preserved',?,?)", ("f" * 64, self.clock.now, self.clock.now + 600))
        conn = db.connect(fresh)
        before = [tuple(row) for row in conn.execute("SELECT * FROM users ORDER BY id")]
        conn.close()
        self.assertEqual(seed_users(fresh, accounts("Different-new-password"), self.clock), 0)
        conn = db.connect(fresh)
        self.assertEqual([tuple(row) for row in conn.execute("SELECT * FROM users ORDER BY id")], before)
        self.assertEqual(conn.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"users", "sessions"})
        conn.close()
        for row in before:
            self.assertTrue(row[3].startswith("scrypt:32768:8:1$"))
            self.assertTrue(check_password_hash(row[3], PASSWORD))
            self.assertNotIn(PASSWORD, row[3])

    def test_initialization_rejects_invalid_accounts_without_creating_database(self):
        fresh = Path(self.directory.name) / "invalid.sqlite3"
        for value in [accounts("short"), accounts()[:2], accounts() + [accounts()[0]]]:
            with self.subTest(value=len(value)), self.assertRaises(ValueError):
                seed_users(fresh, value, self.clock)
            self.assertFalse(fresh.exists())

    def test_login_rotates_token_csrf_and_returns_exact_dto_for_each_role(self):
        for name, display, role in DEMO_IDENTITIES:
            with self.subTest(role=role, name=name):
                client = self.app.test_client()
                csrf, old_token, pre = self.prepare(client)
                self.assertIn("HttpOnly", pre.headers["Set-Cookie"])
                self.assertIn("SameSite=Lax", pre.headers["Set-Cookie"])
                self.assertIn("Max-Age=600", pre.headers["Set-Cookie"])
                result = self.post("/api/login", csrf, {"username": f" {name} ", "password": PASSWORD}, client)
                self.assertEqual(result.status_code, 200)
                user = result.json["data"]
                self.assertEqual(set(user), {"id", "display_name", "role", "csrf_token"})
                self.assertEqual((user["display_name"], user["role"]), (display, role))
                self.assertNotEqual(user["csrf_token"], csrf)
                new_token = client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
                self.assertNotEqual(old_token, new_token)
                self.assertIn("Max-Age=28800", result.headers["Set-Cookie"])
                self.assertNotIn("Domain=", result.headers["Set-Cookie"])
                self.assertEqual(self.get("/api/me", client).json, result.json)
                self.assertIn(display, self.get("/", client).text)
                self.assertEqual(self.get("/login", client).status_code, 302)
                snapshot = json.dumps(self.rows("sessions"), ensure_ascii=False)
                self.assertNotIn(new_token, snapshot)
                self.assertNotIn(old_token, snapshot)
                self.assertNotIn(auth.token_digest(old_token), snapshot)

    def test_invalid_credentials_use_identical_error_and_do_not_change_data(self):
        csrf, _, _ = self.prepare()
        before = self.rows("sessions")
        responses = [self.post("/api/login", csrf, {"username": name, "password": password})
                     for name, password in [("missing-user", PASSWORD), ("demo_member_a", "wrong-password")]]
        for response in responses:
            self.assert_error(response, 401, "INVALID_CREDENTIALS")
            self.assertEqual(response.json["error"]["message"], "账号或密码错误")
        self.assertEqual(responses[0].json, responses[1].json)
        self.assertEqual(self.rows("sessions"), before)

    def test_empty_credentials_are_field_errors(self):
        csrf, _, _ = self.prepare()
        response = self.post("/api/login", csrf, {"username": "  ", "password": ""})
        self.assert_error(response, 400, "INVALID_INPUT")
        self.assertEqual(set(response.json["error"]["fields"]), {"username", "password"})

    def test_temporary_session_refresh_and_expiry_equal_boundary(self):
        csrf, token, _ = self.prepare()
        before = self.rows("sessions")
        self.clock.now += 599
        csrf2, token2, response = self.prepare()
        self.assertEqual((csrf2, token2), (csrf, token))
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertEqual(self.rows("sessions"), before)
        self.clock.now += 1
        self.assert_error(self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD}), 401, "AUTH_REQUIRED")
        csrf3, token3, _ = self.prepare()
        self.assertNotEqual(csrf3, csrf)
        self.assertNotEqual(token3, token)

    def test_session_absolute_expiry_not_extended_by_refresh(self):
        result, _ = self.login()
        before = self.rows("sessions")
        self.clock.now += 28799
        self.assertEqual(self.get("/api/me").status_code, 200)
        self.assertNotIn("Set-Cookie", self.get("/").headers)
        self.assertEqual(self.rows("sessions"), before)
        self.clock.now += 1
        self.assert_error(self.get("/api/me"), 401, "AUTH_REQUIRED")
        self.assert_error(self.post("/api/logout", result.json["data"]["csrf_token"]), 401, "AUTH_REQUIRED")
        self.assertEqual(self.get("/").status_code, 302)
        self.assertEqual(self.rows("sessions"), before)

    def test_logout_revokes_only_current_session_and_old_cookie_cannot_replay(self):
        second = self.app.test_client()
        first_result, _ = self.login()
        second_result, _ = self.login(second)
        raw = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        csrf = first_result.json["data"]["csrf_token"]
        response = self.post("/api/logout", csrf)
        self.assertEqual(response.json, {"ok": True, "data": {"logged_out": True}})
        self.assertIn("Max-Age=0", response.headers["Set-Cookie"])
        self.client.set_cookie(auth.COOKIE_NAME, raw, domain="127.0.0.1")
        self.assert_error(self.get("/api/me"), 401, "AUTH_REQUIRED")
        self.assert_error(self.post("/api/logout", csrf), 401, "AUTH_REQUIRED")
        self.assertEqual(self.get("/api/me", second).json, second_result.json)
        self.assertEqual(len(self.rows("sessions")), 1)

    def test_anonymous_cannot_read_identity_or_home(self):
        self.assert_error(self.get("/api/me"), 401, "AUTH_REQUIRED")
        self.assertEqual(self.get("/").status_code, 302)
        with self.get("/static/app.css") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rows("sessions"), [])

    def test_all_post_routes_reject_bad_origin_and_csrf_without_writes(self):
        for endpoint in ("/api/login", "/api/logout"):
            client = self.app.test_client()
            if endpoint.endswith("login"):
                csrf, _, _ = self.prepare(client)
            else:
                result, _ = self.login(client)
                csrf = result.json["data"]["csrf_token"]
            before = self.rows("sessions")
            for origin in [None, "https://attacker.invalid", ORIGIN + "/", "http://localhost:8000"]:
                response = self.post(endpoint, csrf, client=client, origin=origin)
                self.assert_error(response, 403, "CSRF_REJECTED")
            for bad in [None, "", "wrong", "非ASCII恶意令牌"]:
                response = self.post(endpoint, bad, client=client)
                self.assert_error(response, 403, "CSRF_REJECTED")
            self.assertEqual(self.rows("sessions"), before)

    def test_authenticated_session_cannot_login_again(self):
        result, _ = self.login()
        before = self.rows("sessions")
        self.assert_error(self.post("/api/login", result.json["data"]["csrf_token"],
                                    {"username": "demo_member_b", "password": PASSWORD}), 401, "AUTH_REQUIRED")
        self.assertEqual(self.rows("sessions"), before)

    def test_content_types_json_shape_and_form_csrf(self):
        csrf, _, _ = self.prepare()
        for content_type, body in [("text/plain", "{}"), ("application/json", "[1]"), ("application/json", "{")]:
            response = self.client.post("/api/login", base_url=ORIGIN,
                                        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
                                        content_type=content_type, data=body)
            self.assert_error(response, 400, "INVALID_INPUT")
        response = self.client.post("/api/login", base_url=ORIGIN, headers={"Origin": ORIGIN},
                                    data={"csrf_token": csrf, "username": "demo_member_a", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)

    def test_scrypt_runs_outside_write_lock(self):
        csrf, _, _ = self.prepare()
        original_check = auth.check_password_hash
        def verifier(hashed, password):
            # Acquiring a separate writer proves no writer is held during scrypt.
            with db.write_transaction(self.database) as conn:
                self.assertTrue(conn.in_transaction)
            return original_check(hashed, password)
        with patch.object(auth, "check_password_hash", side_effect=verifier):
            self.assertEqual(self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD}).status_code, 200)

    def test_same_temporary_token_parallel_login_has_one_winner(self):
        csrf, raw, _ = self.prepare()
        barrier = threading.Barrier(2)
        original_check = auth.check_password_hash
        def verifier(hashed, password):
            valid = original_check(hashed, password)
            barrier.wait(timeout=10)
            return valid
        def submit():
            client = self.app.test_client()
            client.set_cookie(auth.COOKIE_NAME, raw, domain="127.0.0.1")
            return self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD}, client)
        with patch.object(auth, "check_password_hash", side_effect=verifier), ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 401])
        self.assert_error(next(r for r in responses if r.status_code == 401), 401, "AUTH_REQUIRED")
        rows = self.rows("sessions")
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0]["user_id"])
        self.assertNotEqual(rows[0]["token_hash"], auth.token_digest(raw))

    def test_login_insert_failure_rolls_back_consumption_and_never_sets_cookie(self):
        csrf, _, _ = self.prepare()
        with db.write_transaction(self.database) as conn:
            conn.execute("CREATE TRIGGER reject_authenticated BEFORE INSERT ON sessions WHEN NEW.user_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'injected'); END")
        before = self.rows("sessions")
        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            response = self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD})
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertEqual(self.rows("sessions"), before)
        self.assertNotIn(PASSWORD, "".join(logs.output))
        self.assertNotIn("injected", "".join(logs.output))

    def test_login_rechecks_expiry_and_password_after_verification(self):
        for mutation in ("expiry", "password", "csrf"):
            client = self.app.test_client()
            csrf, raw, _ = self.prepare(client)
            original_check = auth.check_password_hash
            def verifier(hashed, password):
                valid = original_check(hashed, password)
                if mutation == "expiry":
                    self.clock.now += 600
                else:
                    with db.write_transaction(self.database) as conn:
                        if mutation == "password":
                            conn.execute("UPDATE users SET password_hash=? WHERE username='demo_member_a'", (generate_password_hash("replacement-long-password", method="scrypt:32768:8:1"),))
                        else:
                            conn.execute("UPDATE sessions SET csrf_token='changed' WHERE token_hash=?", (auth.token_digest(raw),))
                return valid
            with self.subTest(mutation=mutation), patch.object(auth, "check_password_hash", side_effect=verifier):
                response = self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD}, client)
                self.assert_error(response, 403 if mutation == "csrf" else 401,
                                  "CSRF_REJECTED" if mutation == "csrf" else "AUTH_REQUIRED")
            self.assertEqual(sum(r["user_id"] is not None for r in self.rows("sessions")), 0)
            with db.write_transaction(self.database) as conn:
                original_hash = self.fixture_hash()
                conn.execute("UPDATE users SET password_hash=? WHERE username='demo_member_a'", (original_hash,))

    def fixture_hash(self):
        conn = db.connect(self.fixture_db)
        try:
            return conn.execute("SELECT password_hash FROM users WHERE username='demo_member_a'").fetchone()[0]
        finally:
            conn.close()

    def test_pre_commit_failure_rolls_back_login_logout_and_preauth_without_cookie(self):
        real_transaction = db.write_transaction
        @contextmanager
        def fail_before_commit(database=None):
            with real_transaction(database) as conn:
                yield conn
                raise RuntimeError("synthetic pre-commit failure")
        with patch.object(db, "write_transaction", fail_before_commit), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.get("/login")
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertEqual(self.rows("sessions"), [])
        csrf, _, _ = self.prepare()
        before = self.rows("sessions")
        with patch.object(db, "write_transaction", fail_before_commit), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD})
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertEqual(self.rows("sessions"), before)
        result, _ = self.login()
        before = self.rows("sessions")
        with patch.object(db, "write_transaction", fail_before_commit), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.post("/api/logout", result.json["data"]["csrf_token"])
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertEqual(self.rows("sessions"), before)
        self.assertEqual(self.get("/api/me").status_code, 200)

    def test_execute_commit_failure_rolls_back_and_never_issues_or_clears_cookie(self):
        real_connect = db.connect
        calls = []
        class FailCommitConnection:
            def __init__(self, conn):
                self.conn = conn
            def __getattr__(self, name):
                return getattr(self.conn, name)
            def execute(self, sql, *args):
                if sql in ("COMMIT", "ROLLBACK"):
                    calls.append(sql)
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("synthetic COMMIT execution failure")
                return self.conn.execute(sql, *args)
        def failing_connect(database):
            return FailCommitConnection(real_connect(database))
        def assert_failed_without_change(operation):
            before = self.rows("sessions")
            calls.clear()
            with patch.object(db, "connect", side_effect=failing_connect), self.assertLogs(self.app.logger, level="ERROR"):
                response = operation()
            self.assert_error(response, 500, "INTERNAL_ERROR")
            self.assertEqual(calls, ["COMMIT", "ROLLBACK"])
            self.assertEqual(self.rows("sessions"), before)
        assert_failed_without_change(lambda: self.get("/login"))
        csrf, raw, _ = self.prepare()
        assert_failed_without_change(lambda: self.post("/api/login", csrf, {"username": "demo_member_a", "password": PASSWORD}))
        self.assertEqual(self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value, raw)
        result, _ = self.login()
        raw = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        assert_failed_without_change(lambda: self.post("/api/logout", result.json["data"]["csrf_token"]))
        self.assertEqual(self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value, raw)
        self.assertEqual(self.get("/api/me").status_code, 200)

    def test_shared_credential_byte_boundaries_can_initialize_and_login(self):
        username, password = "界" * 85 + "a", "密" * 341 + "x"
        self.assertEqual(len(username.encode()), 256)
        self.assertEqual(len(password.encode()), 1024)
        users = accounts()
        users[0].update(username=username, password=password)
        self.assertEqual(seed_users(self.database, users, self.clock), 1)
        csrf, _, _ = self.prepare()
        response = self.post("/api/login", csrf, {"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["data"]["display_name"], users[0]["display_name"])

    def test_login_rejects_oversize_and_invalid_unicode_without_state_change(self):
        csrf, _, _ = self.prepare()
        before = self.rows("sessions")
        for field, value in (("username", "a" * 257), ("password", "b" * 1025),
                             ("username", "界" * 86), ("password", "密" * 342),
                             ("username", "invalid\ud800"), ("password", "invalid\udfff")):
            payload = {"username": "demo_member_a", "password": PASSWORD, field: value}
            with self.subTest(field=field, size=len(value)):
                response = self.post("/api/login", csrf, payload)
                self.assert_error(response, 400, "INVALID_INPUT")
                self.assertEqual(set(response.json["error"]["fields"]), {field})
                self.assertEqual(self.rows("sessions"), before)
        # A normal nonempty wrong password, including a short one, stays a uniform 401.
        self.assert_error(self.post("/api/login", csrf, {"username": "demo_member_a", "password": "x"}), 401, "INVALID_CREDENTIALS")

    def test_initialization_rejects_oversize_and_invalid_unicode_before_database_changes(self):
        before = self.rows("users")
        for field, value in (("username", "a" * 257), ("password", "b" * 1025),
                             ("username", "invalid\ud800"), ("password", "invalid\udfff"),
                             ("display_name", "invalid\ud800")):
            users = accounts()
            users[0][field] = value
            with self.subTest(field=field), self.assertRaises((DomainError, ValueError)):
                seed_users(self.database, users, self.clock)
            self.assertEqual(self.rows("users"), before)

    def run_init_cli(self, config=None, *, mode=0o600, interactive=False):
        command = [sys.executable, "-m", "scripts.init_demo"]
        if not interactive:
            path = Path(self.directory.name) / "input.credentials.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            path.chmod(mode)
            command += ["--credentials-file", str(path)]
        return subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                              env=dict(os.environ, BOOKING_DB_PATH=str(self.database)),
                              input=PASSWORD + "\n", text=True, capture_output=True,
                              start_new_session=True, timeout=10)

    def assert_cli_safe_failure(self, result, before):
        self.assertEqual(result.returncode, 1)
        output = result.stdout + result.stderr
        self.assertNotIn("Traceback", output)
        self.assertNotIn(PASSWORD, output)
        self.assertEqual(self.rows("users"), before)
        self.assertEqual(self.rows("sessions"), [])

    def test_cli_rejects_nonobject_json_without_traceback_or_secret_output(self):
        before = self.rows("users")
        for config in ([], None, PASSWORD, 42, True):
            with self.subTest(shape=type(config).__name__):
                self.assert_cli_safe_failure(self.run_init_cli(config), before)

    def test_cli_rejects_readable_credentials_file_without_database_changes(self):
        before = self.rows("users")
        self.assert_cli_safe_failure(self.run_init_cli({"users": accounts()}, mode=0o644), before)

    def test_cli_rejects_unavailable_hidden_input_with_private_file_guidance(self):
        before = self.rows("users")
        result = self.run_init_cli(interactive=True)
        self.assert_cli_safe_failure(result, before)
        self.assertIn("--credentials-file", result.stderr)
        self.assertIn("600", result.stderr)

    def test_origin_validates_ports_and_matches_browser_default_port_requests(self):
        for bad in ("http://127.0.0.1:abc", "http://127.0.0.1:65536", "http://127.0.0.1:-1",
                    "http://127.0.0.1:0", "http://127.0.0.1:"):
            with self.subTest(origin=bad), self.assertRaisesRegex(RuntimeError, "APP_ORIGIN"):
                create_app({"TESTING": True, "DATABASE": str(self.database), "APP_ORIGIN": bad})
        for configured, canonical in (("http://127.0.0.1:80", "http://127.0.0.1"),
                                      ("https://example.invalid:443", "https://example.invalid"),
                                      ("http://127.0.0.1:8123", "http://127.0.0.1:8123")):
            app = create_app({"TESTING": True, "DATABASE": str(self.database), "APP_ORIGIN": configured,
                              "TRUSTED_HOSTS": ["127.0.0.1", "example.invalid"], "SESSION_COOKIE_SECURE": canonical.startswith("https:")})
            self.assertEqual(app.config["APP_ORIGIN"], canonical)
            client = app.test_client()
            page = client.get("/login", base_url=canonical)
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
            result = client.post("/api/login", base_url=canonical,
                                 headers={"Origin": canonical, "X-CSRF-Token": csrf},
                                 json={"username": "demo_member_a", "password": PASSWORD})
            self.assertEqual(result.status_code, 200, result.json)
            self.assertEqual(client.get("/api/me", base_url=canonical).status_code, 200)

    def test_noscript_notice_requires_javascript_without_changing_json_api(self):
        csrf, _, page = self.prepare()
        self.assertIn("此交互页面需要启用 JavaScript", page.text)
        result = self.client.post("/api/login", base_url=ORIGIN, headers={"Origin": ORIGIN},
                                  data={"csrf_token": csrf, "username": "demo_member_a", "password": PASSWORD})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, "application/json")

    def test_logout_rechecks_expiry_under_lock(self):
        result, _ = self.login()
        before = self.rows("sessions")
        real_transaction = db.write_transaction
        @contextmanager
        def advance_after_lock(database=None):
            with real_transaction(database) as conn:
                self.clock.now += 28800
                yield conn
        with patch.object(db, "write_transaction", advance_after_lock):
            response = self.post("/api/logout", result.json["data"]["csrf_token"])
        self.assert_error(response, 401, "AUTH_REQUIRED")
        self.assertEqual(self.rows("sessions"), before)

    def test_parallel_logout_has_one_commit_and_no_cookie_on_loser(self):
        result, _ = self.login()
        raw = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        csrf = result.json["data"]["csrf_token"]
        barrier = threading.Barrier(2)
        real_transaction = db.write_transaction
        @contextmanager
        def synchronized_transaction(database=None):
            barrier.wait(timeout=10)
            with real_transaction(database) as conn:
                yield conn
        def submit():
            client = self.app.test_client()
            client.set_cookie(auth.COOKIE_NAME, raw, domain="127.0.0.1")
            return self.post("/api/logout", csrf, client=client)
        with patch.object(db, "write_transaction", synchronized_transaction), ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: submit(), range(2)))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 401])
        self.assert_error(next(response for response in responses if response.status_code == 401), 401, "AUTH_REQUIRED")
        self.assertEqual(self.rows("sessions"), [])

    def test_store_busy_is_503_no_cookie_or_state_change(self):
        result, _ = self.login()
        before = self.rows("sessions")
        real_connect = db.connect
        def fast_connect(database):
            conn = real_connect(database)
            conn.execute("PRAGMA busy_timeout=1")
            return conn
        with db.write_transaction(self.database), patch.object(db, "connect", side_effect=fast_connect):
            response = self.post("/api/logout", result.json["data"]["csrf_token"])
        self.assert_error(response, 503, "STORE_BUSY")
        self.assertEqual(self.rows("sessions"), before)

    def test_templates_escape_identity_and_responses_do_not_leak_credentials(self):
        display = '<script>alert("synthetic")</script>'
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET display_name=? WHERE username='demo_member_a'", (display,))
        result, _ = self.login()
        raw = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        page = self.get("/")
        self.assertNotIn(display, page.text)
        self.assertIn("&lt;script&gt;", page.text)
        for response in (result, page, self.get("/api/me")):
            for private in (PASSWORD, raw, auth.token_digest(raw), self.fixture_hash(), "demo_member_a"):
                self.assertNotIn(private, response.text)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])

    def test_session_survives_app_restart_without_extending_expiry(self):
        result, _ = self.login()
        raw = self.client.get_cookie(auth.COOKIE_NAME, domain="127.0.0.1").value
        before = self.rows("sessions")
        restarted = create_app({"TESTING": True, "DATABASE": str(self.database), "CLOCK": self.clock})
        client = restarted.test_client()
        client.set_cookie(auth.COOKIE_NAME, raw, domain="127.0.0.1")
        self.assertEqual(self.get("/api/me", client).json, result.json)
        self.assertEqual(self.rows("sessions"), before)

    def test_connection_pragmas_and_schema_startup_checks(self):
        conn = db.connect(self.database)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 15000)
        self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 2)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        conn.execute("PRAGMA user_version=99")
        conn.close()
        with self.assertRaisesRegex(RuntimeError, "schema"):
            create_app({"TESTING": True, "DATABASE": str(self.database)})
        with self.assertRaisesRegex(RuntimeError, "未初始化"):
            create_app({"TESTING": True, "DATABASE": str(self.database.parent / "absent.sqlite3")})

    def test_runtime_configuration_guards(self):
        with self.assertRaisesRegex(RuntimeError, "TESTING"):
            create_app({"CLOCK": self.clock})
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            create_app({"APP_ORIGIN": "http://example.invalid"})
        with self.assertRaisesRegex(RuntimeError, "COOKIE_SECURE"):
            create_app({"APP_ORIGIN": "https://example.invalid"})
        with patch("booking_app.sqlite3.sqlite_version_info", (3, 50, 0)), self.assertRaisesRegex(RuntimeError, "SQLite"):
            check_runtime()
        https = create_app({"TESTING": True, "DATABASE": str(self.database), "APP_ORIGIN": "https://example.invalid",
                            "TRUSTED_HOSTS": ["example.invalid"], "SESSION_COOKIE_SECURE": True})
        response = https.test_client().get("/login", base_url="https://example.invalid")
        self.assertIn("Secure", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/login", base_url="http://attacker.invalid").status_code, 400)


if __name__ == "__main__":
    unittest.main()

"""Story 2.5 acceptance matrix; independent cases, file database, no inherited tests."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, dto, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError
from scripts.init_demo import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import FULL_KEYS, FixedClock, seed_history_fixture
from tests.schedule_fixtures import NOW, assert_slot_integrity

ORIGIN = 'http://127.0.0.1:8000'


class AdminCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / 'fixture.sqlite3'
        cls.password = secrets.token_urlsafe(24)
        seed_users(cls.fixture_db, [dict(username=u, display_name=d, role=r, password=cls.password)
                                  for u, d, r in DEMO_IDENTITIES], FixedClock())
        seed_history_fixture(cls.fixture_db)

    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'test.sqlite3'
        source, dest = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(dest); source.close(); dest.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING': True, 'DATABASE': str(self.database), 'CLOCK': self.clock})
        self.client, self.identity = self.login('demo_admin')
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, username):
        client = self.app.test_client()
        page = client.get('/login', base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        result = client.post('/api/login', base_url=ORIGIN, headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf},
                             json=dict(username=username, password=self.password))
        self.assertEqual(result.status_code, 200)
        return client, result.json['data']

    def cancel(self, booking_id=103, reason='  维护需要取消  ', client=None, identity=None):
        return (client or self.client).post(f'/api/admin/bookings/{booking_id}/cancel', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': (identity or self.identity)['csrf_token']}, json={'reason': reason})

    def error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json), {'ok', 'error'})
        self.assertFalse(response.json['ok'])
        self.assertEqual(set(response.json['error']), {'code', 'message', 'fields', 'conflicts'})
        self.assertEqual(response.json['error']['code'], code)
        self.assertEqual(response.json['error']['conflicts'], [])

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table: [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('reservations', 'occupancy_slots', 'audit_events')}

    def actor(self):
        return auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME, domain='127.0.0.1').value)

    def test_success_complete_dto_snapshot_same_transaction_once_and_preserved_other_slots(self):
        before = self.facts(); calls = []; connections = []
        original = db.write_transaction
        @contextmanager
        def tracked(database=None):
            with original(database) as conn: connections.append(conn); yield conn
        def writer(conn, event):
            self.assertIs(conn, connections[0]); self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=103').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT cancelled_by FROM reservations WHERE id=103').fetchone()[0], 3)
            calls.append(event); audit_writer(conn, event)
        self.app.config['AUDIT_WRITER'] = writer
        with patch.object(db, 'write_transaction', tracked): result = self.cancel()
        self.assertEqual(result.status_code, 200); self.assertEqual(set(result.json), {'ok', 'data'})
        value = result.json['data']; self.assertEqual(set(value), FULL_KEYS)
        self.assertEqual(set(value['room']), {'id', 'name', 'location', 'capacity'})
        self.assertEqual((value['status'], value['cancelled_at'], value['cancelled_by_id'], value['cancel_reason']),
                         ('cancelled', NOW, 3, '维护需要取消'))
        self.assertEqual(value['cancelled_local'], '2026-11-12T10:00:00+08:00')
        self.assertEqual(value['cancelled_by_display_name'], '演示管理员')
        after = self.facts(); old = next(r for r in before['reservations'] if r['id'] == 103)
        new = next(r for r in after['reservations'] if r['id'] == 103)
        self.assertEqual(new, old | dict(cancelled_at=NOW, cancelled_by=3, cancel_reason='维护需要取消'))
        self.assertEqual(after['occupancy_slots'], [s for s in before['occupancy_slots'] if s['reservation_id'] != 103])
        self.assertEqual(len(calls), 1)
        snapshot = dict(id=103, room_id=1, owner_id=1, title=old['title'], purpose=old['purpose'], attendees=5,
            start_at=old['start_at'], end_at=old['end_at'], created_at=old['created_at'],
            cancelled_at=None, cancelled_by_id=None, cancel_reason=None)
        self.assertEqual(calls[0], dict(actor_id=3, actor_display_name='演示管理员', action='booking.cancelled_by_admin',
            target_type='booking', target_id=103, occurred_at=NOW, before=snapshot,
            after=snapshot | dict(cancelled_at=NOW, cancelled_by_id=3, cancel_reason='维护需要取消'), reason='维护需要取消'))
        self.assertEqual(json.loads(after['audit_events'][0]['before_json']), snapshot)
        self.assertEqual(json.loads(after['audit_events'][0]['after_json']), calls[0]['after'])
        member, _ = self.login('demo_member_a')
        self.assertEqual(member.get('/api/bookings/103', base_url=ORIGIN).json['data'], value)

    def test_exact_time_boundaries_start_equal_and_end_minus_one_allowed_end_equal_closed(self):
        for booking_id, now in [(102, NOW), (103, NOW + 3 * 3600 - 1)]:
            self.clock.now = now
            self.assertEqual(self.cancel(booking_id).status_code, 200)
        before = self.facts()
        for now in [NOW + 3 * 3600, NOW + 3 * 3600 + 1]:
            self.clock.now = now
            self.error(self.cancel(104), 409, 'TRANSITION_CLOSED'); self.assertEqual(self.facts(), before)
        self.error(self.cancel(101), 409, 'TRANSITION_CLOSED')

    def test_repeats_after_end_preserve_admin_or_member_metadata_and_never_call_writer(self):
        original = self.cancel().json['data']
        prior = {i: self.client.get(f'/api/bookings/{i}', base_url=ORIGIN).json['data'] for i in [105, 106]}
        before = self.facts()
        self.app.config['AUDIT_WRITER'] = lambda *_: self.fail('idempotent cancellation invoked writer')
        self.clock.now = NOW + 7 * 3600
        for booking_id, expected in {103: original, **prior}.items():
            response = self.cancel(booking_id, '不同但合法的原因')
            self.assertEqual(response.status_code, 200); self.assertEqual(response.json['data'], expected)
        self.assertEqual(self.facts(), before)

    def test_reason_validation_before_repeats_unicode_boundaries_nul_and_surrogates(self):
        invalid = [None, False, 1, 1.2, [], {}, '', ' \t\n', '字' * 501, 'ok\x00bad', '\ud800', '\udfff']
        before = self.facts()
        for booking_id in [103, 105, 106]:
            for reason in invalid:
                with self.subTest(booking=booking_id, reason=repr(reason)):
                    result = self.cancel(booking_id, reason)
                    self.error(result, 400, 'INVALID_INPUT'); self.assertIn('reason', result.json['error']['fields'])
        self.assertEqual(self.facts(), before)
        for booking_id, reason in [(103, '\u2003😀\t'), (104, '\n' + '😀' * 500 + ' \t')]:
            result = self.cancel(booking_id, reason)
            self.assertEqual(result.status_code, 200); self.assertEqual(result.json['data']['cancel_reason'], reason.strip())

    def test_ids_kind_missing_and_permissions_precede_invalid_parameters(self):
        before = self.facts()
        for username in ['demo_member_a', 'demo_member_b']:
            client, identity = self.login(username)
            for booking_id in [103, 106, 401, '0', '9' * 5000]:
                self.error(self.cancel(booking_id, None, client, identity), 403, 'FORBIDDEN')
        for booking_id in ['0', '01', '-1', '1.0', 'true', '１２', '9223372036854775808', '9' * 5000]:
            self.error(self.cancel(booking_id), 400, 'INVALID_INPUT')
        responses = [self.cancel(i) for i in [401, 999, 2**63 - 1]]
        for response in responses: self.error(response, 404, 'NOT_FOUND')
        self.assertEqual(responses[0].json, responses[1].json)
        with self.app.app_context():
            actor = self.actor()
            for value in [None, True, False, 1.0, [], {}, 2**63]:
                with self.assertRaises(DomainError) as caught: services.admin_cancel_booking(actor, value, '原因')
                self.assertEqual(caught.exception.code, 'INVALID_INPUT')
            for actor in [None, replace(actor, id=1), replace(actor, session_token_hash='0' * 64)]:
                with self.assertRaises(DomainError) as caught: services.admin_cancel_booking(actor, False, None)
                self.assertEqual(caught.exception.code, 'AUTH_REQUIRED')
        self.assertEqual(self.facts(), before)

    def test_json_shape_origin_csrf_malformed_utf8_and_anonymous_leave_storage_unchanged(self):
        before = self.facts(); path = '/api/admin/bookings/103/cancel'
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.identity['csrf_token']}
        for value in [{}, [], False, None, 'reason', {'reason': '取消', 'user_id': 1}]:
            self.error(self.client.post(path, base_url=ORIGIN, headers=headers, data=json.dumps(value),
                content_type='application/json'), 400, 'INVALID_INPUT')
        self.error(self.client.post(path, base_url=ORIGIN, headers=headers, data=b'{"reason":"\xff"}',
            content_type='application/json'), 400, 'INVALID_INPUT')
        self.error(self.client.post(path, base_url=ORIGIN, headers=headers,
            data={'reason': '取消', 'csrf_token': self.identity['csrf_token']}), 400, 'INVALID_INPUT')
        for bad in [{}, {'Origin': 'http://evil.example'}, {'Origin': ORIGIN}, {'Origin': ORIGIN, 'X-CSRF-Token': 'bad'}]:
            self.error(self.client.post(path, base_url=ORIGIN, headers=bad, json={'reason': '取消'}), 403, 'CSRF_REJECTED')
        self.error(self.app.test_client().post('/api/admin/bookings/0/cancel', base_url=ORIGIN,
            headers={'Origin': ORIGIN}, json={'reason': None}), 401, 'AUTH_REQUIRED')
        self.assertEqual(self.facts(), before)

    def test_expired_logged_out_and_demoted_sessions_are_rejected(self):
        before = self.facts(); self.clock.now = NOW + auth.SESSION_SECONDS
        self.error(self.cancel('0', None), 401, 'AUTH_REQUIRED')
        self.clock.now = NOW
        stale = self.client.get_cookie(auth.COOKIE_NAME, domain='127.0.0.1').value
        with self.app.app_context(): actor = self.actor()
        self.assertEqual(self.client.post('/api/logout', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': self.identity['csrf_token']}, json={}).status_code, 200)
        self.client.set_cookie(auth.COOKIE_NAME, stale, domain='127.0.0.1')
        self.error(self.cancel(), 401, 'AUTH_REQUIRED')
        with self.app.app_context():
            with self.assertRaises(DomainError) as caught: services.admin_cancel_booking(actor, 103, '原因')
            self.assertEqual(caught.exception.code, 'AUTH_REQUIRED')
        self.client, self.identity = self.login('demo_admin')
        with self.app.app_context(): actor = self.actor()
        with db.write_transaction(self.database) as conn: conn.execute("UPDATE users SET role='member' WHERE id=3")
        self.error(self.cancel('0', None), 403, 'FORBIDDEN')
        with self.app.app_context():
            with self.assertRaises(DomainError) as caught: services.admin_cancel_booking(actor, False, None)
            self.assertEqual(caught.exception.code, 'FORBIDDEN')
        self.assertEqual(self.facts(), before)

    def test_lock_time_expiry_logout_demotion_and_deadline_are_rechecked(self):
        original = db.write_transaction; before = self.facts()
        for mutation, now, status, code in [
            (None, NOW + auth.SESSION_SECONDS, 401, 'AUTH_REQUIRED'),
            ('DELETE FROM sessions', NOW, 401, 'AUTH_REQUIRED'),
            ("UPDATE users SET role='member' WHERE id=3", NOW, 403, 'FORBIDDEN'),
            (None, NOW + 3 * 3600, 409, 'TRANSITION_CLOSED')]:
            self.clock.now = NOW
            @contextmanager
            def changed(database=None):
                with original(database) as conn:
                    if mutation: conn.execute(mutation)
                    self.clock.now = now
                    yield conn
            with patch.object(db, 'write_transaction', changed): self.error(self.cancel(), status, code)
            self.assertEqual(self.facts(), before)

    def test_fresh_actor_name_role_one_locked_clock_and_current_dto_audit_snapshot(self):
        with self.app.app_context(): actor = self.actor()
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET display_name='事件时名字' WHERE id=3")
        with self.app.app_context():
            self.clock.calls = 0
            result = services.admin_cancel_booking(replace(actor, role='member', display_name='陈旧名字'), 103, '原因')
            self.assertEqual(self.clock.calls, 1)
        self.assertEqual(result['cancelled_by_display_name'], '事件时名字')
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET display_name='当前名字' WHERE id=3")
            conn.execute("UPDATE users SET display_name='当前预约人' WHERE id=1")
            conn.execute("UPDATE rooms SET name='当前会议室' WHERE id=1")
        repeated = self.cancel().json['data']
        self.assertEqual(repeated['cancelled_by_display_name'], '当前名字')
        self.assertEqual(repeated['owner_display_name'], '当前预约人'); self.assertEqual(repeated['room']['name'], '当前会议室')
        self.assertEqual(self.facts()['audit_events'][0]['actor_display_name'], '事件时名字')

    def test_real_write_lock_wait_crosses_end_before_single_clock_capture(self):
        before = self.facts()
        with self.app.app_context(): actor = self.actor()
        owner = db.connect(self.database)
        owner.execute('BEGIN IMMEDIATE')
        attempted = threading.Event(); original = db.connect
        def observed(database):
            conn = original(database)
            conn.set_trace_callback(lambda sql: attempted.set() if sql == 'BEGIN IMMEDIATE' else None)
            return conn
        def cancel():
            with self.app.app_context():
                try: services.admin_cancel_booking(actor, 103, '真实锁等待')
                except DomainError as error: return error.code
                return 'unexpected success'
        self.clock.now = NOW + 3 * 3600 - 1; self.clock.calls = 0
        try:
            with patch.object(db, 'connect', observed), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(cancel)
                try:
                    # The real SQLite BEGIN has reached the trace callback while another
                    # connection owns the write lock. No sleep or transaction substitute.
                    self.assertTrue(attempted.wait(5))
                    self.assertFalse(future.done()); self.assertEqual(self.clock.calls, 0)
                    self.clock.now += 1
                finally: owner.execute('ROLLBACK')
                self.assertEqual(future.result(timeout=5), 'TRANSITION_CLOSED')
                self.assertEqual(self.clock.calls, 1)
        finally: owner.close()
        self.assertEqual(self.facts(), before)

    def test_real_begin_lock_timeout_maps_to_503_without_storage_changes(self):
        before = self.facts(); owner = db.connect(self.database)
        owner.execute('BEGIN IMMEDIATE')
        attempted = threading.Event(); original = db.connect
        def short_timeout(database):
            conn = original(database)
            conn.execute('PRAGMA busy_timeout=50')
            conn.set_trace_callback(lambda sql: attempted.set() if sql == 'BEGIN IMMEDIATE' else None)
            return conn
        try:
            with patch.object(db, 'connect', short_timeout), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.cancel)
                self.assertTrue(attempted.wait(5))
                response = future.result(timeout=5)
                self.assertTrue(owner.in_transaction)
                self.error(response, 503, 'STORE_BUSY')
                self.assertEqual(self.facts(), before)
        finally:
            owner.execute('ROLLBACK'); owner.close()
        self.assertEqual(self.facts(), before)

    def test_writer_before_after_insert_and_actual_sqlite_commit_denial_all_rollback(self):
        before = self.facts()
        for phase in ['before', 'after', 'commit']:
            calls = []
            def fail(conn, event):
                calls.append(event)
                if phase != 'before': audit_writer(conn, event)
                if phase == 'commit':
                    conn.set_authorizer(lambda action, first, *_: sqlite3.SQLITE_DENY
                        if action == sqlite3.SQLITE_TRANSACTION and first == 'COMMIT' else sqlite3.SQLITE_OK)
                else: raise RuntimeError('sensitive SQL fault')
            self.app.config['AUDIT_WRITER'] = fail
            with self.assertLogs(self.app.logger, level='ERROR') as logs: response = self.cancel()
            self.error(response, 500, 'INTERNAL_ERROR'); self.assertEqual(len(calls), 1)
            self.assertNotIn('sensitive', response.text + str(logs.output)); self.assertNotIn('SQL', response.text)
            self.assertEqual(self.facts(), before)
        self.app.config['AUDIT_WRITER'] = audit_writer
        self.assertEqual(self.cancel().status_code, 200)

    def test_member_route_keeps_start_deadline_and_repeat_admin_reason_with_same_result(self):
        self.error(self.client.post('/api/bookings/301/cancel', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': self.identity['csrf_token']}, json={}), 409, 'TRANSITION_CLOSED')
        self.assertEqual(self.cancel(301).status_code, 200)
        result = self.cancel().json['data']; member, identity = self.login('demo_member_a')
        repeated = member.post('/api/bookings/103/cancel', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': identity['csrf_token']}, json={})
        self.assertEqual(repeated.json['data'], result)
        self.assertEqual(len(self.facts()['audit_events']), 2)


if __name__ == '__main__': unittest.main()

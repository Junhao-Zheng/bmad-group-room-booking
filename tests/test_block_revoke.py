"""Administrator block revocation: state, boundaries, authorization and atomicity."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError, local_time
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import FixedClock
from tests.maintenance_contract import BLOCK_KEYS, BLOCK_SNAPSHOT_KEYS
from tests.schedule_fixtures import NOW, assert_slot_integrity, insert_record, seed_schedule_fixture

ORIGIN = 'http://127.0.0.1:8000'


class BlockRevokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.directory.name) / 'fixture.sqlite3'
        cls.password = secrets.token_urlsafe(24)
        seed_users(cls.fixture, [dict(username=u, display_name=d, role=r, password=cls.password)
                                for u, d, r in (*DEMO_IDENTITIES, ('second_admin', '第二管理员', 'admin'))], FixedClock())
        seed_schedule_fixture(cls.fixture)
        with db.write_transaction(cls.fixture) as conn:
            insert_record(conn, 112, 30, '2026-11-12T09:00', '2026-11-12T11:00', kind='block')
            insert_record(conn, 113, 20, '2026-11-12T12:00', '2026-11-13T12:00', kind='block')
            insert_record(conn, 114, 20, '2026-11-12T12:00', '2026-11-12T13:00', cancelled=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.database = Path(temp.name) / 'test.sqlite3'
        source, target = db.connect(self.fixture), db.connect(self.database)
        source.backup(target); source.close(); target.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING': True, 'DATABASE': str(self.database), 'CLOCK': self.clock})
        self.client, self.identity = self.login('demo_admin')
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, username):
        client = self.app.test_client()
        page = client.get('/login', base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = client.post('/api/login', base_url=ORIGIN, headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf},
                               json=dict(username=username, password=self.password))
        self.assertEqual(response.status_code, 200)
        return client, response.json['data']

    def revoke(self, block_id=113, values=None, client=None, identity=None):
        return (client or self.client).post(f'/api/admin/blocks/{block_id}/revoke', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': (identity or self.identity)['csrf_token']},
            json={'reason': ' 维护完成 '} if values is None else values)

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table: [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('rooms', 'reservations', 'occupancy_slots', 'audit_events')}

    def error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json), {'ok', 'error'})
        self.assertFalse(response.json['ok'])
        self.assertEqual(set(response.json['error']), {'code', 'message', 'fields', 'conflicts'})
        self.assertEqual(response.json['error']['code'], code)
        self.assertEqual(response.json['error']['conflicts'], [])

    def test_pending_revoke_exact_details_first_metadata_and_atomic_audit(self):
        before = self.facts(); connections = []; events = []; original = db.write_transaction
        @contextmanager
        def tracked(database=None):
            with original(database) as conn:
                connections.append(conn)
                yield conn
        def writer(conn, event):
            self.assertIs(conn, connections[-1]); self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=113').fetchone()[0], 0)
            events.append(event); audit_writer(conn, event)
        self.app.config['AUDIT_WRITER'] = writer
        with patch.object(db, 'write_transaction', tracked):
            response = self.revoke(values={'reason': ' \u0085<img src=x>🧪\u0085 ', 'cancelled_by': 1, 'revoked_at': 0})
        self.assertEqual(response.status_code, 200); value = response.json['data']
        self.assertEqual(set(response.json), {'ok', 'data'}); self.assertEqual(set(value), BLOCK_KEYS)
        self.assertEqual((value['status'], value['revoked_by_id'], value['revoked_at'], value['revoke_reason']),
                         ('revoked', 3, NOW, '<img src=x>🧪'))
        self.assertEqual(value['revoked_local'], local_time(NOW))
        self.assertEqual(value['revoked_by_display_name'], '演示管理员')
        after = self.facts(); old = next(r for r in before['reservations'] if r['id'] == 113)
        self.assertEqual(after['reservations'], [row | dict(cancelled_at=NOW, cancelled_by=3, cancel_reason='<img src=x>🧪')
                                               if row['id'] == 113 else row for row in before['reservations']])
        self.assertEqual(after['occupancy_slots'], [row for row in before['occupancy_slots'] if row['reservation_id'] != 113])
        self.assertEqual(value['reason'], old['reason']); self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event['action'], event['target_type'], event['target_id']), ('block.revoked', 'block', 113))
        self.assertEqual(set(event['before']), BLOCK_SNAPSHOT_KEYS)
        self.assertEqual(event['after'], event['before'] | dict(revoked_at=NOW, revoked_by_id=3, revoke_reason='<img src=x>🧪'))
        self.assertEqual((event['actor_id'], event['occurred_at'], event['reason']), (3, NOW, '<img src=x>🧪'))
        self.assertEqual(json.loads(after['audit_events'][0]['before_json']), event['before'])
        self.assertEqual(json.loads(after['audit_events'][0]['after_json']), event['after'])

    def test_ongoing_including_last_second_and_exact_end_rejected(self):
        self.clock.now = NOW + 3599
        self.assertEqual(self.revoke(112).status_code, 200)
        before = self.facts()
        for at in (NOW + 3600, NOW + 3601):
            self.clock.now = at
            self.error(self.revoke(101), 409, 'TRANSITION_CLOSED')
            self.assertEqual(self.facts(), before)
        # A separate still-active record ends at 11:30.
        with db.write_transaction(self.database) as conn:
            insert_record(conn, 115, 30, '2026-11-12T11:00', '2026-11-12T11:30', kind='block')
        before = self.facts(); self.clock.now = NOW + 5400
        self.error(self.revoke(115), 409, 'TRANSITION_CLOSED'); self.assertEqual(self.facts(), before)

    def test_repeat_after_end_other_admin_preserves_first_result_and_requires_valid_reason(self):
        first = self.revoke(112).json['data']; second, identity = self.login('second_admin')
        before = self.facts()
        self.app.config['AUDIT_WRITER'] = lambda *_: self.fail('Replay must not audit')
        for now in (first['end_at'], first['end_at'] + 1):
            self.clock.now = now
            response = self.revoke(112, {'reason': '不同原因'}, second, identity)
            self.assertEqual(response.status_code, 200); self.assertEqual(response.json['data'], first)
            self.error(self.revoke(112, {'reason': '   '}, second, identity), 400, 'INVALID_INPUT')
        self.assertEqual(self.facts(), before)
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE rooms SET name='当前名称' WHERE id=30")
        current = self.revoke(112).json['data']
        self.assertEqual(current['room']['name'], '当前名称')
        self.assertEqual({k:v for k,v in current.items() if k!='room'}, {k:v for k,v in first.items() if k!='room'})

    def test_reason_types_unicode_bounds_and_whitespace(self):
        before = self.facts()
        for body in ({}, [], False, 'text', *[{'reason': v} for v in ('', ' \u0085 ', 'x'*501, 'x\x00y', '\ud800', None, 1, True, [])]):
            with self.subTest(body=repr(body)):
                self.error(self.revoke(values=body), 400, 'INVALID_INPUT'); self.assertEqual(self.facts(), before)
        self.assertEqual(self.revoke(112, {'reason': ' \n🧪\t '}).json['data']['revoke_reason'], '🧪')
        self.assertEqual(self.revoke(113, {'reason': ' \n'+'🧪'*500+'\t '}).json['data']['revoke_reason'], '🧪'*500)

    def test_booking_wrong_kind_missing_and_invalid_id_never_change_facts(self):
        before = self.facts()
        for value in (103, 104, 107, 114, 999, 2**63-1):
            self.error(self.revoke(value), 404, 'NOT_FOUND')
        for value in ('0', '01', '-1', '1.0', 'true', str(2**63), '9'*5000):
            self.error(self.revoke(value), 400, 'INVALID_INPUT')
        self.assertEqual(self.facts(), before)

    def test_auth_role_csrf_mime_and_stale_sessions_rejected_even_on_replay(self):
        self.revoke(112); before = self.facts()
        member, identity = self.login('demo_member_a')
        for record in (112, 113):
            self.error(self.revoke(record, {}, member, identity), 403, 'FORBIDDEN')
            anonymous = self.app.test_client()
            self.error(anonymous.post(f'/api/admin/blocks/{record}/revoke', base_url=ORIGIN,
                                     headers={'Origin': ORIGIN}, json={}), 401, 'AUTH_REQUIRED')
        for headers in ({}, {'Origin': 'http://evil.invalid'}, {'Origin': ORIGIN}, {'Origin': ORIGIN, 'X-CSRF-Token': 'invalid'}):
            self.error(self.client.post('/api/admin/blocks/113/revoke', base_url=ORIGIN, headers=headers, json={'reason':'x'}), 403, 'CSRF_REJECTED')
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': self.identity['csrf_token']}
        self.error(self.client.post('/api/admin/blocks/113/revoke', base_url=ORIGIN, headers=headers, data={}), 400, 'INVALID_INPUT')
        cookie = self.client.get_cookie(auth.COOKIE_NAME, domain='127.0.0.1').value
        self.client.post('/api/logout', base_url=ORIGIN, headers=headers, json={})
        self.client.set_cookie(auth.COOKIE_NAME, cookie, domain='127.0.0.1')
        self.error(self.revoke(112), 401, 'AUTH_REQUIRED')
        self.client, self.identity = self.login('demo_admin'); self.clock.now = NOW + auth.SESSION_SECONDS
        self.error(self.revoke(112), 401, 'AUTH_REQUIRED'); self.assertEqual(self.facts(), before)

    def test_transaction_rechecks_actor_clock_role_and_deadline_after_lock(self):
        original = db.write_transaction; before = self.facts()
        for now, status, code in ((NOW+auth.SESSION_SECONDS, 401, 'AUTH_REQUIRED'), (NOW+3600, 409, 'TRANSITION_CLOSED')):
            self.clock.now = NOW
            @contextmanager
            def advance(database=None):
                with original(database) as conn:
                    self.clock.now = now; yield conn
            with patch.object(db, 'write_transaction', advance): self.error(self.revoke(112), status, code)
            self.assertEqual(self.facts(), before)
        self.clock.now = NOW
        with self.app.app_context():
            actor = auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME, domain='127.0.0.1').value)
            for bad in (None, replace(actor, id=1), replace(actor, session_token_hash='0'*64)):
                with self.assertRaises(DomainError) as caught: services.revoke_block(bad, 113, {})
                self.assertEqual(caught.exception.code, 'AUTH_REQUIRED')
            self.clock.calls = 0
            services.revoke_block(replace(actor, display_name='伪造姓名'), 112, {'reason': '完成'})
            self.assertEqual(self.clock.calls, 1)
            with db.write_transaction(self.database) as conn: conn.execute("UPDATE users SET role='member' WHERE id=3")
            for record in (112, 113):
                with self.assertRaises(DomainError) as caught: services.revoke_block(actor, record, {})
                self.assertEqual(caught.exception.code, 'FORBIDDEN')
            with db.write_transaction(self.database) as conn: conn.execute('DELETE FROM sessions')
            with self.assertRaises(DomainError) as caught: services.revoke_block(actor, 112, {'reason':'x'})
            self.assertEqual(caught.exception.code, 'AUTH_REQUIRED')

    def test_audit_and_commit_failures_roll_back_state_slots_and_audit(self):
        before = self.facts()
        for after in (False, True):
            def fail(conn, event):
                if after: audit_writer(conn, event)
                raise RuntimeError('private injected fault')
            self.app.config['AUDIT_WRITER'] = fail
            with self.assertLogs(self.app.logger, level='ERROR') as logs: self.error(self.revoke(), 500, 'INTERNAL_ERROR')
            self.assertNotIn('private', str(logs.output)); self.assertEqual(self.facts(), before)
        self.app.config['AUDIT_WRITER'] = audit_writer; original = db.connect
        class FailCommit:
            def __init__(self, conn): self.conn = conn
            def __getattr__(self, name): return getattr(self.conn, name)
            def execute(self, sql, *args):
                if sql == 'COMMIT': raise sqlite3.OperationalError('injected commit failure')
                return self.conn.execute(sql, *args)
        with patch.object(db, 'connect', lambda *a, **kw: FailCommit(original(*a, **kw))), self.assertLogs(self.app.logger, level='ERROR'):
            self.error(self.revoke(), 500, 'INTERNAL_ERROR')
        self.assertEqual(self.facts(), before); self.assertEqual(self.revoke().status_code, 200)

    def test_release_all_occupancy_schedule_availability_without_restoring_cancelled_booking(self):
        # 本用例验证导师直订；其余用例仍保留真实学生角色。
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET role='teacher' WHERE id=1")
        before = self.facts(); self.assertEqual(self.revoke().status_code, 200)
        rows = self.client.get('/api/schedule?room_id=20&date=2026-11-12', base_url=ORIGIN).json['data']['items']
        self.assertFalse(any(row['kind']=='block' and row['record']['id']==113 for row in rows))
        available = self.client.get('/api/availability?start=2026-11-12T12:00&end=2026-11-12T13:00&attendees=5', base_url=ORIGIN).json['data']['items']
        self.assertIn(20, [room['id'] for room in available])
        member, identity = self.login('demo_member_a')
        result = member.post('/api/bookings', base_url=ORIGIN, headers={'Origin': ORIGIN, 'X-CSRF-Token': identity['csrf_token']},
            json=dict(room_id=20, start='2026-11-12T12:00', end='2026-11-12T13:00', title='替代预约', purpose='测试', attendees=5, intent_key='revoke-slot-reuse-0001'))
        self.assertEqual(result.status_code, 201)
        cancelled = next(r for r in before['reservations'] if r['id']==114)
        self.assertEqual(next(r for r in self.facts()['reservations'] if r['id']==114), cancelled)


if __name__ == '__main__':
    unittest.main()

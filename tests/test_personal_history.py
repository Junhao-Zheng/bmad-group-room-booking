"""Story 2.3: independent fixtures, exact DTOs, boundaries, session and object privacy."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import re
import secrets
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.domain import DomainError
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import CANCEL_REASON, FULL_KEYS, PURPOSE, TITLE, FixedClock, seed_history_fixture
from tests.schedule_fixtures import NOW, epoch, assert_slot_integrity

ORIGIN = 'http://127.0.0.1:8000'

class PersonalHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / 'fixture.sqlite3'
        cls.password = secrets.token_urlsafe(24)
        seed_users(cls.fixture_db, [dict(username=u, display_name=d, role=r, password=cls.password)
                                  for u, d, r in (*DEMO_IDENTITIES, ('demo_empty', '合成空记录成员', 'member'))], FixedClock())
        seed_history_fixture(cls.fixture_db)

    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'test.sqlite3'
        source, dest = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(dest); source.close(); dest.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING': True, 'DATABASE': str(self.database), 'CLOCK': self.clock})
        self.client = self.login('demo_member_a')
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, username):
        client = self.app.test_client()
        page = client.get('/login', base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = client.post('/api/login', base_url=ORIGIN,
            headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf}, json={'username': username, 'password': self.password})
        self.assertEqual(response.status_code, 200)
        return client

    def get(self, path, client=None): return (client or self.client).get(path, base_url=ORIGIN)

    def actor(self, client=None):
        return auth.actor_for_token((client or self.client).get_cookie(auth.COOKIE_NAME, domain='127.0.0.1').value)

    def data(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json), {'ok', 'data'})
        self.assertIs(response.json['ok'], True)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response.json['data']

    def error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(set(response.json), {'ok', 'error'})
        self.assertEqual(set(response.json['error']), {'code', 'message', 'fields', 'conflicts'})
        self.assertEqual(response.json['error']['code'], code)
        return response.json

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('reservations', 'occupancy_slots', 'audit_events')}

    def test_four_filters_exact_contract_descending_ties_and_cancel_priority(self):
        expected = {None: [106,105,104,103,102,101], 'pending': [104,103], 'in_progress': [102],
                    'ended': [101], 'cancelled': [106,105]}
        for status, ids in expected.items():
            response = self.get('/api/bookings/mine' + (f'?status={status}' if status else ''))
            result = self.data(response)
            self.assertEqual(set(result), {'items','total'})
            self.assertEqual(result['total'], len(ids))
            self.assertEqual([b['id'] for b in result['items']], ids)
            for booking in result['items']:
                self.assertEqual(set(booking), FULL_KEYS)
                self.assertEqual(set(booking['room']), {'id','name','location','capacity'})
                self.assertEqual(self.data(self.get(f"/api/bookings/{booking['id']}")), booking)
                self.assertEqual(booking['owner_id'], 1)
                if status: self.assertEqual(booking['status'], status)
                if booking['status'] != 'cancelled':
                    for field in ['cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason']:
                        self.assertIsNone(booking[field])
        self.assertEqual(self.data(self.get('/api/bookings/105'))['cancel_reason'], CANCEL_REASON)
        self.assertEqual(self.data(self.get('/api/bookings/105'))['cancelled_by_display_name'], '演示管理员')
        self.assertIsNone(self.data(self.get('/api/bookings/106'))['cancel_reason'])
        self.assertEqual(self.data(self.get('/api/bookings/104'))['purpose'], PURPOSE)
        self.assertEqual(self.data(self.get('/api/bookings/104'))['title'], TITLE)

    def test_representative_full_dto_values_against_independent_fixed_expectations(self):
        common = dict(supervisor_id=None,supervisor_display_name=None,supervisor_source='legacy',application_id=None,approved_at=None,approved_by=None,owner_id=1, owner_display_name='演示成员甲', attendees=5,
                      created_at=1794362400, created_local='2026-11-11T10:00:00+08:00')
        expected = [
            dict(common, id=104, room=dict(id=2, name='合成历史乙', location='演示楼 202', capacity=20),
                 title=TITLE, purpose=PURPOSE, start_at=1794456000, start_local='2026-11-12T12:00:00+08:00',
                 end_at=1794459600, end_local='2026-11-12T13:00:00+08:00', status='pending',
                 cancelled_at=None, cancelled_local=None, cancelled_by_id=None,
                 cancelled_by_display_name=None, cancel_reason=None),
            dict(common, id=105, room=dict(id=1, name='合成历史甲 <会议室>', location='合成位置'*25, capacity=10),
                 title='合成历史活动 105', purpose='本人私密用途 105', start_at=1794463200,
                 start_local='2026-11-12T14:00:00+08:00', end_at=1794466800,
                 end_local='2026-11-12T15:00:00+08:00', status='cancelled', cancelled_at=1794445200,
                 cancelled_local='2026-11-12T09:00:00+08:00', cancelled_by_id=3,
                 cancelled_by_display_name='演示管理员', cancel_reason=CANCEL_REASON),
            dict(common, id=106, room=dict(id=1, name='合成历史甲 <会议室>', location='合成位置'*25, capacity=10),
                 title='合成历史活动 106', purpose='本人私密用途 106', start_at=1794466800,
                 start_local='2026-11-12T15:00:00+08:00', end_at=1794470400,
                 end_local='2026-11-12T16:00:00+08:00', status='cancelled', cancelled_at=1794445200,
                 cancelled_local='2026-11-12T09:00:00+08:00', cancelled_by_id=1,
                 cancelled_by_display_name='演示成员甲', cancel_reason=None),
        ]
        listing = self.data(self.get('/api/bookings/mine'))['items']
        for record in expected:
            self.assertEqual(self.data(self.get(f"/api/bookings/{record['id']}")), record)
            self.assertEqual(next(item for item in listing if item['id']==record['id']), record)

    def test_exact_start_end_boundaries_in_list_and_detail(self):
        for now, status in [(epoch('2026-11-12T12:00')-1, 'pending'),
                            (epoch('2026-11-12T12:00'), 'in_progress'),
                            (epoch('2026-11-12T13:00')-1, 'in_progress'),
                            (epoch('2026-11-12T13:00'), 'ended')]:
            self.clock.now = now
            self.assertEqual(self.data(self.get('/api/bookings/103'))['status'], status)
            items = self.data(self.get('/api/bookings/mine?status='+status))['items']
            self.assertIn(103, [b['id'] for b in items])
            self.assertEqual(self.data(self.get('/api/bookings/105'))['status'], 'cancelled')
        self.clock.now = epoch('2026-11-12T16:00')
        self.assertEqual(self.data(self.get('/api/bookings/106'))['status'], 'cancelled')

    def test_query_identity_ignored_and_member_privacy_admin_list_stays_personal(self):
        for username, owner, ids in [('demo_member_a',1,[106,105,104,103,102,101]),
                                     ('demo_member_b',2,[201]),('demo_admin',3,[301])]:
            client = self.login(username)
            items = self.data(self.get('/api/bookings/mine?user_id=2&owner_id=1&actor=3',client))['items']
            self.assertEqual([b['id'] for b in items],ids)
            self.assertTrue(all(b['owner_id']==owner for b in items))
        denied = self.error(self.get('/api/bookings/201'),404,'NOT_FOUND')
        self.assertEqual(denied,self.error(self.get('/api/bookings/999'),404,'NOT_FOUND'))
        self.assertEqual(denied,self.error(self.get('/api/bookings/401'),404,'NOT_FOUND'))
        other = self.login('demo_member_b')
        self.assertEqual(denied,self.error(self.get('/api/bookings/105',other),404,'NOT_FOUND'))
        admin = self.login('demo_admin')
        self.assertEqual(self.data(self.get('/api/bookings/105',admin))['cancel_reason'],CANCEL_REASON)
        self.error(self.get('/api/bookings/401',admin),404,'NOT_FOUND')

    def test_latest_database_role_and_names_not_cached_actor_claims(self):
        admin = self.login('demo_admin')
        with self.app.app_context():
            stale = self.actor(admin)
            with db.write_transaction(self.database) as conn:
                conn.execute("UPDATE users SET role='member' WHERE id=3")
            with self.assertRaises(DomainError) as caught: services.booking_detail(stale,105)
            self.assertEqual(caught.exception.code,'NOT_FOUND')
            member = self.actor()
            with self.assertRaises(DomainError): services.booking_detail(replace(member,role='admin'),201)
            with db.write_transaction(self.database) as conn:
                conn.execute("UPDATE users SET role='admin',display_name='当前名字' WHERE id=1")
                conn.execute("UPDATE rooms SET name='当前房间' WHERE id=1")
                conn.execute("UPDATE users SET display_name='当前取消操作者' WHERE id=3")
            self.assertEqual(services.booking_detail(member,201)['owner_id'],2)
            current = services.booking_detail(member,105)
            self.assertEqual(current['owner_display_name'],'当前名字')
            self.assertEqual(current['room']['name'],'当前房间')
            self.assertEqual(current['cancelled_by_display_name'],'当前取消操作者')
            self.assertTrue(all(b['owner_id']==1 for b in services.my_bookings(member)['items']))

    def test_authentication_precedes_bad_parameters_and_rechecks_session(self):
        anonymous = self.app.test_client()
        for path in ['/api/bookings/mine?status=bad','/api/bookings/0','/api/bookings/'+'9'*5000]:
            self.error(self.get(path,anonymous),401,'AUTH_REQUIRED')
        self.assertEqual(self.get('/my',anonymous).status_code,302)
        with self.app.app_context():
            actor = self.actor()
            for fake in [None,replace(actor,id=2),replace(actor,session_token_hash='0'*64)]:
                for operation in [lambda:services.my_bookings(fake,[]),lambda:services.booking_detail(fake,'bad')]:
                    with self.assertRaises(DomainError) as caught: operation()
                    self.assertEqual(caught.exception.code,'AUTH_REQUIRED')
            with db.write_transaction(self.database) as conn:
                conn.execute('DELETE FROM sessions WHERE token_hash=?',(actor.session_token_hash,))
            with self.assertRaises(DomainError) as caught: services.booking_detail(actor,105)
            self.assertEqual(caught.exception.code,'AUTH_REQUIRED')
        self.error(self.get('/api/bookings/mine'),401,'AUTH_REQUIRED')

    def test_session_expiry_between_route_and_service_at_equal_boundary(self):
        original = db.read_transaction
        @contextmanager
        def expire_in_service(database=None):
            with original(database) as conn:
                self.clock.now = NOW + auth.SESSION_SECONDS
                yield conn
        for path in ['/api/bookings/mine', '/api/bookings/103']:
            self.clock.now = NOW
            with patch.object(db, 'read_transaction', expire_in_service), \
                    patch.object(services, '_require_actor', wraps=services._require_actor) as checked:
                self.error(self.get(path), 401, 'AUTH_REQUIRED')
                checked.assert_called_once()
                self.assertEqual(checked.call_args.args[2], NOW + auth.SESSION_SECONDS)

    def test_strict_status_ids_static_mine_route_and_empty_success(self):
        for status in ['', 'PENDING','pending ','all','0']:
            response = self.get('/api/bookings/mine',None) if status is None else self.client.get(
                '/api/bookings/mine',base_url=ORIGIN,query_string={'status':status})
            self.error(response,400,'INVALID_INPUT')
        for value in ['0','01','-1','1.0','true','１２','9223372036854775808','9'*5000]:
            error = self.error(self.get('/api/bookings/'+value),400,'INVALID_INPUT')
            self.assertIn('booking_id',error['error']['fields'])
        self.error(self.get('/api/bookings/9223372036854775807'),404,'NOT_FOUND')
        with self.app.app_context():
            actor = self.actor()
            for value in [True,False,1.0,[],None,2**63]:
                with self.assertRaises(DomainError) as caught: services.booking_detail(actor,value)
                self.assertEqual(caught.exception.code,'INVALID_INPUT')
            for value in [True,[],{},1]:
                with self.assertRaises(DomainError) as caught: services.my_bookings(actor,value)
                self.assertEqual(caught.exception.code,'INVALID_INPUT')
        other = self.login('demo_member_b')
        self.assertEqual(self.data(self.get('/api/bookings/mine?status=cancelled',other)),{'items':[],'total':0})
        self.assertEqual(self.data(self.get('/api/bookings/mine'))['total'],6)
        empty = self.login('demo_empty')
        self.assertEqual(self.data(self.get('/api/bookings/mine',empty)),{'items':[],'total':0})

    def test_read_transaction_one_clock_snapshot_no_writes_and_reopen(self):
        before = self.facts()
        with self.app.app_context():
            actor = self.actor()
            for call in [lambda:services.my_bookings(actor),lambda:services.booking_detail(actor,105)]:
                self.clock.calls = 0
                with patch.dict(self.app.config,AUDIT_WRITER=lambda *_:self.fail('Read must not audit')):
                    call()
                self.assertEqual(self.clock.calls,1)
            original = auth.read_session
            boundaries = []
            def change_after_session_select(conn, token_hash, now):
                session = original(conn, token_hash, now)
                self.assertTrue(conn.in_transaction)
                self.assertIsNotNone(session)
                boundaries.append(now)
                # The session SELECT has established the snapshot; no booking SELECT yet.
                with db.write_transaction(self.database) as writer:
                    writer.execute("UPDATE rooms SET name='并发新房名' WHERE id=1")
                    writer.execute("UPDATE users SET display_name='并发新名字' WHERE id=1")
                self.clock.now += 3600
                return session
            self.clock.calls = 0
            with patch.object(auth, 'read_session', change_after_session_select):
                result = services.my_bookings(actor)
            self.assertEqual(boundaries, [NOW])
            self.assertEqual(self.clock.calls, 1)
            self.assertTrue(all(b['owner_display_name']=='演示成员甲' for b in result['items']))
            self.assertTrue(all(b['room']['name']!='并发新房名' for b in result['items']))
            self.assertEqual(next(b['status'] for b in result['items'] if b['id']==102), 'in_progress')
            # A separate read after the transaction sees the committed update.
            self.assertEqual(services.booking_detail(actor, 103)['room']['name'], '并发新房名')
        self.assertEqual(self.facts(),before)
        self.app = create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client = self.login('demo_member_a')
        self.assertEqual(self.data(self.get('/api/bookings/mine'))['total'],6)
        self.assertEqual(self.data(self.get('/api/bookings/104'))['purpose'],PURPOSE)
        self.assertEqual(self.facts(),before)

    def test_html_navigation_logout_fields_and_no_placeholder_mutation(self):
        page = self.get('/my')
        self.assertEqual(page.status_code,200)
        for value in ['我的预约','全部状态','待开始','进行中','已结束','已取消','history.js','csrf_token','auth-feedback','退出登录']:
            self.assertIn(value,page.text)
        self.assertNotIn('取消预约</button>',page.text)
        self.assertIn('aria-current="page">我的预约',page.text)
        self.assertNotIn('<img src=x',page.text)

if __name__ == '__main__': unittest.main()

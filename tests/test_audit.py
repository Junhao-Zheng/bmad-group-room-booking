"""Story 3.4: real transitions, exact evidence DTO and read authorization."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, db, services
from booking_app.domain import DomainError, beijing_day
from tests import test_auth as auth_test
from tests.test_auth import FixedClock, accounts, ORIGIN
from scripts.init_demo import seed_users
from tests.schedule_fixtures import NOW

AUDIT_KEYS = {'id','actor_id','actor_display_name','action','target_type','target_id','occurred_at','occurred_local','before','after','reason'}

class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name)/'seed.sqlite3'
        seed_users(cls.fixture_db, accounts(), FixedClock(NOW))
    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()
    setUp = auth_test.AuthTests.setUp
    rows = auth_test.AuthTests.rows
    get = auth_test.AuthTests.get
    post = auth_test.AuthTests.post
    prepare = auth_test.AuthTests.prepare
    login = auth_test.AuthTests.login
    assert_error = auth_test.AuthTests.assert_error

    def admin(self):
        self.clock.now = NOW
        response, _ = self.login(username='demo_admin')
        return response.json['data']['csrf_token']

    def mutation(self, path, payload, csrf, client=None, expected=200):
        result = self.post(path, csrf, payload, client)
        self.assertEqual(result.status_code, expected, result.json)
        return result.json['data']

    def test_all_seven_actions_exact_snapshots_and_repeats(self):
        csrf = self.admin()
        room = self.mutation('/api/admin/rooms',dict(name='<script>text</script>',location='L',capacity=20),csrf,expected=201)
        updated = self.mutation('/api/admin/rooms/1',dict(name=room['name'],location='L2',capacity=18),csrf)
        self.mutation('/api/admin/rooms/1',dict(name=room['name'],location='L2',capacity=18),csrf)
        member = self.app.test_client(); response,_ = self.login(member); member_csrf = response.json['data']['csrf_token']
        payload = dict(room_id=1,title='<img src=x>',purpose='private business purpose',attendees=3,start='2026-11-13T12:00',end='2026-11-13T13:00',intent_key='audit-original-intent')
        booking = self.mutation('/api/bookings',payload,member_csrf,member,201)['booking']
        self.mutation('/api/bookings',payload,member_csrf,member)
        self.mutation(f"/api/bookings/{booking['id']}/cancel",{},member_csrf,member)
        self.mutation(f"/api/bookings/{booking['id']}/cancel",{},member_csrf,member)
        self.mutation('/api/bookings',payload,member_csrf,member)
        second = self.mutation('/api/bookings',payload|dict(intent_key='audit-another-intent'),member_csrf,member,201)['booking']
        self.mutation(f"/api/admin/bookings/{second['id']}/cancel",dict(reason='admin reason'),csrf)
        self.mutation(f"/api/admin/bookings/{second['id']}/cancel",dict(reason='ignored repeat'),csrf)
        block = self.mutation('/api/admin/blocks',dict(room_id=1,start=payload['start'],end=payload['end'],reason='maintenance'),csrf,expected=201)
        self.mutation(f"/api/admin/blocks/{block['id']}/revoke",dict(reason='finished'),csrf)
        self.mutation(f"/api/admin/blocks/{block['id']}/revoke",dict(reason='ignored repeat'),csrf)
        before = self.rows('audit_events')
        with db.write_transaction(self.database) as conn: conn.execute("UPDATE users SET display_name='new name' WHERE id=3")
        response = self.get('/api/admin/audit'); self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        result=response.json['data']; self.assertEqual(set(result),{'items','total'}); self.assertEqual(result['total'],8)
        events=result['items']; self.assertEqual([e['id'] for e in events],list(range(8,0,-1)))
        self.assertEqual({e['action'] for e in events},{'room.created','room.updated','booking.created','booking.cancelled_by_member','booking.cancelled_by_admin','block.created','block.revoked'})
        for event,saved in zip(events,reversed(before)):
            self.assertEqual(set(event),AUDIT_KEYS)
            self.assertEqual(event['before'],json.loads(saved['before_json']) if saved['before_json'] else None)
            self.assertEqual(event['after'],json.loads(saved['after_json']))
            self.assertEqual(event['reason'],saved['reason'])
            self.assertEqual(event['reason'],{
                'booking.cancelled_by_admin':'admin reason', 'block.created':'maintenance',
                'block.revoked':'finished',
            }.get(event['action']))
            self.assertEqual(event['occurred_at'],NOW);self.assertTrue(event['occurred_local'].endswith('+08:00'))
            if event['actor_id']==3:self.assertEqual(event['actor_display_name'],'演示管理员')
            self.assertNotIn('new name',json.dumps(event))
        self.assertEqual(events[-1]['after'],room);self.assertEqual(events[-2]['before'],room);self.assertEqual(events[-2]['after'],updated)
        records={r['id']:r for r in self.rows('reservations')}
        for event in events:
            if event['action'] in ('booking.cancelled_by_member','booking.cancelled_by_admin','block.revoked'):
                record=records[event['target_id']]; snap=event['after'];prefix='revoked' if record['kind']=='block' else 'cancelled'
                self.assertEqual(snap[prefix+'_at'],record['cancelled_at']);self.assertEqual(snap[prefix+'_by_id'],record['cancelled_by'])
                self.assertIsNone(event['before'][prefix+'_at'])
        self.assertEqual(self.rows('occupancy_slots'),[]);self.assertEqual(self.rows('audit_events'),before)
        for secret in ('password','csrf','token_hash','intent_key','cookie','request_payload'):
            self.assertNotIn(secret,json.dumps(events))
        page=self.get('/admin').text
        for marker in ('id="audit-form"','for="audit-date"','id="audit-results"','audit.js'):self.assertIn(marker,page)

    def test_date_half_open_filters_sort_and_empty(self):
        csrf=self.admin(); start,end=beijing_day('2026-11-12')
        for index,t in enumerate((start-1,start,end-1,end,end-1)):
            self.clock.now=t
            # Keep authenticated session valid for the boundary fixture.
            with db.write_transaction(self.database) as conn:conn.execute('UPDATE sessions SET expires_at=?',(end+1000,))
            self.mutation('/api/admin/rooms',dict(name=str(index),location='test',capacity=1),csrf,expected=201)
        response=self.get('/api/admin/audit?target_type=room&date=2026-11-12').json['data']
        self.assertEqual([r['id'] for r in response['items']],[5,3,2]);self.assertEqual(response['total'],3)
        self.assertEqual(self.get('/api/admin/audit?target_type=booking').json['data'],dict(items=[],total=0))
        for query in ('target_type=','target_type=ROOM','target_type=invalid','date=','date=2026-02-30','date=9999-12-31','date=2026-1-1'):
            self.assert_error(self.get('/api/admin/audit?'+query),400,'INVALID_INPUT')

    def test_anonymous_member_expired_logged_out_and_role_recheck(self):
        self.assert_error(self.get('/api/admin/audit?date=bad'),401,'AUTH_REQUIRED')
        self.clock.now=NOW;result,_=self.login();self.assert_error(self.get('/api/admin/audit?date=bad'),403,'FORBIDDEN')
        self.client=self.app.test_client();csrf=self.admin();token=self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value
        with self.app.app_context():actor=auth.actor_for_token(token)
        with db.write_transaction(self.database) as conn:conn.execute("UPDATE users SET role='member' WHERE id=3")
        with self.app.app_context():
            with self.assertRaises(DomainError) as found:services.audit_events(replace(actor,role='admin'),date='bad')
            self.assertEqual(found.exception.code,'FORBIDDEN')
        with db.write_transaction(self.database) as conn:conn.execute("UPDATE users SET role='admin' WHERE id=3")
        original=db.read_transaction
        @contextmanager
        def advance(database=None):
            with original(database) as conn:self.clock.now=NOW+auth.SESSION_SECONDS;yield conn
        with patch.object(db,'read_transaction',advance):self.assert_error(self.get('/api/admin/audit?date=bad'),401,'AUTH_REQUIRED')
        self.clock.now=NOW;self.mutation('/api/logout',{},csrf)
        self.client.set_cookie(auth.COOKIE_NAME,token,domain='127.0.0.1');self.assert_error(self.get('/api/admin/audit'),401,'AUTH_REQUIRED')

    def test_service_uses_one_clock_and_read_only_snapshot(self):
        self.admin();token=self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value
        with self.app.app_context():
            actor=auth.actor_for_token(token)
            with patch.object(self.clock,'now_epoch',wraps=self.clock.now_epoch) as clock:
                self.assertEqual(services.audit_events(actor),dict(items=[],total=0));self.assertEqual(clock.call_count,1)
            for forged in (None,replace(actor,id=1),replace(actor,session_token_hash='bad')):
                with self.assertRaises(DomainError) as found:services.audit_events(forged,target_type=[])
                self.assertEqual(found.exception.code,'AUTH_REQUIRED')

    def test_corrupt_json_fails_without_partial_events_or_private_logs(self):
        csrf=self.admin();self.mutation('/api/admin/rooms',dict(name='room',location='L',capacity=4),csrf,expected=201)
        for column,value in [('after_json','{private SQL secret'),('after_json','[]'),('after_json','null'),('before_json','"secret"'),('after_json','{"password":"secret"}')]:
            with db.write_transaction(self.database) as conn:
                conn.execute('PRAGMA ignore_check_constraints=ON')  # Deliberately corrupt storage only in this test.
                conn.execute('UPDATE audit_events SET before_json=NULL,after_json=?',(json.dumps(dict(id=1,name='room',location='L',capacity=4)),))
                conn.execute(f'UPDATE audit_events SET {column}=?',(value,))
            with self.assertLogs(self.app.logger,level='ERROR') as logs:self.assert_error(self.get('/api/admin/audit'),500,'INTERNAL_ERROR')
            self.assertNotIn('secret',str(logs.output));self.assertNotIn('private',str(logs.output))

    def test_parseable_static_contradictions_fail_safely_without_rewriting_history(self):
        csrf=self.admin();self.mutation('/api/admin/rooms',dict(name='room',location='L',capacity=4),csrf,expected=201)
        room=dict(id=1,name='room',location='L',capacity=4)
        base=dict(action='room.created',target_type='room',target_id=1,before_json=None,after_json=json.dumps(room))
        cases=[dict(action='booking.created'),dict(action='room.unknown'),dict(action='room.updated'),
               dict(before_json=json.dumps(room)),dict(after_json=json.dumps(room|dict(id=999))),
               dict(action='room.updated',before_json=json.dumps(room|dict(id=999)))]
        cases += [dict(after_json=json.dumps(room|dict(capacity=value))) for value in (-1,0,1001)]
        cases.append(dict(target_id=0,after_json=json.dumps(room|dict(id=0))))
        for change in cases:
            with self.subTest(change=change):
                values=base|change
                with db.write_transaction(self.database) as conn:
                    conn.execute('PRAGMA ignore_check_constraints=ON')
                    conn.execute('UPDATE audit_events SET action=:action,target_type=:target_type,target_id=:target_id,before_json=:before_json,after_json=:after_json',values)
                before=self.rows('audit_events')
                with self.assertLogs(self.app.logger,level='ERROR'):self.assert_error(self.get('/api/admin/audit'),500,'INTERNAL_ERROR')
                self.assertEqual(self.rows('audit_events'),before)

    def test_historical_snapshots_stay_readable_but_invalid_ids_or_attendees_fail(self):
        csrf=self.admin();self.mutation('/api/admin/rooms',dict(name='room',location='L',capacity=4),csrf,expected=201)
        historical=dict(id=9,room_id=1,owner_id=1,title='historical',purpose='past',attendees=4,
                        start_at=1800,end_at=3600,created_at=0,cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
        def store(snapshot):
            with db.write_transaction(self.database) as conn:
                conn.execute("UPDATE audit_events SET action='booking.created',target_type='booking',target_id=9,before_json=NULL,after_json=?",(json.dumps(snapshot),))
        store(historical)
        self.assertEqual(self.get('/api/admin/audit').json['data']['items'][0]['after'],historical)
        for field,value in [('attendees',0),('attendees',-1),('room_id',0),('owner_id',-1),('owner_id',2**63),('cancelled_by_id',0)]:
            with self.subTest(field=field,value=value):
                store(historical|{field:value})
                with self.assertLogs(self.app.logger,level='ERROR'):self.assert_error(self.get('/api/admin/audit'),500,'INTERNAL_ERROR')

if __name__=='__main__':unittest.main()

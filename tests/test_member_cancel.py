"""Story 2.4 independent member-cancellation acceptance tests (no inherited cases)."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import re
import secrets
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import FULL_KEYS, FixedClock, seed_history_fixture
from tests.schedule_fixtures import NOW, epoch, assert_slot_integrity

ORIGIN = 'http://127.0.0.1:8000'


class MemberCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / 'fixture.sqlite3'
        cls.password = secrets.token_urlsafe(24)
        seed_users(cls.fixture_db, [dict(username=u,display_name=d,role=r,password=cls.password)
                                  for u,d,r in DEMO_IDENTITIES], FixedClock())
        seed_history_fixture(cls.fixture_db)

    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'test.sqlite3'
        source, dest = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(dest); source.close(); dest.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client, self.identity = self.login('demo_member_a')
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, username):
        client = self.app.test_client()
        page = client.get('/login', base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
        result = client.post('/api/login', base_url=ORIGIN, headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},
                             json=dict(username=username,password=self.password))
        self.assertEqual(result.status_code,200)
        return client, result.json['data']

    def cancel(self, booking_id=103, data=None, client=None, identity=None):
        return (client or self.client).post(f'/api/bookings/{booking_id}/cancel', base_url=ORIGIN,
            headers={'Origin':ORIGIN,'X-CSRF-Token':(identity or self.identity)['csrf_token']},
            json={} if data is None else data)

    def error(self, response, status, code):
        self.assertEqual(response.status_code,status,response.text)
        self.assertEqual(response.json, {'ok':False,'error':dict(code=code,
            message=response.json['error']['message'],fields=response.json['error']['fields'],conflicts=[])})
        return response.json

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('reservations','occupancy_slots','audit_events')}

    def actor(self):
        return auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value)

    def test_success_exact_dto_atomic_audit_complete_snapshots_and_preserved_intent(self):
        before = self.facts(); calls = []; connections = []
        original = db.write_transaction
        @contextmanager
        def tracked(database=None):
            with original(database) as conn:
                connections.append(conn); yield conn
        def writer(conn,event):
            self.assertIs(conn,connections[0]); self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=103').fetchone()[0],0)
            calls.append(event); audit_writer(conn,event)
        self.app.config['AUDIT_WRITER'] = writer
        with patch.object(db,'write_transaction',tracked): result = self.cancel()
        self.assertEqual(result.status_code,200)
        self.assertEqual(set(result.json),{'ok','data'}); value = result.json['data']
        self.assertEqual(set(value),FULL_KEYS)
        self.assertEqual((value['status'],value['cancelled_at'],value['cancelled_by_id'],value['cancel_reason']),
                         ('cancelled',NOW,1,None))
        self.assertEqual(value['cancelled_local'],'2026-11-12T10:00:00+08:00')
        after=self.facts(); old=next(r for r in before['reservations'] if r['id']==103)
        new=next(r for r in after['reservations'] if r['id']==103)
        self.assertEqual(new,old|dict(cancelled_at=NOW,cancelled_by=1,cancel_reason=None))
        self.assertEqual(after['occupancy_slots'],[s for s in before['occupancy_slots'] if s['reservation_id']!=103])
        self.assertEqual(len(calls),1); event=calls[0]
        expected_before=dict(id=103,room_id=1,owner_id=1,title='合成历史活动 103',purpose='本人私密用途 103',
            attendees=5,start_at=1794456000,end_at=1794459600,created_at=1794362400,
            cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
        self.assertEqual(event,dict(actor_id=1,actor_display_name='演示成员甲',action='booking.cancelled_by_member',
            target_type='booking',target_id=103,occurred_at=NOW,before=expected_before,
            after=expected_before|dict(cancelled_at=NOW,cancelled_by_id=1),reason=None))
        self.assertEqual(json.loads(after['audit_events'][0]['before_json']),event['before'])
        self.assertEqual(json.loads(after['audit_events'][0]['after_json']),event['after'])

    def test_ownership_before_repeat_other_missing_and_block_are_same_404_even_for_admin(self):
        before=self.facts()
        for username in ['demo_member_a','demo_member_b','demo_admin']:
            client, identity=self.login(username)
            forbidden=[201,401,999,2**63-1] if username=='demo_member_a' else [103,105,106,401,999]
            responses=[self.error(self.cancel(i,client=client,identity=identity),404,'NOT_FOUND') for i in forbidden]
            self.assertTrue(all(r==responses[0] for r in responses))
        self.assertEqual(self.facts(),before)

    def test_repeat_after_start_and_end_returns_original_metadata_without_writer(self):
        result=self.cancel().json['data']; before=self.facts()
        def forbidden(*_): self.fail('Repeated cancellation must not call writer')
        self.app.config['AUDIT_WRITER']=forbidden
        for now in [result['start_at'],result['end_at'],result['end_at']+1]:
            self.clock.now=now
            self.assertEqual(self.cancel().json['data'],result)
        # Previously admin-cancelled owned record also preserves original reason and actor.
        original=self.client.get('/api/bookings/105',base_url=ORIGIN).json['data']
        self.assertEqual(self.cancel(105).json['data'],original)
        self.assertEqual(self.facts(),before)

    def test_first_cancel_start_equal_and_later_closed_admin_own_has_same_deadline(self):
        for username, booking_id in [('demo_member_a',103),('demo_admin',301)]:
            self.clock.now=NOW
            client,identity=self.login(username)
            start=epoch('2026-11-12T12:00') if booking_id==103 else NOW
            before=self.facts()
            for now in [start,start+1,start+3600]:
                self.clock.now=now
                self.error(self.cancel(booking_id,client=client,identity=identity),409,'TRANSITION_CLOSED')
                self.assertEqual(self.facts(),before)
        self.clock.now=epoch('2026-11-12T12:00')-1
        self.assertEqual(self.cancel().status_code,200)

    def test_admin_can_cancel_only_own_pending_record_with_member_audit_and_no_reason(self):
        self.clock.now=NOW-1
        admin,identity=self.login('demo_admin')
        response=self.cancel(301,client=admin,identity=identity)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['data']['cancelled_by_id'],3)
        self.assertIsNone(response.json['data']['cancel_reason'])
        self.assertEqual(self.facts()['audit_events'][0]['action'],'booking.cancelled_by_member')

    def test_strict_empty_json_ids_origin_csrf_authentication_and_no_mutations(self):
        before=self.facts()
        headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']}
        for body in [dict(reason='no'),dict(user_id=1),[],False,'text',None]:
            response=self.client.post('/api/bookings/103/cancel',base_url=ORIGIN,headers=headers,
                                      data=json.dumps(body),content_type='application/json')
            self.error(response,400,'INVALID_INPUT')
        self.error(self.client.post('/api/bookings/103/cancel',base_url=ORIGIN,headers=headers,data={}),400,'INVALID_INPUT')
        for value in ['0','01','-1','true','1.0','9223372036854775808','9'*5000]:
            self.error(self.cancel(value),400,'INVALID_INPUT')
        for bad_headers in [{},{'Origin':'http://evil.example'},{'Origin':ORIGIN},{'Origin':ORIGIN,'X-CSRF-Token':'bad'}]:
            self.error(self.client.post('/api/bookings/103/cancel',base_url=ORIGIN,headers=bad_headers,json={}),403,'CSRF_REJECTED')
        anonymous=self.app.test_client()
        self.error(anonymous.post('/api/bookings/0/cancel',base_url=ORIGIN,headers={'Origin':ORIGIN},json={'bad':1}),401,'AUTH_REQUIRED')
        self.assertEqual(self.facts(),before)

    def test_lock_time_session_role_identity_and_one_clock_rechecked(self):
        original=db.write_transaction; before=self.facts()
        for now,code,status in [(NOW+auth.SESSION_SECONDS,'AUTH_REQUIRED',401),(epoch('2026-11-12T12:00'),'TRANSITION_CLOSED',409)]:
            self.clock.now=NOW
            @contextmanager
            def advance(database=None):
                with original(database) as conn:
                    self.clock.now=now; yield conn
            with patch.object(db,'write_transaction',advance): self.error(self.cancel(),status,code)
            self.assertEqual(self.facts(),before)
        self.clock.now=NOW
        with self.app.app_context():
            actor=self.actor()
            for bad in [None,replace(actor,id=2),replace(actor,session_token_hash='0'*64)]:
                with self.assertRaises(DomainError) as caught: services.member_cancel_booking(bad,False)
                self.assertEqual(caught.exception.code,'AUTH_REQUIRED')
            for bad in [True,False,1.0,None,[],2**63]:
                with self.assertRaises(DomainError) as caught: services.member_cancel_booking(actor,bad)
                self.assertEqual(caught.exception.code,'INVALID_INPUT')
            with db.write_transaction(self.database) as conn: conn.execute("UPDATE users SET display_name='当前名字' WHERE id=1")
            self.clock.calls=0
            result=services.member_cancel_booking(replace(actor,role='admin',display_name='旧名字'),103)
            self.assertEqual(self.clock.calls,1); self.assertEqual(result['cancelled_by_display_name'],'当前名字')
            self.assertEqual(self.facts()['audit_events'][0]['actor_display_name'],'当前名字')
            with db.write_transaction(self.database) as conn: conn.execute('DELETE FROM sessions')
            with self.assertRaises(DomainError) as caught: services.member_cancel_booking(actor,103)
            self.assertEqual(caught.exception.code,'AUTH_REQUIRED')

    def test_audit_failure_before_and_after_insert_rolls_back_everything_then_slot_reuse_and_replay(self):
        before=self.facts()
        for after_insert in [False,True]:
            def fail(conn,event):
                if after_insert: audit_writer(conn,event)
                raise RuntimeError('sensitive SQL fault')
            self.app.config['AUDIT_WRITER']=fail
            with self.assertLogs(self.app.logger,level='ERROR') as logs:
                result=self.cancel()
            self.error(result,500,'INTERNAL_ERROR')
            self.assertNotIn('sensitive',result.text+str(logs.output)); self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer
        result=self.cancel().json['data']
        headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']}
        payload=dict(room_id=1,title='合成历史活动 103',purpose='本人私密用途 103',attendees=5,
                     start='2026-11-12T12:00',end='2026-11-12T13:00',intent_key='history-fixture-0103')
        response=self.client.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload)
        self.assertEqual(response.status_code,200); self.assertTrue(response.json['data']['replayed'])
        self.assertEqual(response.json['data']['booking'],result)
        self.assertNotIn(result['title'],self.client.get('/api/schedule?room_id=1&date=2026-11-12',base_url=ORIGIN).text)
        rooms=self.client.get('/api/availability?start=2026-11-12T12:00&end=2026-11-12T13:00&attendees=5',base_url=ORIGIN).json['data']['items']
        self.assertIn(1,[room['id'] for room in rooms])
        replacement=self.client.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload|dict(intent_key='replacement-intent-01'))
        self.assertEqual(replacement.status_code,201)
        saved=self.facts()
        self.app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client,self.identity=self.login('demo_member_a')
        self.assertEqual(self.cancel().json['data'],result); self.assertEqual(self.facts(),saved)


if __name__=='__main__': unittest.main()

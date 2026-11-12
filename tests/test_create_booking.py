"""Story 2.1 transaction, strict-input and exact-contract acceptance tests."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError
from scripts.init_demo import DEMO_IDENTITIES, seed_users
from tests.schedule_fixtures import NOW, epoch, insert_record, assert_slot_integrity

ORIGIN = 'http://127.0.0.1:8000'
PASSWORD = 'Synthetic-create-passphrase'
FULL_KEYS = {'id','room','title','purpose','attendees','owner_id','owner_display_name','start_at','start_local',
             'end_at','end_local','status','created_at','created_local','cancelled_at','cancelled_local',
             'cancelled_by_id','cancelled_by_display_name','cancel_reason'}
SHARED_CONFLICT_KEYS = {'type','room_id','start_at','start_local','end_at','end_local','status'}
SNAPSHOT_KEYS = {'id','room_id','owner_id','title','purpose','attendees','start_at','end_at','created_at',
                 'cancelled_at','cancelled_by_id','cancel_reason'}

class FixedClock:
    def __init__(self): self.now, self.calls = NOW, 0
    def now_epoch(self):
        self.calls += 1
        return self.now

class CreateBookingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.fixture_db = Path(cls.fixture.name) / 'fixture.sqlite3'
        seed_users(cls.fixture_db, [dict(username=u,display_name=d,role=r,password=PASSWORD)
                                  for u,d,r in DEMO_IDENTITIES], FixedClock())
        with db.write_transaction(cls.fixture_db) as conn:
            conn.executemany('INSERT INTO rooms VALUES(?,?,?,?,?,?)',
                             [(1,'合成甲','101',10,NOW,NOW),(2,'合成乙','102',20,NOW,NOW)])
    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / 'test.sqlite3'
        source, destination = db.connect(self.fixture_db), db.connect(self.database)
        source.backup(destination); source.close(); destination.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client = self.app.test_client()
        self.identity = self.login(self.client)
        self.addCleanup(assert_slot_integrity, self, self.database)

    def login(self, client, username='demo_member_a'):
        page = client.get('/login',base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
        response = client.post('/api/login',base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},
                               json={'username':username,'password':PASSWORD})
        self.assertEqual(response.status_code,200,response.text)
        return response.json['data']

    def payload(self, **changes):
        return dict(room_id=1,title='  合成讨论 🧪  ',purpose='  <script>普通用途</script>  ',attendees=10,
                    start='2026-11-12T12:00',end='2026-11-12T14:00',intent_key='test-intent-key-0001') | changes

    def post(self, data=None, **changes):
        return self.client.post('/api/bookings',base_url=ORIGIN,
            headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']},
            json=self.payload(**changes) if data is None else data)

    def counts(self):
        with db.read_transaction(self.database) as conn:
            return tuple(conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                         for t in ('reservations','occupancy_slots','audit_events'))

    def error(self, response, status, code, field=None):
        self.assertEqual(response.status_code,status,response.text)
        self.assertEqual(set(response.json),{'ok','error'})
        self.assertIs(response.json['ok'],False)
        self.assertEqual(set(response.json['error']),{'code','message','fields','conflicts'})
        self.assertEqual(response.json['error']['code'],code)
        if field: self.assertIn(field,response.json['error']['fields'])
        self.assertNotIn('Set-Cookie',response.headers)

    def actor(self):
        return auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value)

    def test_exact_creation_dto_slots_normalized_payload_and_audit(self):
        calls = []
        def writer(conn,event):
            self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT count(*) FROM reservations').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots').fetchone()[0],4)
            calls.append(event)
            audit_writer(conn,event)
        self.app.config['AUDIT_WRITER'] = writer
        response = self.post()
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(set(response.json),{'ok','data'})
        result = response.json['data']
        self.assertEqual(set(result),{'booking','replayed'}); self.assertIs(result['replayed'],False)
        b = result['booking']; self.assertEqual(set(b),FULL_KEYS)
        self.assertEqual(b['room'],{'id':1,'name':'合成甲','location':'101','capacity':10})
        self.assertEqual(b['title'],'合成讨论 🧪'); self.assertEqual(b['purpose'],'<script>普通用途</script>')
        self.assertEqual(b['owner_id'],self.identity['id']); self.assertEqual(b['owner_display_name'],self.identity['display_name'])
        self.assertEqual(b['status'],'pending'); self.assertEqual(b['created_at'],NOW)
        self.assertEqual(b['start_at'],epoch('2026-11-12T12:00'))
        self.assertEqual(b['start_local'],'2026-11-12T12:00:00+08:00')
        self.assertEqual(b['end_local'],'2026-11-12T14:00:00+08:00')
        self.assertEqual(b['created_local'],'2026-11-12T10:00:00+08:00')
        for key in ('cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason'):
            self.assertIsNone(b[key])
        self.assertEqual(self.counts(),(1,4,1)); self.assertEqual(len(calls),1)
        event = calls[0]
        self.assertEqual(set(event),{'actor_id','actor_display_name','action','target_type','target_id','occurred_at','before','after','reason'})
        self.assertEqual(set(event['after']),SNAPSHOT_KEYS)
        self.assertIsNone(event['before']); self.assertIsNone(event['reason'])
        self.assertEqual((event['action'],event['target_type'],event['target_id']),('booking.created','booking',b['id']))
        with db.read_transaction(self.database) as conn:
            saved = conn.execute('SELECT request_payload FROM reservations').fetchone()[0]
            expected = dict(room_id=1,title=b['title'],purpose=b['purpose'],attendees=10,start_at=b['start_at'],end_at=b['end_at'])
            self.assertEqual(saved,json.dumps(expected,sort_keys=True,ensure_ascii=False,separators=(',',':')))
            audit = conn.execute('SELECT * FROM audit_events').fetchone()
            self.assertEqual(json.loads(audit['after_json']),event['after'])
            self.assertIsNone(audit['before_json'])
        shared = self.client.get('/api/schedule',base_url=ORIGIN,query_string={'room_id':1,'date':'2026-11-12'}).json
        self.assertNotIn('purpose',shared['data']['items'][0]['record'])
        self.assertNotIn('attendees',shared['data']['items'][0]['record'])

    def test_text_integer_and_intent_validation_no_mutation(self):
        invalid = {'title':['',' \t\n','x'*81,'x\x00','\ud800',None,1],
                   'purpose':['','\u3000','x'*501,'\udfff','x\x00',False],
                   'room_id':[True,False,1.0,'1',0,-1,2**63,'9'*6000,None],
                   'attendees':[True,False,1.0,'2',0,-1,None,[],{}],
                   'intent_key':['short','x'*81,'with space in key','非ASCII'*10,None]}
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field,value=repr(value)[:30]):
                    self.error(self.post(**{field:value}),400,'INVALID_INPUT',field)
                    self.assertEqual(self.counts(),(0,0,0))
        for field in self.payload():
            value=self.payload(); del value[field]
            self.error(self.post(value),400,'INVALID_INPUT',field)
        self.assertEqual(self.post(title='🧪'*80,purpose='中'*500).status_code,201)

    def test_window_edges_and_formats(self):
        cases = [('2026-11-12T10:00','2026-11-12T10:30','start'),
                 ('2026-11-12T09:30','2026-11-12T10:00','start'),
                 ('2026-11-12T12:00','2026-11-12T12:00','end'),
                 ('2026-11-12T12:00','2026-11-12T11:30','end'),
                 ('2026-11-12T12:00','2026-11-12T16:30','end'),
                 ('2026-12-12T10:00','2026-12-12T10:30','end'),
                 ('2026-11-12T23:30','2026-11-13T00:00','end')]
        for start,end,field in cases:
            self.error(self.post(start=start,end=end),400,'INVALID_INPUT',field)
        for value in ['2026-11-12T12:15','2026-2-01T12:00','2026-02-29T12:00','2026-11-12T12:00:00',
                      '2026-11-12T12:00+08:00','2026-11-12 12:00','0001-01-01T00:00','9999-12-31T23:30',None,True]:
            self.error(self.post(start=value),400,'INVALID_INPUT')
        self.assertEqual(self.counts(),(0,0,0))
        for i,(start,end) in enumerate([('2026-11-12T12:00','2026-11-12T12:30'),
                                       ('2026-11-12T13:00','2026-11-12T17:00'),
                                       ('2026-12-12T09:30','2026-12-12T10:00')]):
            self.assertEqual(self.post(start=start,end=end,intent_key=f'valid-boundary-{i:03}').status_code,201)

    def test_missing_room_capacity_and_huge_counts_do_not_bind_or_serialize(self):
        self.error(self.post(room_id=2**63-1),404,'NOT_FOUND')
        for value in [11,2**63,10**100]:
            self.error(self.post(attendees=value),409,'CAPACITY_CONFLICT')
        with self.app.app_context():
            with self.assertRaises(DomainError) as caught:
                services.create_booking(self.actor(),self.payload(attendees=10**10000))
            self.assertEqual(caught.exception.code,'CAPACITY_CONFLICT')
        self.assertEqual(self.counts(),(0,0,0))

    def test_booking_and_block_overlap_privacy_adjacency_and_other_room(self):
        with db.write_transaction(self.database) as conn:
            insert_record(conn,100,1,'2026-11-12T12:00','2026-11-12T13:00')
            insert_record(conn,101,1,'2026-11-12T14:00','2026-11-12T15:00',kind='block')
        for start,end,kind in [('2026-11-12T11:30','2026-11-12T12:30','booking'),
                               ('2026-11-12T14:30','2026-11-12T15:30','block')]:
            response=self.post(start=start,end=end)
            self.error(response,409,'OCCUPANCY_CONFLICT')
            self.assertEqual(set(response.json['error']['conflicts'][0]),SHARED_CONFLICT_KEYS)
            self.assertEqual(response.json['error']['conflicts'][0]['type'],kind)
        self.assertEqual(self.post(start='2026-11-12T13:00',end='2026-11-12T14:00').status_code,201)
        self.assertEqual(self.post(room_id=2,intent_key='different-room-key').status_code,201)
        self.client=self.app.test_client()
        self.identity=self.login(self.client,'demo_admin')
        response=self.post(start='2026-11-12T14:00',end='2026-11-12T15:00')
        conflict=response.json['error']['conflicts'][0]
        self.assertEqual(set(conflict),SHARED_CONFLICT_KEYS|{'id','attendees','reason'})
        self.assertIsNone(conflict['attendees']); self.assertIsInstance(conflict['reason'],str)
        response=self.post(start='2026-11-12T12:00',end='2026-11-12T13:00')
        self.assertIsNone(response.json['error']['conflicts'][0]['reason'])

    def test_duplicate_key_is_controlled_409_and_user_scoped(self):
        self.assertEqual(self.post().status_code,201)
        self.assertEqual(self.post().status_code,200)
        self.error(self.post(title='不同活动'),409,'IDEMPOTENCY_MISMATCH')
        self.client=self.app.test_client()
        self.identity=self.login(self.client,'demo_member_b')
        self.assertEqual(self.post(room_id=2).status_code,201)
        self.assertEqual(self.counts(),(2,8,2))

    def test_authorization_csrf_origin_content_type_first(self):
        anonymous=self.app.test_client()
        self.error(anonymous.post('/api/bookings',base_url=ORIGIN,headers={'Origin':ORIGIN},json={}),401,'AUTH_REQUIRED')
        for headers in [{},{'Origin':'http://evil.example'},{'Origin':ORIGIN},{'Origin':ORIGIN,'X-CSRF-Token':'bad'}]:
            self.error(self.client.post('/api/bookings',base_url=ORIGIN,headers=headers,json={}),403,'CSRF_REJECTED')
        for body in [[],None,'text']:
            response=self.client.post('/api/bookings',base_url=ORIGIN,
                headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token'],'Content-Type':'application/json'},data=json.dumps(body))
            self.error(response,400,'INVALID_INPUT')
        self.error(self.client.post('/api/bookings',base_url=ORIGIN,
            headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']},data={}),400,'INVALID_INPUT')
        self.clock.now=NOW+auth.SESSION_SECONDS
        self.error(self.post(room_id='bad'),401,'AUTH_REQUIRED')
        self.assertEqual(self.counts(),(0,0,0))

    def test_service_refreshes_identity_and_one_clock_after_lock(self):
        with self.app.app_context():
            actor=self.actor()
            with db.write_transaction(self.database) as conn:
                conn.execute("UPDATE users SET display_name='新名字',role='member' WHERE id=?",(actor.id,))
            self.clock.calls=0
            result=services.create_booking(replace(actor,display_name='过期名字',role='admin'),self.payload())
            self.assertEqual(self.clock.calls,1)
            self.assertEqual(result['booking']['owner_display_name'],'新名字')
            for bad in (None,replace(actor,id=2),replace(actor,session_token_hash='0'*64)):
                with self.assertRaises(DomainError) as caught: services.create_booking(bad,{})
                self.assertEqual(caught.exception.code,'AUTH_REQUIRED')
            with db.read_transaction(self.database) as conn:
                self.assertEqual(conn.execute('SELECT actor_display_name FROM audit_events').fetchone()[0],'新名字')
            with db.write_transaction(self.database) as conn: conn.execute('DELETE FROM sessions')
            with self.assertRaises(DomainError) as caught: services.create_booking(actor,{})
            self.assertEqual(caught.exception.code,'AUTH_REQUIRED')

    def test_session_expiry_and_start_boundary_are_rechecked_after_lock(self):
        real_transaction=db.write_transaction
        for locked_now,status,code,field in [
            (NOW+auth.SESSION_SECONDS,401,'AUTH_REQUIRED',None),
            (epoch('2026-11-12T12:00'),400,'INVALID_INPUT','start'),
        ]:
            with self.subTest(locked_now=locked_now):
                self.clock.now=NOW
                with db.read_transaction(self.database) as conn:
                    before={table:[tuple(row) for row in conn.execute(f'SELECT * FROM {table}')]
                            for table in ('reservations','occupancy_slots','audit_events')}
                @contextmanager
                def advance_after_lock(database=None):
                    with real_transaction(database) as conn:
                        self.clock.now=locked_now
                        yield conn
                with patch.object(db,'write_transaction',advance_after_lock):
                    self.error(self.post(),status,code,field)
                with db.read_transaction(self.database) as conn:
                    after={table:[tuple(row) for row in conn.execute(f'SELECT * FROM {table}')]
                           for table in before}
                self.assertEqual(after,before)
        self.clock.now=NOW

    def test_real_member_with_stale_admin_actor_gets_only_shared_conflict(self):
        with db.write_transaction(self.database) as conn:
            insert_record(conn,100,1,'2026-11-12T12:00','2026-11-12T14:00')
        before=self.counts()
        with self.app.app_context():
            actor=self.actor()
            self.assertEqual(actor.role,'member')
            with self.assertRaises(DomainError) as caught:
                services.create_booking(replace(actor,role='admin'),self.payload())
            self.assertEqual(caught.exception.code,'OCCUPANCY_CONFLICT')
            self.assertEqual(len(caught.exception.conflicts),1)
            self.assertEqual(set(caught.exception.conflicts[0]),SHARED_CONFLICT_KEYS)
        self.assertEqual(self.counts(),before)

    def test_cancelled_booking_and_revoked_block_release_slots_without_changing_history(self):
        with db.write_transaction(self.database) as conn:
            insert_record(conn,100,1,'2026-11-12T12:00','2026-11-12T14:00',cancelled=True)
            insert_record(conn,101,2,'2026-11-12T12:00','2026-11-12T14:00',kind='block',cancelled=True)
        with db.read_transaction(self.database) as conn:
            before=[dict(row) for row in conn.execute('SELECT * FROM reservations ORDER BY id')]
        for room_id,old_id in [(1,100),(2,101)]:
            with self.subTest(room_id=room_id):
                response=self.post(room_id=room_id,intent_key=f'cancelled-slot-reuse-{room_id}')
                self.assertEqual(response.status_code,201,response.text)
                booking=response.json['data']['booking']
                with db.read_transaction(self.database) as conn:
                    self.assertEqual([dict(row) for row in conn.execute('SELECT * FROM reservations WHERE id IN (100,101) ORDER BY id')],before)
                    self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=?',(old_id,)).fetchone()[0],0)
                    slots=[tuple(row) for row in conn.execute('SELECT room_id,slot_start FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start',(booking['id'],))]
                    self.assertEqual(slots,[(room_id,t) for t in range(booking['start_at'],booking['end_at'],1800)])
                    audit=conn.execute('SELECT * FROM audit_events WHERE target_id=?',(booking['id'],)).fetchall()
                    self.assertEqual(len(audit),1)
                    self.assertEqual(audit[0]['action'],'booking.created')
                    self.assertEqual(json.loads(audit[0]['after_json'])['id'],booking['id'])
        self.assertEqual(self.counts(),(4,8,2))

    def test_audit_failure_before_and_after_insert_rolls_back_and_key_reusable(self):
        for after_insert in (False,True):
            def fail(conn,event):
                if after_insert: audit_writer(conn,event)
                raise RuntimeError('sensitive fault text SQL credentials')
            self.app.config['AUDIT_WRITER']=fail
            with self.assertLogs(self.app.logger,level='ERROR') as logs:
                response=self.post()
            self.error(response,500,'INTERNAL_ERROR')
            self.assertNotIn('sensitive',response.text+str(logs.output))
            self.assertEqual(self.counts(),(0,0,0))
        self.app.config['AUDIT_WRITER']=audit_writer
        self.assertEqual(self.post().status_code,201)

    def test_commit_failure_and_unrelated_integrity_error_are_safe_500(self):
        original=db.write_transaction
        connect=db.connect
        class FailCommit:
            def __init__(self,conn): self.conn=conn
            def __getattr__(self,name): return getattr(self.conn,name)
            def execute(self,sql,*args):
                if sql == 'COMMIT': raise sqlite3.OperationalError('injected COMMIT failure')
                return self.conn.execute(sql,*args)
        with patch.object(db,'connect',lambda *a,**kw:FailCommit(connect(*a,**kw))),self.assertLogs(self.app.logger,level='ERROR'):
            self.error(self.post(),500,'INTERNAL_ERROR')
        self.assertEqual(self.counts(),(0,0,0))
        with original(self.database) as conn:
            conn.execute("CREATE TRIGGER reject_booking BEFORE INSERT ON reservations BEGIN SELECT RAISE(ABORT,'private trigger failure'); END")
        with self.assertLogs(self.app.logger,level='ERROR'):
            self.error(self.post(),500,'INTERNAL_ERROR')
        self.assertEqual(self.counts(),(0,0,0))

    def test_slot_constraint_collision_rolls_back_every_part_of_creation(self):
        connect=db.connect
        class DuplicateSecondSlot:
            def __init__(self,conn): self.conn=conn
            def __getattr__(self,name): return getattr(self.conn,name)
            def executemany(self,sql,rows):
                rows=list(rows)
                self.conn.execute(sql,rows[0])
                self.conn.execute(sql,rows[0])
        with patch.object(db,'connect',lambda *a,**kw:DuplicateSecondSlot(connect(*a,**kw))):
            self.error(self.post(),409,'OCCUPANCY_CONFLICT')
        self.assertEqual(self.counts(),(0,0,0))
        self.assertEqual(self.post().status_code,201)

    def test_legacy_v1_initialization_preserves_history_and_requires_audit_columns(self):
        self.assertEqual(self.post().status_code,201)
        with db.read_transaction(self.database) as conn: before=list(conn.iterdump())
        db.initialize_database(self.database)
        with db.read_transaction(self.database) as conn:
            self.assertEqual(list(conn.iterdump()),before)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
        with db.write_transaction(self.database) as conn:
            conn.execute('DROP TABLE audit_events')
        with self.assertRaises(RuntimeError): db.check_database(self.database)
        db.initialize_database(self.database)
        self.assertEqual(self.counts(),(1,4,0))

if __name__ == '__main__': unittest.main()

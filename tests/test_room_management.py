"""Story 3.1 independent authorization, capacity and atomicity acceptance cases."""
from contextlib import contextmanager
from dataclasses import replace
import json
import html
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError
from scripts.init_demo import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import FixedClock, seed_history_fixture
from tests.schedule_fixtures import NOW, assert_slot_integrity

ORIGIN = 'http://127.0.0.1:8000'
ROOM_KEYS = {'id', 'name', 'location', 'capacity'}
CONFLICT_KEYS = {'id','type','room_id','start_at','start_local','end_at','end_local','status','attendees','reason'}


class RoomManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.fixture = Path(cls.directory.name)/'fixture.sqlite3'
        cls.password = secrets.token_urlsafe(24)
        seed_users(cls.fixture, [dict(username=u,display_name=d,role=r,password=cls.password)
                               for u,d,r in DEMO_IDENTITIES], FixedClock())
        seed_history_fixture(cls.fixture)

    @classmethod
    def tearDownClass(cls): cls.directory.cleanup()

    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.database = Path(directory.name)/'test.sqlite3'
        source, target = db.connect(self.fixture), db.connect(self.database)
        source.backup(target); source.close(); target.close()
        self.clock = FixedClock()
        self.app = create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client, self.identity = self.login('demo_admin')
        self.addCleanup(assert_slot_integrity,self,self.database)

    def login(self, username):
        client = self.app.test_client(); page = client.get('/login',base_url=ORIGIN)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
        response = client.post('/api/login',base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},
                               json=dict(username=username,password=self.password))
        self.assertEqual(response.status_code,200)
        return client,response.json['data']

    def post(self, values=None, room_id=None, client=None, identity=None):
        return (client or self.client).post('/api/admin/rooms'+('' if room_id is None else f'/{room_id}'),
            base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':(identity or self.identity)['csrf_token']},
            json=values if values is not None else dict(name='新会议室',location='测试楼',capacity=20))

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('rooms','reservations','occupancy_slots','audit_events')}

    def error(self,response,status,code):
        self.assertEqual(response.status_code,status,response.text)
        self.assertEqual(set(response.json),{'ok','error'})
        self.assertEqual(set(response.json['error']),{'code','message','fields','conflicts'})
        self.assertFalse(response.json['ok']); self.assertEqual(response.json['error']['code'],code)
        return response.json['error']

    def actor(self):
        return auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value)

    def test_create_update_stable_id_exact_dto_and_snapshots(self):
        observed=[]; connections=[]; real_transaction=db.write_transaction
        @contextmanager
        def tracked(database=None):
            with real_transaction(database) as conn:
                connections.append(conn)
                try: yield conn
                finally: connections.pop()
        self.enterContext(patch.object(db,'write_transaction',tracked))
        def writer(conn,event):
            self.assertIs(conn,connections[-1])
            self.assertTrue(conn.in_transaction)
            row=conn.execute('SELECT * FROM rooms WHERE id=?',(event['target_id'],)).fetchone()
            self.assertEqual({key:row[key] for key in ROOM_KEYS},event['after'])
            observed.append(event); audit_writer(conn,event)
        self.app.config['AUDIT_WRITER']=writer
        response=self.post(dict(name='  <img src=x> 🧪  ',location=' \u0085楼 101\u0085 ',capacity=1000))
        self.assertEqual(response.status_code,201); original=response.json['data']; self.assertEqual(set(original),ROOM_KEYS)
        self.assertEqual(original['name'],'<img src=x> 🧪'); self.assertEqual(original['location'],'楼 101')
        self.assertEqual(observed[0]['before'],None); self.assertEqual(observed[0]['after'],original)
        changed=dict(name='改名',location='改地点',capacity=1)
        response=self.post(changed,original['id']); self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,dict(ok=True,data=dict(id=original['id'],**changed)))
        self.assertEqual(len(observed),2); self.assertEqual(observed[1]['before'],original)
        for event in observed:
            self.assertEqual(event['reason'],None); self.assertEqual(event['occurred_at'],NOW)
            self.assertEqual(set(event['after']),ROOM_KEYS); self.assertEqual(event['actor_display_name'],'演示管理员')
        self.assertEqual([e['action'] for e in observed],['room.created','room.updated'])

    def test_no_change_normalization_does_not_write_timestamp_or_audit(self):
        original=self.facts()['rooms'][0]; before=self.facts()
        self.clock.now+=1
        self.app.config['AUDIT_WRITER']=lambda *_:self.fail('No-change must not call writer')
        response=self.post(dict(name=' '+original['name']+' ',location=' '+original['location']+' ',capacity=original['capacity']),1)
        self.assertEqual(response.status_code,200); self.assertEqual(set(response.json['data']),ROOM_KEYS)
        self.assertEqual(self.facts(),before)

    def assert_multiline_round_trip(self, newline):
        values=dict(name='上'+newline+'下',location='东'+newline+'西',capacity=20)
        created=self.post(values);self.assertEqual(created.status_code,201)
        room_id=created.json['data']['id'];before=self.facts()
        page=self.client.get('/admin',base_url=ORIGIN)
        embedded=[json.loads(html.unescape(value)) for value in re.findall(r'data-room="([^"]*)"',page.text)]
        self.assertIn(dict(id=room_id,**values),embedded)
        self.assertEqual(self.post(values,room_id).status_code,200);self.assertEqual(self.facts(),before)
        response=self.post(values|dict(capacity=21),room_id);self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['data'],dict(id=room_id,**(values|dict(capacity=21))))
        event=self.facts()['audit_events'][-1]
        self.assertEqual(json.loads(event['before_json']),dict(id=room_id,**values))
        self.assertEqual(json.loads(event['after_json']),response.json['data'])

    def test_lf_multiline_text_round_trip(self): self.assert_multiline_round_trip('\n')

    def test_cr_multiline_text_round_trip(self): self.assert_multiline_round_trip('\r')

    def test_crlf_multiline_text_round_trip(self): self.assert_multiline_round_trip('\r\n')

    def test_real_write_lock_create_and_update_timeout_then_deliberate_retry(self):
        real_connect=db.connect
        def fast_connect(database):
            conn=real_connect(database);conn.execute('PRAGMA busy_timeout=10');return conn
        for room_id,values,expected in ((None,dict(name='等待新增',location='新楼',capacity=20),201),
                                       (1,dict(name='等待修改',location='旧楼',capacity=20),200)):
            with self.subTest(room_id=room_id):
                before=self.facts();blocker=real_connect(self.database)
                try:
                    blocker.execute('BEGIN IMMEDIATE')
                    with patch.object(db,'connect',side_effect=fast_connect):
                        response=self.post(values,room_id)
                    error=self.error(response,503,'STORE_BUSY')
                    self.assertEqual(error['fields'],{});self.assertEqual(error['conflicts'],[])
                    self.assertNotRegex(response.text,r'SELECT|INSERT|UPDATE|sqlite|Traceback')
                    self.assertEqual(self.facts(),before)
                finally:
                    blocker.execute('ROLLBACK');blocker.close()
                self.assertEqual(self.post(values,room_id).status_code,expected)
                self.assertEqual(len(self.facts()['audit_events']),len(before['audit_events'])+1)

    def test_invalid_complete_fields_strict_types_bounds_utf8_and_rollback(self):
        valid=dict(name='合法',location='地点',capacity=10); before=self.facts()
        bad=[{}, {'name':'partial'}, *[valid|{'capacity':v} for v in (True,False,1.0,'10',0,-1,1001,10**100,None)],
             *[valid|{key:value} for key,limit in [('name',80),('location',120)]
               for value in ('',' \u0085 ', 'x'*(limit+1),'x\x00y','x\ud800',None,7)]]
        for value in bad:
            for room_id in (None,1):
                with self.subTest(value=repr(value),room_id=room_id):
                    self.error(self.post(value,room_id),400,'INVALID_INPUT');self.assertEqual(self.facts(),before)
        response=self.post(dict(name='🧪'*80,location='🧪'*120,capacity=1000));self.assertEqual(response.status_code,201)

    def test_duplicate_combination_409_complete_rollback_case_sensitive(self):
        first=self.post().json['data']; before=self.facts()
        for room_id in (None,1):
            self.error(self.post(dict(name=' 新会议室 ',location=' 测试楼 ',capacity=1),room_id),409,'ROOM_DUPLICATE')
            self.assertEqual(self.facts(),before)
        self.assertEqual(self.post(dict(name=first['name'],location='另一个地点',capacity=20)).status_code,201)
        for name in ('Room','room','é','e\u0301'):
            self.assertEqual(self.post(dict(name=name,location='同地',capacity=1)).status_code,201)

    def test_capacity_protects_pending_and_in_progress_and_equal_succeeds(self):
        before=self.facts()
        error=self.error(self.post(dict(name='不得部分改名',location='不得部分保存',capacity=4),1),409,'CAPACITY_CONFLICT')
        self.assertEqual(self.facts(),before); self.assertEqual([c['id'] for c in error['conflicts']],[102,103])
        self.assertEqual([c['status'] for c in error['conflicts']],['in_progress','pending'])
        for row in error['conflicts']:
            self.assertEqual(set(row),CONFLICT_KEYS); self.assertEqual(row['attendees'],5);self.assertIsNone(row['reason'])
        response=self.post(dict(name='等于人数',location='新地点',capacity=5),1)
        self.assertEqual(response.status_code,200); after=self.facts()
        for table in ('reservations','occupancy_slots'):self.assertEqual(after[table],before[table])
        self.assertEqual(len(after['audit_events']),1)

    def test_ended_cancelled_and_block_do_not_prevent_lowering(self):
        # At the exact final active booking end, historical slots remain but do not prevent lowering.
        with db.write_transaction(self.database) as conn:
            conn.execute("INSERT INTO rooms VALUES(4,'仅停用','4',30,?,?)",(NOW,NOW))
            conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,reason,start_at,end_at,created_at) "
                         "VALUES(402,'block',4,3,'未来维护',?,?,?)",(NOW+1800,NOW+3600,NOW))
            conn.execute('INSERT INTO occupancy_slots VALUES(4,?,402)',(NOW+1800,))
        self.assertEqual(self.post(dict(name='仅停用',location='4',capacity=1),4).status_code,200)
        self.clock.now=NOW+3*3600
        response=self.post(dict(name='历史仍保留',location='1',capacity=1),1)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.post(dict(name='停用不按人数',location='3',capacity=1),3).status_code,200)
        self.assertEqual(len(self.facts()['reservations']),10)

    def test_authorization_html_api_nav_and_ids_before_validation(self):
        before=self.facts(); member,identity=self.login('demo_member_a'); anonymous=self.app.test_client()
        for room_id in (None,1,'9'*5000):
            self.error(self.post({},room_id,member,identity),403,'FORBIDDEN')
            response=anonymous.post('/api/admin/rooms'+('' if room_id is None else f'/{room_id}'),base_url=ORIGIN,headers={'Origin':ORIGIN},json={})
            self.error(response,401,'AUTH_REQUIRED')
        self.assertEqual(member.get('/admin',base_url=ORIGIN).status_code,403)
        self.assertEqual(anonymous.get('/admin',base_url=ORIGIN).status_code,302)
        self.assertNotIn('href="/admin"',member.get('/',base_url=ORIGIN).text)
        page=self.client.get('/admin',base_url=ORIGIN);self.assertEqual(page.status_code,200)
        for text in ['href="/admin"','id="room-form"','for="room-name"','for="room-location"','for="room-capacity"','id="room-confirm"']:
            self.assertIn(text,page.text)
        for value in ('0','01','-1','1.0','abc',str(2**63),'9'*5000):self.error(self.post(room_id=value),400,'INVALID_INPUT')
        self.error(self.post(room_id=2**63-1),404,'NOT_FOUND')
        self.assertNotEqual(self.client.delete('/api/admin/rooms/1',base_url=ORIGIN).status_code,200)
        self.assertEqual(self.facts(),before)

    def test_origin_csrf_content_type_logout_and_expired_rejections(self):
        before=self.facts()
        for headers in ({},{'Origin':'http://evil.test'},{'Origin':ORIGIN},{'Origin':ORIGIN,'X-CSRF-Token':'bad'}):
            self.error(self.client.post('/api/admin/rooms',base_url=ORIGIN,headers=headers,json={}),403,'CSRF_REJECTED')
        headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']}
        self.error(self.client.post('/api/admin/rooms',base_url=ORIGIN,headers=headers,data={}),400,'INVALID_INPUT')
        self.error(self.client.post('/api/admin/rooms',base_url=ORIGIN,headers=headers,json=[]),400,'INVALID_INPUT')
        old=self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value
        self.assertEqual(self.client.post('/api/logout',base_url=ORIGIN,headers=headers,json={}).status_code,200)
        self.client.set_cookie(auth.COOKIE_NAME,old,domain='127.0.0.1')
        self.error(self.post(),401,'AUTH_REQUIRED')
        self.client,self.identity=self.login('demo_admin');self.clock.now=NOW+auth.SESSION_SECONDS
        self.error(self.post(room_id='bad'),401,'AUTH_REQUIRED');self.assertEqual(self.facts(),before)

    def test_service_reloads_role_actor_and_one_clock_after_write_lock(self):
        with self.app.app_context():
            actor=self.actor(); self.clock.calls=0
            services.create_room(replace(actor,display_name='stale'),dict(name='新',location='地',capacity=10))
            self.assertEqual(self.clock.calls,1)
            self.assertEqual(self.facts()['audit_events'][0]['actor_display_name'],'演示管理员')
            for bad in (None,replace(actor,id=1),replace(actor,session_token_hash='0'*64)):
                with self.assertRaises(DomainError) as found:services.create_room(bad,{})
                self.assertEqual(found.exception.code,'AUTH_REQUIRED')
            with db.write_transaction(self.database) as conn:conn.execute("UPDATE users SET role='member' WHERE id=?",(actor.id,))
            for command,args in ((services.create_room,({},)),(services.update_room,('bad',{}))):
                with self.assertRaises(DomainError) as found:command(actor,*args)
                self.assertEqual(found.exception.code,'FORBIDDEN')

    def test_expiration_rechecked_after_lock_before_fields_or_changes(self):
        original=db.write_transaction;before=self.facts()
        @contextmanager
        def advance(database=None):
            with original(database) as conn:
                self.clock.now=NOW+auth.SESSION_SECONDS;yield conn
        with patch.object(db,'write_transaction',advance):self.error(self.post(),401,'AUTH_REQUIRED')
        self.assertEqual(self.facts(),before)

    def test_audit_failure_before_after_insert_and_commit_roll_back_every_table(self):
        before=self.facts()
        for after_insert in (False,True):
            def fail(conn,event):
                if after_insert:audit_writer(conn,event)
                raise RuntimeError('private SQL token secret')
            self.app.config['AUDIT_WRITER']=fail
            for room_id in (None,1):
                with self.assertLogs(self.app.logger,level='ERROR') as logs:self.error(self.post(room_id=room_id),500,'INTERNAL_ERROR')
                self.assertNotIn('private',str(logs.output));self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer; connect=db.connect
        class FailCommit:
            def __init__(self,conn):self.conn=conn
            def __getattr__(self,name):return getattr(self.conn,name)
            def execute(self,sql,*args):
                if sql=='COMMIT':raise sqlite3.OperationalError('commit failure')
                return self.conn.execute(sql,*args)
        with patch.object(db,'connect',lambda *a,**k:FailCommit(connect(*a,**k))),self.assertLogs(self.app.logger,level='ERROR'):
            self.error(self.post(),500,'INTERNAL_ERROR')
        self.assertEqual(self.facts(),before)

    def test_old_successful_intent_replays_after_cancel_and_capacity_reduction(self):
        member,identity=self.login('demo_member_a');headers={'Origin':ORIGIN,'X-CSRF-Token':identity['csrf_token']}
        payload=dict(room_id=2,title='原预约',purpose='保留',attendees=10,start='2026-11-13T12:00',end='2026-11-13T13:00',intent_key='room-replay-original-intent')
        first=member.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload)
        self.assertEqual(first.status_code,201);booking_id=first.json['data']['booking']['id']
        self.assertEqual(member.post(f'/api/bookings/{booking_id}/cancel',base_url=ORIGIN,headers=headers,json={}).status_code,200)
        self.assertEqual(self.post(dict(name='降容房间',location='2',capacity=5),2).status_code,200)
        before=self.facts();response=member.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json['data']['replayed'])
        self.assertEqual(response.json['data']['booking']['id'],booking_id)
        self.assertEqual(response.json['data']['booking']['room']['capacity'],5)
        self.assertEqual(self.facts(),before)

if __name__=='__main__':unittest.main()

"""Story 3.2 independent acceptance tests; no inherited test cases."""
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
from tests.history_fixtures import FixedClock, FULL_KEYS
from tests.schedule_fixtures import NOW, assert_slot_integrity, seed_schedule_fixture, insert_record

ORIGIN = 'http://127.0.0.1:8000'
BLOCK_KEYS = {'id','room','creator_id','creator_display_name','reason','start_at','start_local','end_at','end_local',
              'status','created_at','created_local','revoked_at','revoked_local','revoked_by_id','revoked_by_display_name','revoke_reason'}
SNAPSHOT_KEYS = {'id','room_id','creator_id','reason','start_at','end_at','created_at','revoked_at','revoked_by_id','revoke_reason'}
CONFLICT_KEYS = {'id','type','room_id','start_at','start_local','end_at','end_local','status','attendees','reason'}

class MaintenanceBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory(); cls.fixture=Path(cls.directory.name)/'fixture.sqlite3'
        cls.password=secrets.token_urlsafe(24)
        seed_users(cls.fixture,[dict(username=u,display_name=d,role=r,password=cls.password) for u,d,r in DEMO_IDENTITIES],FixedClock())
        seed_schedule_fixture(cls.fixture)
        with db.write_transaction(cls.fixture) as conn:
            insert_record(conn,112,30,'2026-11-12T10:00','2026-11-12T11:00',kind='block')
    @classmethod
    def tearDownClass(cls): cls.directory.cleanup()
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.database=Path(temporary.name)/'test.sqlite3'
        source,target=db.connect(self.fixture),db.connect(self.database);source.backup(target);source.close();target.close()
        self.clock=FixedClock();self.app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client,self.identity=self.login('demo_admin');self.addCleanup(assert_slot_integrity,self,self.database)
    def login(self,username):
        client=self.app.test_client();page=client.get('/login',base_url=ORIGIN)
        csrf=re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
        result=client.post('/api/login',base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},json=dict(username=username,password=self.password))
        self.assertEqual(result.status_code,200);return client,result.json['data']
    def payload(self,**changes):
        return dict(room_id=30,start='2026-11-13T10:00',end='2026-11-14T16:00',reason=' 维护设备 ')|changes
    def post(self,values=None,client=None,identity=None):
        return (client or self.client).post('/api/admin/blocks',base_url=ORIGIN,json=self.payload() if values is None else values,
            headers={'Origin':ORIGIN,'X-CSRF-Token':(identity or self.identity)['csrf_token']})
    def get(self,kind='blocks',client=None,**query):
        return (client or self.client).get('/api/admin/'+kind,base_url=ORIGIN,query_string=query)
    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('rooms','reservations','occupancy_slots','audit_events')}
    def error(self,response,status,code):
        self.assertEqual(response.status_code,status,response.text);self.assertEqual(set(response.json),{'ok','error'})
        self.assertEqual(set(response.json['error']),{'code','message','fields','conflicts'})
        self.assertFalse(response.json['ok']);self.assertEqual(response.json['error']['code'],code);return response.json['error']
    def test_long_cross_day_creation_exact_dto_storage_slots_and_single_same_connection_audit(self):
        original=db.write_transaction;connections=[];events=[]
        @contextmanager
        def track(database=None):
            with original(database) as conn:
                connections.append(conn)
                try:yield conn
                finally:connections.pop()
        self.enterContext(patch.object(db,'write_transaction',track))
        def writer(conn,event):
            self.assertIs(conn,connections[-1]);self.assertTrue(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=?',(event['target_id'],)).fetchone()[0],60)
            events.append(event);audit_writer(conn,event)
        self.app.config['AUDIT_WRITER']=writer
        response=self.post(self.payload(reason=' \u0085<img src=x>🧪\u0085 ',user_id=1,kind='booking'))
        self.assertEqual(response.status_code,201);self.assertEqual(set(response.json),{'ok','data'})
        block=response.json['data'];self.assertEqual(set(block),BLOCK_KEYS)
        self.assertEqual(block['reason'],'<img src=x>🧪');self.assertEqual(block['creator_id'],3)
        self.assertEqual(set(block['room']),{'id','name','location','capacity'})
        for key in ('revoked_at','revoked_local','revoked_by_id','revoked_by_display_name','revoke_reason'):self.assertIsNone(block[key])
        self.assertEqual(block['status'],'pending');self.assertEqual(block['created_at'],NOW)
        row=self.facts()['reservations'][-1];self.assertEqual(row['user_id'],3);self.assertEqual(row['kind'],'block')
        for key in ('title','purpose','attendees','intent_key','request_payload'):self.assertIsNone(row[key])
        self.assertEqual(len(events),1);event=events[0]
        self.assertEqual((event['action'],event['target_type'],event['target_id'],event['occurred_at']),('block.created','block',block['id'],NOW))
        self.assertIsNone(event['before']);self.assertEqual(event['reason'],block['reason']);self.assertEqual(set(event['after']),SNAPSHOT_KEYS)
        self.assertEqual(event['actor_display_name'],'演示管理员')
    def test_half_hour_and_exact_30_day_boundary_allowed(self):
        for start,end in [(NOW+3600,NOW+5400),(NOW+30*86400-1800,NOW+30*86400)]:
            result=self.post(self.payload(room_id=20,start=local_time(start)[:16],end=local_time(end)[:16],reason='🧪'*500))
            self.assertEqual(result.status_code,201,result.text)
    def test_invalid_fields_strict_id_reason_time_and_window_leave_no_facts(self):
        before=self.facts();bad=[{},[],*[self.payload(room_id=v) for v in (True,1.0,'30',0,-1,2**63,None,'9'*5000)],
            *[self.payload(reason=v) for v in ('',' \u0085 ','x'*501,'x\x00y','x\ud800',None,True)],
            *[self.payload(**{key:value}) for key in ('start','end') for value in ('2026-11-13T10:01','2026-11-13T10:00:00','2026-11-13T10:00+08:00','2026-02-30T10:00','26-11-13T10:00',None)],
            self.payload(start='2026-11-12T10:00'),self.payload(start='2026-11-12T09:30'),
            self.payload(end='2026-11-13T10:00'),self.payload(end='2026-11-13T09:30'),
            self.payload(end=local_time(NOW+30*86400+1800)[:16]),self.payload(start='0001-01-01T00:00')]
        for payload in bad:
            with self.subTest(payload=repr(payload)):
                self.error(self.post(payload),400,'INVALID_INPUT');self.assertEqual(self.facts(),before)
        self.error(self.post(self.payload(room_id=2**63-1)),404,'NOT_FOUND')
    def test_overlap_booking_block_409_unchanged_and_adjacent_allowed(self):
        before=self.facts()
        for room,start,end,kind in [(10,'2026-11-12T11:00','2026-11-12T12:00','booking'),(10,'2026-11-12T22:30','2026-11-13T00:00','block')]:
            conflict=self.error(self.post(self.payload(room_id=room,start=start,end=end)),409,'OCCUPANCY_CONFLICT')['conflicts'][0]
            self.assertEqual(set(conflict),CONFLICT_KEYS);self.assertEqual(conflict['type'],kind);self.assertEqual(self.facts(),before)
            self.assertIsNone(conflict['reason'] if kind=='booking' else conflict['attendees'])
        response=self.post(self.payload(room_id=10,start='2026-11-12T11:30',end='2026-11-12T12:00'))
        self.assertEqual(response.status_code,201);self.assertEqual(self.facts()['reservations'][:-1],before['reservations'])
    def test_booking_against_created_block_rejected_and_adjacent_allowed(self):
        # 本用例验证导师直订；其余用例仍保留真实学生角色。
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET role='teacher' WHERE id=1")
        created=self.post(self.payload(start='2026-11-13T10:00',end='2026-11-13T15:00')).json['data']
        member,identity=self.login('demo_member_a');headers={'Origin':ORIGIN,'X-CSRF-Token':identity['csrf_token']}
        payload=dict(room_id=30,start='2026-11-13T14:30',end='2026-11-13T15:30',title='测试',purpose='私密',attendees=5,intent_key='block-overlap-booking')
        before=self.facts();response=member.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload)
        conflict=self.error(response,409,'OCCUPANCY_CONFLICT')['conflicts'][0]
        self.assertEqual(conflict['type'],'block');self.assertNotIn('reason',conflict);self.assertEqual(self.facts(),before)
        self.assertEqual(member.post('/api/bookings',base_url=ORIGIN,headers=headers,json=payload|dict(start='2026-11-13T15:00')).status_code,201)
        self.assertEqual(created['creator_id'],3)
    def test_admin_lists_exact_full_fields_ascending_room_date_and_four_states(self):
        before=self.facts()
        for kind,keys,terminal in [('bookings',FULL_KEYS,'cancelled'),('blocks',BLOCK_KEYS,'revoked')]:
            all_items=self.get(kind).json['data'];self.assertEqual(set(all_items),{'items','total'})
            items=all_items['items'];self.assertEqual(all_items['total'],len(items));self.assertEqual([(r['start_at'],r['id']) for r in items],sorted((r['start_at'],r['id']) for r in items))
            for row in items:self.assertEqual(set(row),keys)
            partition=[]
            for status in ('pending','in_progress','ended',terminal):
                rows=self.get(kind,status=status).json['data']['items'];self.assertTrue(rows)
                self.assertTrue(all(row['status']==status for row in rows));partition += [row['id'] for row in rows]
            self.assertEqual(sorted(partition),sorted(row['id'] for row in items));self.assertEqual(len(partition),len(set(partition)))
            selected=self.get(kind,room_id='10',date='2026-11-12',status='pending').json['data']['items']
            self.assertTrue(all(row['room']['id']==10 and row['status']=='pending' for row in selected))
            self.assertEqual(self.get(kind,room_id='30',date='2025-01-01').json,dict(ok=True,data=dict(items=[],total=0)))
        revoked=self.get(status='revoked').json['data']['items'][0]
        self.assertEqual(revoked['revoked_by_id'],3);self.assertIsInstance(revoked['revoke_reason'],str)
        self.assertFalse(any('cancel' in key for key in revoked));self.assertEqual(self.facts(),before)
    def test_cross_midnight_intersection_and_terminal_priority_at_boundaries(self):
        for day,expected in [('2026-11-11',[101]),('2026-11-12',[101,112,110,108]),('2026-11-13',[109])]:
            items=self.get(date=day).json['data']['items'];self.assertEqual([r['id'] for r in items],expected)
        self.clock.now=NOW+3600
        self.assertEqual([r['id'] for r in self.get(status='ended').json['data']['items']],[101,112])
        self.assertEqual([r['id'] for r in self.get(status='revoked').json['data']['items']],[110])
        block=self.post().json['data']
        for day in ('2026-11-13','2026-11-14'):self.assertIn(block['id'],[r['id'] for r in self.get(room_id='30',date=day).json['data']['items']])
    def test_list_invalid_filters_and_nonexistent_room(self):
        before=self.facts()
        for kind in ('bookings','blocks'):
            for query in [dict(status=v) for v in ('','unknown','revoked' if kind=='bookings' else 'cancelled')]+[dict(room_id=v) for v in ('','0','01','1.0',str(2**63),'9'*5000)]+[dict(date=v) for v in ('','2026-02-30','2026-1-01','9999-12-31')]:
                self.error(self.get(kind,**query),400,'INVALID_INPUT')
            self.error(self.get(kind,room_id=str(2**63-1)),404,'NOT_FOUND')
        self.assertEqual(self.facts(),before)
    def test_authorization_before_fields_direct_api_and_management_form(self):
        before=self.facts();member,identity=self.login('demo_member_a');anonymous=self.app.test_client()
        self.error(self.post({},member,identity),403,'FORBIDDEN')
        for kind in ('bookings','blocks'):
            self.error(self.get(kind,member,status='invalid',room_id='bad'),403,'FORBIDDEN')
            self.error(self.get(kind,anonymous),401,'AUTH_REQUIRED')
        self.error(anonymous.post('/api/admin/blocks',base_url=ORIGIN,headers={'Origin':ORIGIN},json={}),401,'AUTH_REQUIRED')
        page=self.client.get('/admin',base_url=ORIGIN).text
        for text in ('id="block-form"','id="admin-bookings-form"','id="admin-blocks-form"','尚未查询'):self.assertIn(text,page)
        self.assertEqual(self.facts(),before)
    def test_origin_csrf_mime_logout_expiry_and_unchanged_facts(self):
        before=self.facts()
        for headers in ({},{'Origin':'http://evil.test'},{'Origin':ORIGIN},{'Origin':ORIGIN,'X-CSRF-Token':'bad'}):
            self.error(self.client.post('/api/admin/blocks',base_url=ORIGIN,headers=headers,json=self.payload()),403,'CSRF_REJECTED')
        headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']}
        self.error(self.client.post('/api/admin/blocks',base_url=ORIGIN,headers=headers,data={}),400,'INVALID_INPUT')
        cookie=self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value
        self.assertEqual(self.client.post('/api/logout',base_url=ORIGIN,headers=headers,json={}).status_code,200)
        self.client.set_cookie(auth.COOKIE_NAME,cookie,domain='127.0.0.1');self.error(self.post(),401,'AUTH_REQUIRED')
        for kind in ('bookings','blocks'):self.error(self.get(kind),401,'AUTH_REQUIRED')
        self.client,self.identity=self.login('demo_admin');self.clock.now=NOW+auth.SESSION_SECONDS
        self.error(self.post({}),401,'AUTH_REQUIRED')
        for kind in ('bookings','blocks'):self.error(self.get(kind,status='bad'),401,'AUTH_REQUIRED')
        self.assertEqual(self.facts(),before)
    def test_service_auth_reloads_role_and_samples_one_clock_inside_transaction(self):
        with self.app.app_context():
            actor=auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value)
            for command,args in [(services.create_block,(self.payload(),)),(services.admin_blocks,()),(services.admin_bookings,())]:
                self.clock.calls=0;command(replace(actor,display_name='stale'),*args);self.assertEqual(self.clock.calls,1)
            self.assertEqual(self.facts()['audit_events'][0]['actor_display_name'],'演示管理员')
            for bad in (None,replace(actor,id=1),replace(actor,session_token_hash='0'*64)):
                for command,args in [(services.create_block,({},)),(services.admin_blocks,()),(services.admin_bookings,())]:
                    with self.assertRaises(DomainError) as error:command(bad,*args)
                    self.assertEqual(error.exception.code,'AUTH_REQUIRED')
            with db.write_transaction(self.database) as conn:conn.execute("UPDATE users SET role='member' WHERE id=3")
            for command,args in [(services.create_block,({},)),(services.admin_blocks,('bad',)),(services.admin_bookings,('bad',))]:
                with self.assertRaises(DomainError) as error:command(actor,*args)
                self.assertEqual(error.exception.code,'FORBIDDEN')
    def test_expiry_is_rechecked_after_write_lock(self):
        before=self.facts();original=db.write_transaction
        @contextmanager
        def advance(database=None):
            with original(database) as conn:self.clock.now=NOW+auth.SESSION_SECONDS;yield conn
        with patch.object(db,'write_transaction',advance):self.error(self.post({}),401,'AUTH_REQUIRED')
        self.assertEqual(self.facts(),before)
    def test_audit_failure_before_after_insert_and_commit_rolls_back_all_facts(self):
        before=self.facts()
        for after in (False,True):
            def fail(conn,event):
                if after:audit_writer(conn,event)
                raise RuntimeError('private SQL secret')
            self.app.config['AUDIT_WRITER']=fail
            with self.assertLogs(self.app.logger,level='ERROR') as logs:self.error(self.post(),500,'INTERNAL_ERROR')
            self.assertNotIn('private',str(logs.output));self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer;original=db.connect
        class FailCommit:
            def __init__(self,conn):self.conn=conn
            def __getattr__(self,name):return getattr(self.conn,name)
            def execute(self,sql,*args):
                if sql=='COMMIT':raise sqlite3.OperationalError('commit failure')
                return self.conn.execute(sql,*args)
        with patch.object(db,'connect',lambda *a,**kw:FailCommit(original(*a,**kw))),self.assertLogs(self.app.logger,level='ERROR'):
            self.error(self.post(),500,'INTERNAL_ERROR')
        self.assertEqual(self.facts(),before)
    def test_real_write_lock_timeout_returns_503_then_deliberate_retry(self):
        before=self.facts();original=db.connect
        def quick(database):
            conn=original(database);conn.execute('PRAGMA busy_timeout=10');return conn
        blocker=original(self.database)
        try:
            blocker.execute('BEGIN IMMEDIATE')
            with patch.object(db,'connect',quick):self.error(self.post(),503,'STORE_BUSY')
            self.assertEqual(self.facts(),before)
        finally:blocker.execute('ROLLBACK');blocker.close()
        self.assertEqual(self.post().status_code,201)

if __name__=='__main__':unittest.main()

"""Approval storage, authorization, replay, concurrency and migration acceptance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from booking_app import auth, create_app, db, dto, services, applications
from booking_app.audit import audit_writer
from booking_app.domain import DomainError, local_time
from scripts.init_demo import seed_users
from scripts.migrate_db import migrate_database
from tests.test_auth import accounts, FixedClock, ORIGIN


class SupervisedBookingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed_dir=tempfile.TemporaryDirectory()
        cls.seed=Path(cls.seed_dir.name)/'seed.db'
        seed_users(cls.seed,accounts(),FixedClock())

    @classmethod
    def tearDownClass(cls):
        cls.seed_dir.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db'
        with closing(db.connect(self.seed)) as source,closing(db.connect(self.path)) as dest:source.backup(dest)
        self.clock=FixedClock()
        self.actors={};self.clients={}
        with db.write_transaction(self.path) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'讨论室','研究楼',20,?,?)",(self.clock.now,self.clock.now))
            for row in conn.execute('SELECT * FROM users').fetchall():
                name=row['username']; token='token-'+name;digest=auth.token_digest(token)
                conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest,row['id'],'csrf-'+name,self.clock.now,self.clock.now+60*86400))
                self.actors[name]=auth.Actor(row['id'],row['display_name'],row['role'],digest)
        self.app=create_app({'TESTING':True,'DATABASE':str(self.path),'CLOCK':self.clock})
        for name in self.actors:
            client=self.app.test_client();client.set_cookie(auth.COOKIE_NAME,'token-'+name,domain='127.0.0.1');self.clients[name]=client
        self.student=self.actors['demo_member_a'];self.teacher=self.actors['demo_teacher_a'];self.other=self.actors['demo_teacher_b'];self.admin=self.actors['demo_admin']
        start=(self.clock.now//1800+2)*1800
        self.payload=dict(room_id=1,title='学生讨论 <img>',purpose='私有用途',attendees=3,start=local_time(start)[:16],end=local_time(start+3600)[:16],intent_key='application-intent-0001')

    def call(self,function,*args):
        with self.app.app_context():return function(*args)

    def create(self,**overrides):return self.call(applications.create_application,self.student,self.payload|overrides)['application']
    def decide(self,item,action='approve',actor=None,payload=None):return self.call(applications.decide_application,actor or self.teacher,item['id'],action,payload or {})
    def facts(self):
        with closing(db.connect(self.path)) as conn:
            return {table:[dict(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY 1')] for table in db.REQUIRED_COLUMNS}
    def assert_code(self,code,func,*args):
        with self.assertRaises(DomainError) as context:self.call(func,*args)
        self.assertEqual(context.exception.code,code)

    def test_submit_replay_approve_and_shared_privacy(self):
        item=self.create();facts=self.facts()
        self.assertEqual(item['status'],'awaiting_approval');self.assertEqual(item['weeks'],1)
        self.assertEqual(facts['reservations'],[]);self.assertEqual(facts['occupancy_slots'],[])
        self.assertEqual(self.create()['id'],item['id']);self.assertEqual(self.facts(),facts)
        self.assert_code('IDEMPOTENCY_MISMATCH',applications.create_application,self.student,self.payload|{'title':'different'})
        approved=self.decide(item);self.assertEqual(approved['status'],'approved')
        facts=self.facts();self.assertEqual(len(facts['reservations']),1);self.assertEqual(len(facts['occupancy_slots']),2)
        self.assertEqual([r['action'] for r in facts['audit_events']],['application.created','booking.created','application.approved'])
        self.assertEqual(self.create(),approved);self.assertEqual(self.decide(item),approved);self.assertEqual(self.facts(),facts)
        booking=self.call(services.booking_detail,self.teacher,approved['reservation_id'])
        self.assertEqual(booking['application_id'],item['id']);self.assertEqual(booking['approved_by'],self.teacher.id)
        shared=self.call(services.schedule,self.other,1,self.payload['start'][:10])['items'][0]['record']
        self.assertEqual(shared['supervisor_display_name'],self.teacher.display_name)
        self.assertFalse({'purpose','owner_id','supervisor_id','application_id','decision_reason'}&shared.keys())
        self.assertEqual(self.call(services.audit_events,self.admin,'application')['total'],2)

    def test_visibility_cross_teacher_admin_and_forged_actor(self):
        item=self.create();facts=self.facts()
        self.assertEqual(self.call(applications.list_applications,self.other)['items'],[])
        for actor in (self.other,self.actors['demo_member_b']):
            self.assert_code('NOT_FOUND',applications.application_detail,actor,item['id'])
            self.assert_code('NOT_FOUND',applications.decide_application,actor,item['id'],'approve',{})
        self.assertEqual(self.call(applications.application_detail,self.admin,item['id'])['id'],item['id'])
        for action in ('approve','reject','withdraw'):
            self.assert_code('FORBIDDEN',applications.decide_application,self.admin,item['id'],action,{'reason':'理由'} if action=='reject' else {})
        forged=auth.Actor(self.student.id,'forged','teacher',self.student.session_token_hash)
        self.assert_code('FORBIDDEN',applications.decide_application,forged,item['id'],'approve',{})
        self.assertEqual(self.facts(),facts)
        approved=self.decide(item)
        self.assert_code('NOT_FOUND',services.booking_detail,self.other,approved['reservation_id'])

    def test_reject_withdraw_and_first_decision_facts(self):
        item=self.create();self.assert_code('INVALID_INPUT',applications.decide_application,self.teacher,item['id'],'reject',{'reason':' '})
        rejected=self.decide(item,'reject',payload={'reason':' 首次原因 '});self.assertEqual(rejected['decision_reason'],'首次原因')
        facts=self.facts();self.assertEqual(self.decide(item,'reject',payload={'reason':'不同原因'}),rejected);self.assertEqual(self.facts(),facts)
        self.assert_code('TRANSITION_CLOSED',applications.decide_application,self.student,item['id'],'withdraw',{})
        other=self.create(intent_key='application-intent-0002');withdrawn=self.decide(other,'withdraw',self.student)
        self.assertEqual(withdrawn['status'],'withdrawn');self.assertEqual(self.decide(other,'withdraw',self.student),withdrawn)
        self.assertEqual(self.facts()['occupancy_slots'],[])

    def test_twenty_competing_approvals_exactly_one(self):
        items=[self.create(intent_key=f'application-intent-{i:04}') for i in range(20)]
        def approve(item):
            try:return self.decide(item)['status']
            except DomainError as error:return error.code
        with ThreadPoolExecutor(max_workers=20) as pool:results=list(pool.map(approve,items))
        self.assertEqual(results.count('approved'),1);self.assertEqual(results.count('OCCUPANCY_CONFLICT'),19)
        facts=self.facts();self.assertEqual(len(facts['reservations']),1);self.assertEqual(len(facts['occupancy_slots']),2)
        self.assertEqual(sum(r['status']=='awaiting_approval' for r in facts['applications']),19)
        self.assertEqual(len(facts['audit_events']),22)

    def test_audit_failure_rolls_back_each_approval_stage_and_creation(self):
        before=self.facts()
        def fail(conn,event):
            audit_writer(conn,event)
            raise RuntimeError('injected')
        self.app.config['AUDIT_WRITER']=fail
        with self.assertRaises(RuntimeError):self.create()
        self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer;item=self.create();before=self.facts()
        for target in ('booking.created','application.approved'):
            def fail_target(conn,event):
                audit_writer(conn,event)
                if event['action']==target:raise RuntimeError('injected')
            self.app.config['AUDIT_WRITER']=fail_target
            with self.assertRaises(RuntimeError):self.decide(item)
            self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer;self.assertEqual(self.decide(item)['status'],'approved')

    def test_approval_rechecks_time_capacity_identity_and_expiry_is_derived(self):
        item=self.create()
        with db.write_transaction(self.path) as conn:conn.execute('UPDATE rooms SET capacity=2 WHERE id=1')
        self.assert_code('CAPACITY_CONFLICT',applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assertEqual(self.facts()['applications'][0]['status'],'awaiting_approval')
        with db.write_transaction(self.path) as conn:conn.execute('UPDATE rooms SET capacity=20 WHERE id=1')
        self.clock.now=item['start_at'];before=self.facts()
        self.assert_code('INVALID_INPUT',applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assertTrue(self.call(applications.application_detail,self.student,item['id'])['expired']);self.assertEqual(self.facts(),before)
        self.clock.now=item['created_at']
        with db.write_transaction(self.path) as conn:conn.execute('UPDATE users SET supervisor_id=? WHERE id=?',(self.other.id,self.student.id))
        self.assert_code('NOT_FOUND',applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assert_code('NOT_FOUND',applications.decide_application,self.other,item['id'],'approve',{})

    def test_window_exact_seven_day_boundary_and_block_stays_thirty(self):
        self.clock.now=self.clock.now//1800*1800
        end=self.clock.now+7*86400
        values=self.payload|{'start':local_time(end-1800)[:16],'end':local_time(end)[:16]}
        item=self.call(applications.create_application,self.student,values)['application'];self.decide(item)
        self.assertEqual(self.call(services.availability,self.student,values['start'],values['end'],3)['total'],0)
        too_late=values|{'intent_key':'application-intent-late','end':local_time(end+1800)[:16]}
        self.assert_code('INVALID_INPUT',applications.create_application,self.student,too_late)
        self.assert_code('INVALID_INPUT',services.create_booking,self.teacher,too_late)
        block_start=self.clock.now+29*86400
        self.assertEqual(self.call(services.create_block,self.admin,dict(room_id=1,start=local_time(block_start)[:16],end=local_time(block_start+1800)[:16],reason='维护'))['status'],'pending')

    def test_students_cannot_direct_book_or_cancel_but_legacy_replays_survive(self):
        self.assert_code('FORBIDDEN',services.create_booking,self.student,self.payload)
        self.assert_code('INVALID_INPUT',applications.create_application,self.student,self.payload|{'supervisor_id':self.other.id})
        self.assert_code('INVALID_INPUT',applications.create_application,self.student,self.payload|{'weeks':2})
        item=self.decide(self.create());before=self.facts()
        self.assert_code('FORBIDDEN',services.member_cancel_booking,self.student,item['reservation_id']);self.assertEqual(self.facts(),before)
        self.call(services.admin_cancel_booking,self.admin,item['reservation_id'],'管理员取消')
        self.assertEqual(self.call(services.member_cancel_booking,self.student,item['reservation_id'])['status'],'cancelled')

    def test_real_schema_one_history_preserves_replay_without_invented_supervisor(self):
        from booking_app.domain import normalize_booking_payload
        values,key=normalize_booking_payload(self.payload)
        legacy=Path(self.temp.name)/'v1-history.db'
        with closing(db.connect(legacy)) as conn:
            conn.execute('PRAGMA journal_mode=WAL');conn.executescript(Path('tests/fixtures/schema_v1.sql').read_text())
            conn.execute("INSERT INTO users VALUES(?,'old-student','旧学生','preserved-hash','member',?)",(self.student.id,self.clock.now))
            conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(self.student.session_token_hash,self.student.id,'legacy-csrf',self.clock.now,self.clock.now+3600))
            conn.execute("INSERT INTO rooms VALUES(1,'历史房间','旧地点',20,?,?)",(self.clock.now,self.clock.now))
            conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                         "VALUES(41,'booking',1,?,?,?,?,?,?,?,?,?)",(self.student.id,values['title'],values['purpose'],values['attendees'],values['start_at'],values['end_at'],key,json.dumps(values),self.clock.now))
            conn.executemany('INSERT INTO occupancy_slots VALUES(1,?,41)',[(slot,) for slot in range(values['start_at'],values['end_at'],1800)])
            conn.execute('PRAGMA user_version=1')
        migrate_database(legacy,Path(self.temp.name)/'v1-history-backup.db')
        legacy_app=create_app({'TESTING':True,'DATABASE':str(legacy),'CLOCK':self.clock})
        with legacy_app.app_context():
            result=services.create_booking(self.student,self.payload)
            self.assertTrue(result['replayed']);self.assertEqual(result['booking']['id'],41)
            self.assertEqual(result['booking']['supervisor_source'],'legacy');self.assertIsNone(result['booking']['supervisor_id'])
            with self.assertRaises(DomainError) as context:services.create_booking(self.student,self.payload|{'intent_key':'new-student-intent'})
            self.assertEqual(context.exception.code,'FORBIDDEN')
            with self.assertRaises(DomainError) as context:services.member_cancel_booking(self.student,41)
            self.assertEqual(context.exception.code,'FORBIDDEN')
        with closing(db.connect(legacy)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM booking_supervisors').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM audit_events').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots').fetchone()[0],2)

    def test_concurrent_same_intent_and_failed_terminal_audit(self):
        def submit(_):return self.create()['id']
        with ThreadPoolExecutor(max_workers=10) as pool:ids=list(pool.map(submit,range(10)))
        self.assertEqual(len(set(ids)),1);item=self.create();before=self.facts()
        self.assertEqual(len(before['applications']),1);self.assertEqual(len(before['audit_events']),1)
        def fail(conn,event):
            audit_writer(conn,event);raise RuntimeError('injected')
        self.app.config['AUDIT_WRITER']=fail
        for action,actor,payload in [('reject',self.teacher,{'reason':'不合适'}),('withdraw',self.student,{})]:
            with self.assertRaises(RuntimeError):self.decide(item,action,actor,payload)
            self.assertEqual(self.facts(),before)

    def test_teacher_and_admin_direct_booking_supervisor_facts(self):
        teacher=self.call(services.create_booking,self.teacher,self.payload)['booking'];self.assertEqual(teacher['supervisor_id'],self.teacher.id)
        self.call(services.member_cancel_booking,self.teacher,teacher['id'])
        admin=self.call(services.create_booking,self.admin,self.payload)['booking'];self.assertEqual(admin['supervisor_source'],'admin');self.assertIsNone(admin['supervisor_id'])
        self.assertTrue(self.call(services.create_booking,self.admin,self.payload)['replayed'])

    def test_http_csrf_origin_routes_and_pages(self):
        student=self.clients['demo_member_a'];teacher=self.clients['demo_teacher_a']
        def post(client,url,body,who):return client.post(url,base_url=ORIGIN,json=body,headers={'Origin':ORIGIN,'X-CSRF-Token':'csrf-'+who})
        self.assertEqual(student.post('/api/applications',base_url=ORIGIN,json=self.payload).status_code,403)
        response=post(student,'/api/applications',self.payload,'demo_member_a');self.assertEqual(response.status_code,201,response.text)
        item=response.json['data']['application'];self.assertEqual(post(student,'/api/applications',self.payload,'demo_member_a').status_code,200)
        self.assertEqual(post(teacher,f"/api/applications/{item['id']}/approve",{},'demo_teacher_a').status_code,200)
        self.assertEqual(self.clients['demo_teacher_b'].get(f"/api/applications/{item['id']}",base_url=ORIGIN).status_code,404)
        for page in ('/','/my','/applications'):self.assertEqual(student.get(page,base_url=ORIGIN).status_code,200)

    def test_schema_two_migration_preserves_identity_and_has_empty_new_tables(self):
        path=Path(self.temp.name)/'v2.db';backup=Path(self.temp.name)/'v2-backup.db'
        with closing(db.connect(path)) as conn:
            conn.execute('PRAGMA journal_mode=WAL');conn.executescript(Path('tests/fixtures/schema_v2.sql').read_text())
            conn.execute("INSERT INTO users VALUES(1,'teacher','导师','hash','teacher',100,NULL)")
            conn.execute("INSERT INTO users VALUES(2,'student','学生','hash','member',100,1)")
            conn.execute("INSERT INTO rooms VALUES(1,'历史室','旧位置',12,100,100)")
            conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                "VALUES(11,'booking',1,2,'旧预约','保留用途',3,1800001800,1800005400,'historical-v2-intent','{}',100)")
            conn.executemany('INSERT INTO occupancy_slots VALUES(1,?,11)',[(1800001800,),(1800003600,)])
            conn.execute('INSERT INTO sessions VALUES(?,2,?,100,1000)',('a'*64,'historical-csrf'))
            for action,target_type,target_id,after in [
                ('room.created','room',1,dict(id=1,name='历史室',location='旧位置',capacity=12)),
                ('booking.created','booking',11,dto.booking_snapshot(conn.execute('SELECT * FROM reservations WHERE id=11').fetchone()))]:
                audit_writer(conn,dict(actor_id=2,actor_display_name='历史显示名',action=action,target_type=target_type,target_id=target_id,occurred_at=100,before=None,after=after,reason=None))
            conn.execute('PRAGMA user_version=2')
            old_tables=('users','sessions','rooms','reservations','occupancy_slots','audit_events')
            before={table:[tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY 1')] for table in old_tables}
        migrate_database(path,backup);db.check_database(path)
        with closing(db.connect(path)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual([tuple(r) for r in conn.execute('SELECT role,supervisor_id FROM users ORDER BY id')],[('teacher',None),('member',1)])
            for table in ('applications','application_occurrences','booking_supervisors','cancellation_requests'):self.assertEqual(conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
            self.assertEqual({table:[tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY 1')] for table in old_tables},before)
            historical=[dto.audit_event(r) for r in conn.execute('SELECT * FROM audit_events ORDER BY id')]
            self.assertEqual([e['action'] for e in historical],['room.created','booking.created'])
            self.assertEqual(historical[1]['after']['purpose'],'保留用途')
        with closing(db.connect(backup)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual({table:[tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY 1')] for table in old_tables},before)
        create_app({'TESTING':True,'DATABASE':str(path),'CLOCK':self.clock})

    def test_schema_two_trigger_failure_leaves_version_and_facts(self):
        path=Path(self.temp.name)/'bad-v2.db';backup=Path(self.temp.name)/'bad-backup.db'
        with closing(db.connect(path)) as conn:
            conn.execute('PRAGMA journal_mode=WAL');conn.executescript(Path('tests/fixtures/schema_v2.sql').read_text());conn.execute('PRAGMA user_version=2');conn.execute('DROP TRIGGER users_supervisor_insert')
        with self.assertRaises(RuntimeError):migrate_database(path,backup)
        with closing(db.connect(path)) as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],2)
        self.assertFalse(backup.exists())

    def test_sql_rejected_application_requires_nonnull_reason(self):
        item=self.create();before=self.facts()
        with closing(db.connect(self.path)) as conn:
            for reason in (None,'','   '):
                with self.subTest(reason=reason),self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("UPDATE applications SET status='rejected',decided_at=?,decided_by=?,decision_reason=? WHERE id=?",(self.clock.now,self.teacher.id,reason,item['id']))
        self.assertEqual(self.facts(),before)
        self.assertEqual(self.decide(item,'reject',payload={'reason':'有效原因'})['decision_reason'],'有效原因')

    def test_http_reject_withdraw_authorization_payload_csrf_and_replay(self):
        def post(who,url,body,**headers):
            return self.clients[who].post(url,base_url=ORIGIN,json=body,headers={'Origin':ORIGIN,'X-CSRF-Token':'csrf-'+who}|headers)
        for action,who,payload,status in [('reject','demo_teacher_a',{'reason':'首次拒绝'},'rejected'),('withdraw','demo_member_a',{},'withdrawn')]:
            item=self.create(intent_key='http-transition-'+action)
            url=f"/api/applications/{item['id']}/{action}";before=self.facts()
            anonymous=self.app.test_client()
            self.assertEqual(anonymous.post(url,base_url=ORIGIN,json=payload,headers={'Origin':ORIGIN}).status_code,401)
            for headers in ({'Origin':'https://invalid.example'},{'X-CSRF-Token':'bad-token'}):
                response=post(who,url,payload,**headers);self.assertEqual(response.status_code,403);self.assertEqual(response.json['error']['code'],'CSRF_REJECTED')
            for other,expected in [('demo_teacher_b',404),('demo_member_b',404),('demo_admin',403),('demo_member_a' if action=='reject' else 'demo_teacher_a',403)]:
                self.assertEqual(post(other,url,payload).status_code,expected)
            invalid=[{'reason':None},{'reason':' '},{'reason':'x'*501},{'reason':'理由','owner_id':self.student.id},{}] if action=='reject' else [{'reason':'不接受'}, {'owner_id':self.student.id}]
            for bad in invalid:self.assertEqual(post(who,url,bad).status_code,400)
            self.assertEqual(self.clients[who].post(url,base_url=ORIGIN,data={},headers={'Origin':ORIGIN,'X-CSRF-Token':'csrf-'+who}).status_code,400)
            self.assertEqual(self.facts(),before)
            response=post(who,url,payload);self.assertEqual(response.status_code,200,response.text)
            first=response.json['data'];self.assertEqual(first['status'],status)
            committed=self.facts()
            replay=post(who,url,{'reason':'之后的原因'} if action=='reject' else {})
            self.assertEqual(replay.status_code,200);self.assertEqual(replay.json['data'],first);self.assertEqual(self.facts(),committed)
            self.assertEqual(post('demo_admin',url,payload).status_code,403)
            self.assertEqual(post('demo_teacher_b',url,payload).status_code,404)
            self.assertEqual(post(who,url,payload,**{'X-CSRF-Token':'stale'}).status_code,403)
            self.assertEqual(self.facts(),committed)
        self.assertEqual(self.facts()['occupancy_slots'],[])

    def test_startup_rejects_missing_critical_definitions_and_indexes(self):
        schema=Path('booking_app/schema.sql').read_text()
        variants={
            'application-unique':schema.replace('UNIQUE(owner_id,intent_key),',''),
            'occurrence-unique':schema.replace('reservation_id INTEGER NOT NULL UNIQUE REFERENCES reservations','reservation_id INTEGER NOT NULL REFERENCES reservations'),
            'supervisor-source':schema.replace("CHECK(source IN ('teacher','application','admin'))",""),
            'user-role':schema.replace("CHECK (role IN ('member', 'teacher', 'admin'))",''),
            'rejection-null':schema.replace('decision_reason IS NOT NULL AND ',''),
            'intent-index':schema.replace('CREATE UNIQUE INDEX IF NOT EXISTS reservations_user_intent','CREATE INDEX IF NOT EXISTS reservations_user_intent'),
            'missing-index':schema.replace('CREATE INDEX IF NOT EXISTS applications_supervisor ON applications(supervisor_id,created_at,id);',''),
        }
        for label,modified in variants.items():
            with self.subTest(label=label):
                self.assertNotEqual(schema,modified)
                path=Path(self.temp.name)/(label+'.db')
                with closing(db.connect(path)) as conn:
                    conn.execute('PRAGMA journal_mode=WAL');conn.executescript(modified);conn.execute('PRAGMA user_version=3')
                    self.assertEqual({r[1] for r in conn.execute('PRAGMA table_info(applications)')},db.REQUIRED_COLUMNS['applications'])
                with self.assertRaises(RuntimeError):create_app({'TESTING':True,'DATABASE':str(path),'CLOCK':self.clock})
        db.check_database(self.path)

    def test_legacy_audit_variations_are_rejected_without_losing_source_or_creating_backup(self):
        for version in (1,2):
            original=Path(f'tests/fixtures/schema_v{version}.sql').read_text()
            for variation in ('constraint','custom-index','custom-trigger','altered-index'):
                with self.subTest(version=version,variation=variation):
                    path=Path(self.temp.name)/f'bad-audit-{version}-{variation}.db';backup=path.with_suffix('.backup')
                    schema=original.replace("target_type IN ('room','booking','block')","target_type IN ('room','booking','block','local')") if variation=='constraint' else original
                    with closing(db.connect(path)) as conn:
                        conn.execute('PRAGMA journal_mode=WAL');conn.executescript(schema)
                        conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'admin','旧管理员','hash','admin',100)")
                        conn.execute("INSERT INTO audit_events VALUES(1,1,'旧名字','room.created','room',1,100,NULL,?,NULL)",(json.dumps(dict(id=1,name='历史室',location='原位置',capacity=12)),))
                        if variation=='custom-index':conn.execute('CREATE INDEX local_audit ON audit_events(actor_id)')
                        if variation=='custom-trigger':conn.execute("CREATE TRIGGER local_audit BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'protected'); END")
                        if variation=='altered-index':
                            conn.execute('DROP INDEX audit_events_target_time');conn.execute('CREATE INDEX audit_events_target_time ON audit_events(actor_id)')
                        conn.execute(f'PRAGMA user_version={version}');before=list(conn.iterdump())
                    with self.assertRaises(ValueError):migrate_database(path,backup)
                    with closing(db.connect(path)) as conn:
                        self.assertEqual(list(conn.iterdump()),before);self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],version)
                        self.assertEqual(conn.execute('SELECT actor_display_name FROM audit_events').fetchone()[0],'旧名字')
                    self.assertFalse(backup.exists())

if __name__=='__main__':unittest.main()

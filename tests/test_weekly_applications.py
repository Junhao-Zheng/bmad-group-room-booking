"""Eight-week all-or-nothing approval and per-occurrence cancellation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from booking_app import auth, create_app, db, applications, cancellations, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError, local_time
from scripts.init_demo import seed_users
from scripts.migrate_db import migrate_database
from tests.test_auth import accounts, FixedClock


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'weekly.sqlite3';self.clock=FixedClock()
        seed_users(self.path,accounts(),self.clock)
        self.actors={}
        with db.write_transaction(self.path) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'407','2号楼',20,?,?)",(self.clock.now,self.clock.now))
            for row in conn.execute('SELECT * FROM users'):
                token=auth.token_digest('token-'+row['username'])
                conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(token,row['id'],'csrf',self.clock.now,self.clock.now+70*86400))
                self.actors[row['username']]=auth.Actor(row['id'],row['display_name'],row['role'],token)
        self.app=create_app({'TESTING':True,'DATABASE':str(self.path),'CLOCK':self.clock})
        self.student=self.actors['demo_member_a'];self.teacher=self.actors['demo_teacher_a'];self.admin=self.actors['demo_admin']
        start=(self.clock.now//1800+2)*1800
        self.payload=dict(room_id=1,title='每周组会',purpose='课题讨论',attendees=3,
            start=local_time(start)[:16],end=local_time(start+3600)[:16],weeks=8,intent_key='weekly-intent-0000001')

    def call(self,func,*args):
        with self.app.app_context():return func(*args)

    def facts(self):
        with closing(db.connect(self.path)) as conn:
            return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('applications','application_occurrences','reservations','occupancy_slots','audit_events')}

    def code(self,expected,func,*args):
        with self.assertRaises(DomainError) as caught:self.call(func,*args)
        self.assertEqual(caught.exception.code,expected)
        return caught.exception

    def test_eight_weeks_atomic_approval_and_one_occurrence_cancellation(self):
        item=self.call(applications.create_application,self.student,self.payload)['application']
        self.assertEqual(item['weeks'],8);self.assertEqual(len(item['occurrences']),8)
        self.assertEqual(self.facts()['occupancy_slots'],[])
        approved=self.call(applications.decide_application,self.teacher,item['id'],'approve',{})
        ids=[part['reservation_id'] for part in approved['occurrences']]
        self.assertEqual(len(set(ids)),8)
        self.assertEqual(len(self.facts()['occupancy_slots']),16)
        self.assertEqual(self.call(applications.create_application,self.student,self.payload)['application'],approved)
        self.assertEqual(self.call(applications.decide_application,self.teacher,item['id'],'approve',{}),approved)
        request=self.call(cancellations.create_request,self.student,ids[2])['cancellation_request']
        self.call(cancellations.decide_request,self.teacher,request['id'],'approve',{})
        after=self.call(applications.application_detail,self.student,item['id'])
        self.assertEqual(after['occurrences'][2]['status'],'cancelled')
        self.assertEqual(len(self.facts()['occupancy_slots']),14)
        self.assertTrue(all(part['status']!='cancelled' for index,part in enumerate(after['occurrences']) if index!=2))

    def test_third_week_conflict_rejects_whole_group_until_removed(self):
        start=(self.clock.now//1800+2)*1800+14*86400
        with db.write_transaction(self.path) as conn:
            conn.execute("INSERT INTO reservations(kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                "VALUES('booking',1,?,'占用','已有组会',3,?,?,'other-booking-intent','{}',?)",
                (self.teacher.id,start,start+3600,self.clock.now))
            booking_id=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.executemany('INSERT INTO occupancy_slots VALUES(1,?,?)',[(slot,booking_id) for slot in range(start,start+3600,1800)])
        item=self.call(applications.create_application,self.student,self.payload)['application']
        before=self.facts()
        error=self.code('OCCUPANCY_CONFLICT',applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assertEqual(error.conflicts[0]['start_local'][:10],local_time(start)[:10])
        self.assertEqual(self.facts(),before)
        self.call(services.admin_cancel_booking,self.admin,booking_id,'旧预约取消')
        self.assertEqual(len(self.call(applications.decide_application,self.teacher,item['id'],'approve',{})['occurrences']),8)

    def test_direct_teacher_and_admin_all_or_nothing_and_intent_rules(self):
        direct=self.call(applications.create_application,self.teacher,self.payload)['application']
        self.assertEqual(direct['status'],'approved')
        first=direct['occurrences'][0]['reservation_id']
        self.assertEqual(self.call(services.booking_detail,self.teacher,first)['supervisor_source'],'teacher')
        before=self.facts()
        self.code('OCCUPANCY_CONFLICT',applications.create_application,self.admin,self.payload)
        self.assertEqual(self.facts(),before)
        self.assertEqual(self.call(applications.create_application,self.teacher,self.payload)['application'],direct)
        for weeks in (0,9,True,2.5,'8'):
            self.code('INVALID_INPUT',applications.create_application,self.teacher,self.payload|{'weeks':weeks,'intent_key':f'bad-week-{weeks}'})
        self.code('IDEMPOTENCY_MISMATCH',applications.create_application,self.teacher,self.payload|{'weeks':7})
        self.code('IDEMPOTENCY_MISMATCH',services.create_booking,self.teacher,{key:value for key,value in self.payload.items() if key!='weeks'})

    def test_failure_in_last_booking_audit_rolls_back_every_week(self):
        item=self.call(applications.create_application,self.student,self.payload)['application'];before=self.facts()
        count=0
        def fail(conn,event):
            nonlocal count
            audit_writer(conn,event)
            if event['action']=='booking.created':
                count+=1
                if count==8:raise RuntimeError('injected')
        self.app.config['AUDIT_WRITER']=fail
        with self.assertRaises(RuntimeError):self.call(applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer
        self.assertEqual(self.call(applications.decide_application,self.teacher,item['id'],'approve',{})['status'],'approved')

    def test_twenty_competing_groups_have_one_complete_winner(self):
        items=[self.call(applications.create_application,self.student,
            self.payload|{'intent_key':f'weekly-race-{index:04}'})['application'] for index in range(20)]
        def approve(item):
            try:return self.call(applications.decide_application,self.teacher,item['id'],'approve',{})['status']
            except DomainError as error:return error.code
        with ThreadPoolExecutor(max_workers=20) as pool:outcomes=list(pool.map(approve,items))
        self.assertEqual(outcomes.count('approved'),1)
        self.assertEqual(outcomes.count('OCCUPANCY_CONFLICT'),19)
        facts=self.facts()
        self.assertEqual(len(facts['reservations']),8)
        self.assertEqual(len(facts['occupancy_slots']),16)
        self.assertEqual(len(facts['application_occurrences']),8)

    def test_cross_year_dates_and_expired_first_week(self):
        self.clock.now=int(datetime(2026,12,29,12,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())
        start=int(datetime(2026,12,30,15,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())
        payload=self.payload|{'start':local_time(start)[:16],'end':local_time(start+9000)[:16]}
        item=self.call(applications.create_application,self.student,payload)['application']
        self.assertEqual(item['occurrences'][0]['start_local'][:10],'2026-12-30')
        self.assertEqual(item['occurrences'][-1]['start_local'][:10],'2027-02-17')
        self.clock.now=start
        before=self.facts()
        self.code('INVALID_INPUT',applications.decide_application,self.teacher,item['id'],'approve',{})
        self.assertEqual(self.facts(),before)

    def test_version_four_migration_preserves_history(self):
        legacy=Path(self.temp.name)/'v4.sqlite3'
        schema=Path(db.__file__).with_name('schema_v6.sql').read_text()
        schema=schema.split('CREATE TABLE IF NOT EXISTS maintenance_previews')[0]
        schema=schema.replace("CHECK(typeof(weeks)='integer' AND weeks BETWEEN 1 AND 8)","CHECK(weeks=1)")
        schema=schema.replace('CHECK(occurrence BETWEEN 1 AND 8)','CHECK(occurrence=1)')
        with closing(db.connect(legacy)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(schema)
            conn.execute('PRAGMA user_version=4')
            conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) "
                "VALUES(1,'old','旧管理员','hash','admin',?)",(self.clock.now,))
            conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) "
                "VALUES(2,'teacher','旧导师','hash','teacher',?)",(self.clock.now,))
            conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at,supervisor_id) "
                "VALUES(3,'student','旧学生','hash','member',?,2)",(self.clock.now,))
            conn.execute("INSERT INTO rooms VALUES(1,'旧房间','旧楼',10,?,?)",(self.clock.now,self.clock.now))
            start=(self.clock.now//1800+2)*1800
            conn.execute("INSERT INTO applications(id,owner_id,owner_display_name,supervisor_id,supervisor_display_name,room_id,"
                "title,purpose,attendees,start_at,end_at,weeks,intent_key,request_payload,status,created_at,decided_at,decided_by) "
                "VALUES(10,3,'旧学生',2,'旧导师',1,'旧组会','旧用途',3,?,?,1,'old-app-intent-0001',?,'approved',?,?,2)",
                (start,start+3600,json.dumps({'room_id':1,'title':'旧组会','purpose':'旧用途','attendees':3,'start_at':start,'end_at':start+3600,'weeks':1}),self.clock.now,self.clock.now))
            conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                "VALUES(20,'booking',1,3,'旧组会','旧用途',3,?,?,'old-booking-intent-1','{}',?)",
                (start,start+3600,self.clock.now))
            conn.execute("INSERT INTO application_occurrences VALUES(10,1,20)")
            conn.execute("INSERT INTO booking_supervisors VALUES(20,2,'旧导师','application')")
            conn.executemany("INSERT INTO occupancy_slots VALUES(1,?,20)",[(slot,) for slot in range(start,start+3600,1800)])
            conn.execute("INSERT INTO cancellation_requests(booking_id,requester_id,supervisor_id,created_at,status) "
                "VALUES(20,3,2,?,'awaiting_approval')",(self.clock.now,))
        backup=Path(self.temp.name)/'v4-backup.sqlite3'
        migrate_database(legacy,backup)
        with closing(db.connect(legacy)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT name FROM rooms').fetchone()[0],'旧房间')
            self.assertEqual(conn.execute('SELECT weeks FROM applications WHERE id=10').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT reservation_id FROM application_occurrences WHERE application_id=10').fetchone()[0],20)
            self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=20').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT status FROM cancellation_requests WHERE booking_id=20').fetchone()[0],'awaiting_approval')
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with closing(db.connect(backup)) as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],4)


if __name__=='__main__':unittest.main()

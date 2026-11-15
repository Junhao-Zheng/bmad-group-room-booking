"""Preview-bound, atomic maintenance with durable retry facts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from booking_app import auth, create_app, db, applications, cancellations, maintenance, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError, local_time
from scripts.init_demo import seed_users
from scripts.migrate_db import migrate_database
from tests.test_auth import accounts, FixedClock


class BatchMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'batch.sqlite3';self.clock=FixedClock()
        seed_users(self.path,accounts(),self.clock)
        self.actors={}
        with db.write_transaction(self.path) as conn:
            for room_id in (1,2):conn.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?)',
                (room_id,f'会议室{room_id}','2号楼',20,self.clock.now,self.clock.now))
            for row in conn.execute('SELECT * FROM users'):
                token=auth.token_digest('token-'+row['username'])
                conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(token,row['id'],'csrf',self.clock.now,self.clock.now+60*86400))
                self.actors[row['username']]=auth.Actor(row['id'],row['display_name'],row['role'],token)
        self.app=create_app({'TESTING':True,'DATABASE':str(self.path),'CLOCK':self.clock})
        self.admin=self.actors['demo_admin'];self.teacher=self.actors['demo_teacher_a'];self.student=self.actors['demo_member_a']
        self.start=(self.clock.now//1800+3)*1800
        self.window=dict(room_id=1,start=local_time(self.start)[:16],end=local_time(self.start+7200)[:16],reason='空调维修')

    def call(self,func,*args):
        with self.app.app_context():return func(*args)

    def code(self,expected,func,*args):
        with self.assertRaises(DomainError) as caught:self.call(func,*args)
        self.assertEqual(caught.exception.code,expected)

    def book(self,offset,key,room=1,student=False):
        payload=dict(room_id=room,title=f'组会{key}',purpose='研究',attendees=3,
            start=local_time(self.start+offset)[:16],end=local_time(self.start+offset+1800)[:16],intent_key=key)
        if not student:return self.call(services.create_booking,self.teacher,payload)['booking']['id']
        item=self.call(applications.create_application,self.student,payload)['application']
        return self.call(applications.decide_application,self.teacher,item['id'],'approve',{})['reservation_id']

    def facts(self):
        with closing(db.connect(self.path)) as conn:
            return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('reservations','occupancy_slots','cancellation_requests','maintenance_previews','audit_events')}

    def test_two_bookings_cancelled_one_block_and_revoke_does_not_restore(self):
        first=self.book(0,'batch-booking-0001',student=True)
        second=self.book(3600,'batch-booking-0002')
        adjacent=self.book(7200,'batch-booking-0003')
        other=self.book(0,'batch-booking-0004',room=2)
        request=self.call(cancellations.create_request,self.student,first)['cancellation_request']
        preview=self.call(maintenance.preview,self.admin,self.window)
        self.assertEqual([r['id'] for r in preview['affected']],[first,second])
        self.assertEqual(len(self.facts()['reservations']),4)
        result=self.call(maintenance.confirm,self.admin,dict(preview_token=preview['preview_token'],confirmed=True))
        self.assertFalse(result['replayed']);block=result['block'];self.assertEqual(block['status'],'pending')
        facts=self.facts()
        self.assertEqual([r['id'] for r in facts['reservations'] if r['cancelled_at'] is not None],[first,second])
        self.assertEqual(len(facts['occupancy_slots']),6)
        self.assertEqual(facts['cancellation_requests'][0]['status'],'superseded')
        self.assertEqual([r['id'] for r in facts['reservations'] if r['cancelled_at'] is None and r['kind']=='booking'],[adjacent,other])
        self.clock.now=preview['expires_at']+1
        replay=self.call(maintenance.confirm,self.admin,dict(preview_token=preview['preview_token'],confirmed=True))
        self.assertTrue(replay['replayed']);self.assertEqual(replay['block']['id'],block['id']);self.assertEqual(self.facts(),facts)
        self.call(services.revoke_block,self.admin,block['id'],{'reason':'维修结束'})
        self.assertEqual(self.call(services.booking_detail,self.student,first)['status'],'cancelled')
        self.assertEqual(self.call(services.booking_detail,self.teacher,second)['status'],'cancelled')

    def test_changed_affected_set_requires_new_preview(self):
        first=self.book(0,'batch-booking-0001')
        preview=self.call(maintenance.preview,self.admin,self.window)
        second=self.book(3600,'batch-booking-0002')
        before=self.facts()
        self.code('TRANSITION_CLOSED',maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':True})
        self.assertEqual(self.facts(),before)
        fresh=self.call(maintenance.preview,self.admin,self.window)
        self.assertEqual([r['id'] for r in fresh['affected']],[first,second])
        self.call(services.admin_cancel_booking,self.admin,first,'取消首条')
        before=self.facts()
        self.code('TRANSITION_CLOSED',maintenance.confirm,self.admin,{'preview_token':fresh['preview_token'],'confirmed':True})
        self.assertEqual(self.facts(),before)

    def test_audit_failure_rolls_back_bookings_slots_pending_request_and_block(self):
        first=self.book(0,'batch-booking-0001',student=True)
        self.book(3600,'batch-booking-0002')
        self.call(cancellations.create_request,self.student,first)
        preview=self.call(maintenance.preview,self.admin,self.window)
        before=self.facts()
        def fail(conn,event):
            audit_writer(conn,event)
            if event['action']=='block.created':raise RuntimeError('injected')
        self.app.config['AUDIT_WRITER']=fail
        with self.assertRaises(RuntimeError):self.call(maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':True})
        self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer
        self.assertEqual(len(self.call(maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':True})['affected']),2)

    def test_token_actor_expiry_and_existing_block_rejected(self):
        preview=self.call(maintenance.preview,self.admin,self.window)
        before=self.facts()
        for actor in (self.teacher,self.student):
            self.code('FORBIDDEN',maintenance.confirm,actor,{'preview_token':preview['preview_token'],'confirmed':True})
        self.code('INVALID_INPUT',maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':False})
        self.code('NOT_FOUND',maintenance.confirm,self.admin,{'preview_token':'x'*43,'confirmed':True})
        self.assertEqual(self.facts(),before)
        original_now=self.clock.now
        self.clock.now=preview['expires_at']+1
        self.code('TRANSITION_CLOSED',maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':True})
        self.clock.now=original_now
        self.call(services.create_block,self.admin,self.window)
        self.code('OCCUPANCY_CONFLICT',maintenance.preview,self.admin,self.window)
        self.code('OCCUPANCY_CONFLICT',maintenance.confirm,self.admin,{'preview_token':preview['preview_token'],'confirmed':True})

    def test_version_five_migration_preserves_weekly_history(self):
        legacy=Path(self.temp.name)/'v5.sqlite3'
        schema=Path(db.__file__).with_name('schema.sql').read_text()
        schema=schema.split('CREATE TABLE IF NOT EXISTS maintenance_previews')[0]
        with closing(db.connect(legacy)) as conn:
            conn.execute('PRAGMA journal_mode=WAL');conn.executescript(schema);conn.execute('PRAGMA user_version=5')
            conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'old','旧管理员','hash','admin',?)",(self.clock.now,))
            conn.execute("INSERT INTO rooms VALUES(1,'旧房间','旧楼',10,?,?)",(self.clock.now,self.clock.now))
        backup=Path(self.temp.name)/'v5-backup.sqlite3'
        migrate_database(legacy,backup)
        with closing(db.connect(legacy)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],db.SCHEMA_VERSION)
            self.assertEqual(conn.execute('SELECT count(*) FROM maintenance_previews').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT name FROM rooms').fetchone()[0],'旧房间')
        with closing(db.connect(backup)) as conn:self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],5)

    def test_twenty_approval_and_confirmation_races_have_one_complete_winner(self):
        with db.write_transaction(self.path) as conn:
            for room_id in range(3,23):
                conn.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?)',
                    (room_id,f'竞争房间{room_id}','2号楼',20,self.clock.now,self.clock.now))
        pairs=[]
        for room_id in range(3,23):
            payload=dict(room_id=room_id,title='待批准组会',purpose='研究',attendees=3,
                start=local_time(self.start)[:16],end=local_time(self.start+1800)[:16],
                intent_key=f'batch-race-app-{room_id:04}')
            item=self.call(applications.create_application,self.student,payload)['application']
            window=self.window|{'room_id':room_id,'end':local_time(self.start+1800)[:16]}
            preview=self.call(maintenance.preview,self.admin,window)
            pairs.append((room_id,item['id'],preview['preview_token']))
        def compete(task):
            room_id,application_id,token,action=task
            try:
                if action=='approve':self.call(applications.decide_application,self.teacher,application_id,'approve',{})
                else:self.call(maintenance.confirm,self.admin,{'preview_token':token,'confirmed':True})
                return room_id,action,'success'
            except DomainError as error:return room_id,action,error.code
        tasks=[(room_id,application_id,token,action) for room_id,application_id,token in pairs for action in ('approve','confirm')]
        with ThreadPoolExecutor(max_workers=20) as pool:results=list(pool.map(compete,tasks))
        for room_id,_,_ in pairs:
            outcomes=[result for result in results if result[0]==room_id]
            self.assertEqual(sum(result[2]=='success' for result in outcomes),1)
            with closing(db.connect(self.path)) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM reservations WHERE room_id=?',(room_id,)).fetchone()[0],1)
                self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE room_id=?',(room_id,)).fetchone()[0],1)


if __name__=='__main__':unittest.main()

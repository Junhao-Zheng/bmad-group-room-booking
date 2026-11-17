"""Cancellation requests keep occupancy and decisions atomic."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from booking_app import auth, create_app, db, applications, cancellations, services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError, local_time
from scripts.init_demo import seed_users
from tests.test_auth import accounts, FixedClock, ORIGIN


class CancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'test.db';self.clock=FixedClock()
        seed_users(self.path,accounts(),self.clock)
        self.actors={};self.clients={}
        with db.write_transaction(self.path) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'讨论室','研究楼',20,?,?)",(self.clock.now,self.clock.now))
            for row in conn.execute('SELECT * FROM users'):
                name=row['username'];token='token-'+name;digest=auth.token_digest(token)
                conn.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest,row['id'],'csrf-'+name,self.clock.now,self.clock.now+86400))
                self.actors[name]=auth.Actor(row['id'],row['display_name'],row['role'],digest)
        self.app=create_app({'TESTING':True,'DATABASE':str(self.path),'CLOCK':self.clock})
        for name in self.actors:
            client=self.app.test_client();client.set_cookie(auth.COOKIE_NAME,'token-'+name,domain='127.0.0.1');self.clients[name]=client
        self.student=self.actors['demo_member_a'];self.teacher=self.actors['demo_teacher_a']
        self.other=self.actors['demo_teacher_b'];self.admin=self.actors['demo_admin']
        start=(self.clock.now//1800+2)*1800
        self.payload=dict(room_id=1,title='讨论',purpose='研究',attendees=3,start=local_time(start)[:16],end=local_time(start+3600)[:16],intent_key='cancellation-test-0001')
        with self.app.app_context():
            item=applications.create_application(self.student,self.payload)['application']
            self.booking_id=applications.decide_application(self.teacher,item['id'],'approve',{})['reservation_id']

    def call(self,func,*args):
        with self.app.app_context():return func(*args)

    def facts(self):
        with closing(db.connect(self.path)) as conn:
            return {name:[dict(row) for row in conn.execute(f'SELECT * FROM {name} ORDER BY 1')]
                    for name in ('reservations','occupancy_slots','cancellation_requests','audit_events')}

    def code(self,expected,func,*args):
        with self.assertRaises(DomainError) as raised:self.call(func,*args)
        self.assertEqual(raised.exception.code,expected)

    def test_request_approval_replay_and_audit(self):
        created=self.call(cancellations.create_request,self.student,self.booking_id)
        self.assertFalse(created['replayed']);request=created['cancellation_request']
        self.assertEqual(request['status'],'awaiting_approval')
        self.assertEqual(request['room_id'],1)
        self.assertEqual(self.call(cancellations.list_requests,self.teacher)['items'][0]['id'],request['id'])
        self.assertEqual(self.call(cancellations.list_requests,self.other)['total'],0)
        self.assertEqual(len(self.facts()['occupancy_slots']),2)
        self.assertTrue(self.call(cancellations.create_request,self.student,self.booking_id)['replayed'])
        approved=self.call(cancellations.decide_request,self.teacher,request['id'],'approve',{})
        self.assertEqual(approved['status'],'approved')
        self.assertEqual(self.call(cancellations.decide_request,self.teacher,request['id'],'approve',{}),approved)
        facts=self.facts();self.assertEqual(facts['occupancy_slots'],[])
        self.assertEqual(facts['reservations'][0]['cancelled_by'],self.teacher.id)
        self.assertEqual([event['action'] for event in facts['audit_events']][-3:],
                         ['cancellation_request.created','booking.cancelled_by_supervisor','cancellation_request.approved'])
        self.assertEqual(self.call(cancellations.list_requests,self.student)['total'],1)
        self.assertEqual(self.call(cancellations.list_requests,self.other)['total'],0)
        self.assertEqual(self.call(services.audit_events,self.admin,'cancellation_request')['total'],2)

    def test_reject_retry_expiry_and_authorization(self):
        request=self.call(cancellations.create_request,self.student,self.booking_id)['cancellation_request']
        before=self.facts()
        for actor in (self.other,self.admin,self.student):
            self.code('NOT_FOUND',cancellations.decide_request,actor,request['id'],'approve',{})
        self.assertEqual(self.facts(),before)
        rejected=self.call(cancellations.decide_request,self.teacher,request['id'],'reject',{'reason':'原计划保留'})
        self.assertEqual(rejected['status'],'rejected')
        self.code('TRANSITION_CLOSED',cancellations.decide_request,self.teacher,request['id'],'approve',{})
        second=self.call(cancellations.create_request,self.student,self.booking_id)['cancellation_request']
        self.assertNotEqual(second['id'],request['id'])
        self.clock.now=second['start_at']
        self.code('TRANSITION_CLOSED',cancellations.decide_request,self.teacher,second['id'],'approve',{})
        self.assertEqual(len(self.facts()['occupancy_slots']),2)

    def test_admin_supersedes_and_audit_failure_rolls_back(self):
        request=self.call(cancellations.create_request,self.student,self.booking_id)['cancellation_request']
        before=self.facts()
        def fail(conn,event):
            audit_writer(conn,event)
            if event['action']=='cancellation_request.approved':raise RuntimeError('injected')
        self.app.config['AUDIT_WRITER']=fail
        with self.assertRaises(RuntimeError):self.call(cancellations.decide_request,self.teacher,request['id'],'approve',{})
        self.assertEqual(self.facts(),before)
        self.app.config['AUDIT_WRITER']=audit_writer
        self.call(services.admin_cancel_booking,self.admin,self.booking_id,'管理干预')
        facts=self.facts();self.assertEqual(facts['cancellation_requests'][0]['status'],'superseded')
        self.assertEqual(facts['occupancy_slots'],[])
        self.code('TRANSITION_CLOSED',cancellations.decide_request,self.teacher,request['id'],'approve',{})
        self.assertEqual(self.facts(),facts)

    def test_twenty_competing_decisions_and_http(self):
        client=self.clients['demo_member_a']
        response=client.post(f'/api/bookings/{self.booking_id}/cancellation-requests',base_url=ORIGIN,json={},headers={'Origin':ORIGIN,'X-CSRF-Token':'csrf-demo_member_a'})
        self.assertEqual(response.status_code,201)
        request=response.json['data']['cancellation_request']
        self.assertEqual(client.get('/api/cancellation-requests',base_url=ORIGIN).json['data']['total'],1)
        def decide(index):
            try:
                if index%2:self.call(services.admin_cancel_booking,self.admin,self.booking_id,'竞争干预')
                else:self.call(cancellations.decide_request,self.teacher,request['id'],'approve',{})
            except DomainError as error:return error.code
        with ThreadPoolExecutor(max_workers=20) as pool:list(pool.map(decide,range(20)))
        facts=self.facts();self.assertEqual(facts['occupancy_slots'],[])
        self.assertEqual(sum(event['action'].startswith('booking.cancelled_') for event in facts['audit_events']),1)
        self.assertIn(facts['cancellation_requests'][0]['status'],('approved','superseded'))


if __name__=='__main__':unittest.main()

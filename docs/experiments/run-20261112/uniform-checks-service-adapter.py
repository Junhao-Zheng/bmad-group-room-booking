"""One withheld, identical acceptance probe for both original Experiment A outputs.
Run from each isolated project's interpreter; it never modifies source files.
UI and real-HTTP race evidence are assessed separately against the frozen rubric.
"""
import argparse,contextlib,hashlib,json,re,secrets,sqlite3,sys,tempfile,unittest
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--group',choices=['X','Y'],required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
root=args.project.resolve();sys.path.insert(0,str(root))
from booking_app import auth,create_app,db,services
from booking_app.audit import audit_writer
from booking_app.domain import DomainError
from scripts.init_demo import DEMO_IDENTITIES,seed_users
from tests.history_fixtures import FixedClock
from tests.schedule_fixtures import NOW,insert_record
KIND='booking' if args.group=='X' else 'block'
COMMAND='admin_cancel_booking' if KIND=='booking' else 'revoke_block'
# Invocation adapter only: X takes reason; Y takes a payload. Acceptance assertions unchanged.
def service_input(reason):return reason if args.group=='X' else {'reason':reason}
PREFIX='/api/admin/bookings/' if KIND=='booking' else '/api/admin/blocks/'
SUFFIX='/cancel' if KIND=='booking' else '/revoke'
FULL_COMMON={'id','room','start_at','start_local','end_at','end_local','status','created_at','created_local'}
FULL_KEYS=FULL_COMMON|({'title','purpose','attendees','owner_id','owner_display_name','cancelled_at','cancelled_local','cancelled_by_id','cancelled_by_display_name','cancel_reason'} if KIND=='booking' else {'creator_id','creator_display_name','reason','revoked_at','revoked_local','revoked_by_id','revoked_by_display_name','revoke_reason'})
ORIGIN='http://127.0.0.1:8000'

class UniformChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed_dir=tempfile.TemporaryDirectory();cls.seed_db=Path(cls.seed_dir.name)/'seed.sqlite3';cls.password=secrets.token_urlsafe(24)
  seed_users(cls.seed_db,[dict(username=u,display_name=d,role=r,password=cls.password) for u,d,r in (*DEMO_IDENTITIES,('demo_admin_second','合成管理员乙','admin'))],FixedClock())
  with db.write_transaction(cls.seed_db) as conn:
   for room_id in (50,51):conn.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?)',(room_id,f'统一评审 {room_id}','合成楼',20,NOW,NOW))
   for record_id,start,end in [(9001,'12:00','13:00'),(9002,'09:00','11:00'),(9003,'08:00','09:00')]:
    insert_record(conn,record_id,50,'2026-11-12T'+start,'2026-11-12T'+end,kind=KIND,owner_id=1)
   insert_record(conn,9010,51,'2026-11-12T12:00','2026-11-12T13:00',kind='block' if KIND=='booking' else 'booking',owner_id=1)
 @classmethod
 def tearDownClass(cls):cls.seed_dir.cleanup()
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.database=Path(tmp.name)/'case.sqlite3'
  src,dest=db.connect(self.seed_db),db.connect(self.database)
  try:src.backup(dest)
  finally:src.close();dest.close()
  self.clock=FixedClock();self.app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
  self.client,self.identity=self.login('demo_admin')
 def login(self,name):
  client=self.app.test_client();page=client.get('/login',base_url=ORIGIN)
  csrf=re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
  result=client.post('/api/login',base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},json={'username':name,'password':self.password})
  self.assertEqual(result.status_code,200);return client,result.json['data']
 def call(self,record=9001,reason=' 合成评审原因 ',client=None,identity=None,headers=None):
  return (client or self.client).post(PREFIX+str(record)+SUFFIX,base_url=ORIGIN,
   headers=headers if headers is not None else {'Origin':ORIGIN,'X-CSRF-Token':(identity or self.identity)['csrf_token']},json={'reason':reason})
 def facts(self):
  with db.read_transaction(self.database) as conn:
   self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
   return {table:[dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY 1,2')] for table in ('rooms','reservations','occupancy_slots','audit_events')}
 def error(self,response,status,code):
  self.assertEqual(response.status_code,status);self.assertEqual(set(response.json),{'ok','error'});self.assertIs(response.json['ok'],False)
  self.assertEqual(set(response.json['error']),{'code','message','fields','conflicts'});self.assertEqual(response.json['error']['code'],code)
 def test_A1_anonymous(self):
  before=self.facts();self.error(self.call(client=self.app.test_client()),401,'AUTH_REQUIRED');self.assertEqual(self.facts(),before)
 def test_A1_member_before_bad_id_reason(self):
  client,identity=self.login('demo_member_a');before=self.facts();self.error(self.call('bad','',client,identity),403,'FORBIDDEN');self.assertEqual(self.facts(),before)
 def test_A1_expired(self):
  before=self.facts();self.clock.now+=auth.SESSION_SECONDS;self.error(self.call(),401,'AUTH_REQUIRED');self.assertEqual(self.facts(),before)
 def test_A1_logged_out(self):
  token=self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value
  self.assertEqual(self.client.post('/api/logout',base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']},json={}).status_code,200)
  self.client.set_cookie(auth.COOKIE_NAME,token,domain='127.0.0.1');before=self.facts();self.error(self.call(),401,'AUTH_REQUIRED');self.assertEqual(self.facts(),before)
 def test_A1_demoted_and_forged_actor_service(self):
  with self.app.app_context():
   actor=auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value);command=getattr(services,COMMAND)
   for invalid in (None,replace(actor,id=1),replace(actor,session_token_hash='0'*64)):
    with self.subTest(case='forged_actor'):
     before=self.facts()
     with self.assertRaises(DomainError) as caught:command(invalid,9001,service_input('合成原因'))
     self.assertEqual(caught.exception.code,'AUTH_REQUIRED');self.assertEqual(self.facts(),before)
   with db.write_transaction(self.database) as conn:conn.execute("UPDATE users SET role='member' WHERE id=?",(actor.id,))
   before=self.facts()
   with self.assertRaises(DomainError) as caught:command(actor,9001,service_input('合成原因'))
   self.assertEqual(caught.exception.code,'FORBIDDEN');self.assertEqual(self.facts(),before)
  self.error(self.call('bad',''),403,'FORBIDDEN')
 def test_A2_invalid_reasons_initial_and_repeat(self):
  for repeated in (False,True):
   if repeated:self.assertEqual(self.call().status_code,200)
   before=self.facts()
   for reason in ('',' \u0085 ','长'*501,7,True,None,[],{},'x\x00y','x\ud800'):
    with self.subTest(repeated=repeated,case=type(reason).__name__):self.error(self.call(reason=reason),400,'INVALID_INPUT');self.assertEqual(self.facts(),before)
 def test_A2_length_one_and_500(self):
  for record,reason in [(9001,' 单 '),(9002,'  '+'🧪'*500+'  ')]:
   response=self.call(record,reason);self.assertEqual(response.status_code,200)
   key='cancel_reason' if KIND=='booking' else 'revoke_reason';self.assertEqual(response.json['data'][key],reason.strip())
 def test_A2_strict_path_and_wrong_kind(self):
  before=self.facts()
  for record in ('0','01','-1','1.0','bad',str(2**63),'9'*5000):
   with self.subTest(case=record[:20]):self.error(self.call(record),400,'INVALID_INPUT')
  for record in (9010,2**63-1):self.error(self.call(record),404,'NOT_FOUND')
  self.assertEqual(self.facts(),before)
 def test_A3_pending_in_progress_and_exact_end(self):
  for record in (9001,9002):self.assertEqual(self.call(record).status_code,200)
  before=self.facts();self.error(self.call(9003),409,'TRANSITION_CLOSED');self.assertEqual(self.facts(),before)
 def test_A3_first_exact_end(self):
  self.clock.now=NOW+10800;before=self.facts();self.error(self.call(),409,'TRANSITION_CLOSED');self.assertEqual(self.facts(),before)
 def test_A3_one_clock_after_write_lock(self):
  with self.app.app_context():
   actor=auth.actor_for_token(self.client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value);original=db.write_transaction;self.clock.calls=0
   @contextlib.contextmanager
   def advance(database=None):
    with original(database) as conn:self.clock.now=NOW+10800;yield conn
   before=self.facts()
   with patch.object(db,'write_transaction',advance),self.assertRaises(DomainError) as caught:getattr(services,COMMAND)(actor,9001,service_input('合成原因'))
   self.assertEqual(caught.exception.code,'TRANSITION_CLOSED');self.assertEqual(self.clock.calls,1);self.assertEqual(self.facts(),before)
 def test_A4_repeat_other_admin_after_end_preserves_first(self):
  first=self.call(reason='首次原因');self.assertEqual(first.status_code,200);before=self.facts();self.clock.now=NOW+10801
  other,identity=self.login('demo_admin_second');again=self.call(reason='后续不能覆盖',client=other,identity=identity)
  self.assertEqual(again.status_code,200);self.assertEqual(again.json,first.json);self.assertEqual(self.facts(),before)
 def test_A5_A7_exact_full_dto_history_and_slot_release(self):
  before=self.facts();response=self.call();self.assertEqual(response.status_code,200);self.assertEqual(set(response.json),{'ok','data'});self.assertIs(response.json['ok'],True)
  dto=response.json['data'];self.assertEqual(set(dto),FULL_KEYS);self.assertEqual(set(dto['room']),{'id','name','location','capacity'});self.assertEqual(dto['id'],9001)
  after=self.facts();old=next(r for r in before['reservations'] if r['id']==9001);new=next(r for r in after['reservations'] if r['id']==9001)
  self.assertEqual(new,old|{'cancelled_at':NOW,'cancelled_by':3,'cancel_reason':'合成评审原因'})
  self.assertEqual(after['occupancy_slots'],[r for r in before['occupancy_slots'] if r['reservation_id']!=9001]);self.assertEqual(after['rooms'],before['rooms'])
  self.assertEqual([r for r in after['reservations'] if r['id']!=9001],[r for r in before['reservations'] if r['id']!=9001])
  self.assertEqual(dto['status'],'cancelled' if KIND=='booking' else 'revoked')
  stem='cancelled' if KIND=='booking' else 'revoked';self.assertEqual(dto[stem+'_at'],NOW);self.assertEqual(dto[stem+'_local'],'2026-11-12T10:00:00+08:00');self.assertEqual(dto[stem+'_by_id'],3)
  if KIND=='block':self.assertEqual(dto['reason'],old['reason'])
 def test_A6_same_connection_once_and_snapshots(self):
  before=self.facts();connections=[];events=[];original=db.write_transaction
  @contextlib.contextmanager
  def track(database=None):
   with original(database) as conn:connections.append(conn);yield conn
  def writer(conn,event):
   self.assertIs(conn,connections[-1]);self.assertTrue(conn.in_transaction);self.assertEqual(conn.execute('SELECT count(*) FROM occupancy_slots WHERE reservation_id=9001').fetchone()[0],0)
   events.append(event);audit_writer(conn,event)
  self.app.config['AUDIT_WRITER']=writer
  with patch.object(db,'write_transaction',track):self.assertEqual(self.call().status_code,200)
  self.assertEqual(len(events),1);event=events[0];self.assertEqual(event['action'],'booking.cancelled_by_admin' if KIND=='booking' else 'block.revoked');self.assertEqual(event['target_type'],KIND)
  self.assertEqual(event['actor_id'],3);self.assertEqual(event['actor_display_name'],'演示管理员');self.assertEqual(event['target_id'],9001);self.assertEqual(event['occurred_at'],NOW);self.assertEqual(event['reason'],'合成评审原因')
  self.assertIsInstance(event['before'],dict);self.assertIsInstance(event['after'],dict);self.assertEqual(event['before']['id'],9001);self.assertEqual(event['after']['id'],9001)
  self.assertEqual(len(self.facts()['audit_events']),len(before['audit_events'])+1)
  self.assertEqual(self.call().status_code,200);self.assertEqual(len(events),1)
 def test_A6_audit_before_after_insert_failures(self):
  before=self.facts()
  for inserted in (False,True):
   def fail(conn,event):
    if inserted:audit_writer(conn,event)
    raise RuntimeError('SENSITIVE_SENTINEL_NOT_FOR_OUTPUT')
   self.app.config['AUDIT_WRITER']=fail
   with self.assertLogs(self.app.logger,level='ERROR') as logs:self.error(self.call(),500,'INTERNAL_ERROR')
   self.assertNotIn('SENSITIVE_SENTINEL',str(logs.output));self.assertEqual(self.facts(),before)
 def test_A6_commit_failure_rollback(self):
  before=self.facts();connect=db.connect
  class FailCommit:
   def __init__(self,conn):self.conn=conn
   def __getattr__(self,name):return getattr(self.conn,name)
   def execute(self,sql,*a):
    if sql=='COMMIT':raise sqlite3.OperationalError('SENSITIVE_SENTINEL_NOT_FOR_OUTPUT')
    return self.conn.execute(sql,*a)
  with patch.object(db,'connect',lambda *a,**kw:FailCommit(connect(*a,**kw))),self.assertLogs(self.app.logger,level='ERROR'):self.error(self.call(),500,'INTERNAL_ERROR')
  self.assertEqual(self.facts(),before)
 def test_A7_origin_csrf_and_shape(self):
  before=self.facts()
  for headers in ({},{'Origin':'http://evil.test','X-CSRF-Token':self.identity['csrf_token']},{'Origin':ORIGIN,'X-CSRF-Token':'bad'}):
   self.error(self.call(headers=headers),403,'CSRF_REJECTED')
  for value in ([],7,'reason'):
   response=self.client.post(PREFIX+'9001'+SUFFIX,base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':self.identity['csrf_token']},json=value);self.error(response,400,'INVALID_INPUT')
  self.assertEqual(self.facts(),before)

class SafeResult(unittest.TestResult):
 def __init__(self):super().__init__();self.rows=[]
 def addSuccess(self,test):super().addSuccess(test);self.rows.append({'test':test.id(),'result':'PASS'})
 def _safe(self,test,err,label):
  coords=[];trace=err[2]
  while trace:
   f=Path(trace.tb_frame.f_code.co_filename)
   if f.resolve()==Path(__file__).resolve() or f.resolve().is_relative_to(root/'booking_app'):
    coords.append({'file':str(f.relative_to(root)) if f.is_relative_to(root) else f.name,'line':trace.tb_lineno})
   trace=trace.tb_next
  self.rows.append({'test':test.id(),'result':label,'error_type':err[0].__name__,'locations':coords})
 def addFailure(self,test,err):self.failures.append((test,'details omitted'));self._safe(test,err,'FAIL')
 def addError(self,test,err):self.errors.append((test,'details omitted'));self._safe(test,err,'ERROR')
 def addSubTest(self,test,subtest,err):
  if err is not None:self.failures.append((subtest,'details omitted'));self._safe(subtest,err,'FAIL')

out=args.output.resolve();assert not out.exists(),'Do not overwrite a measured run';out.parent.mkdir(parents=True,exist_ok=True)
started=datetime.now(timezone.utc).isoformat();result=SafeResult();unittest.defaultTestLoader.loadTestsFromTestCase(UniformChecks).run(result)
report={'protocol':'experiment-a-uniform-review-v1','group':args.group,'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'tests_run':result.testsRun,'result':'PASS' if result.wasSuccessful() else 'FAIL','failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'checks':result.rows,'scope':'A1–A7 executable supplement; does not replace UI, full snapshots/source review, real HTTP races or regression evidence.'}
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2));sys.exit(0 if result.wasSuccessful() else 1)

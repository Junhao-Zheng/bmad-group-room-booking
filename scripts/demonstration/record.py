"""Record a real ten-minute browser demonstration against an isolated synthetic database."""
import argparse, functools, hashlib, http.server, json, os, re, secrets, socket, subprocess, sys, tempfile, threading, time
from datetime import datetime, timezone
from pathlib import Path
WORK=Path(__file__).resolve().parent
REPO=WORK.parent.parent
sys.path.insert(0,str(REPO))
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from tests.history_fixtures import FixedClock
from tests.schedule_fixtures import NOW
from booking_app import auth,create_app,db,services
from scripts.verify_history_browser import stop_process_group, browser_wrapper, run_driver

class QuietHandler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass

def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def fingerprint():
 return {str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO/'booking_app').rglob('*')) if p.is_file() and p.suffix in {'.py','.sql','.js','.css','.html'}}
def seed_demonstration(database,users):
 """Create readable synthetic history through the real business services, one day earlier."""
 clock=FixedClock();clock.now=NOW-86400
 seed_users(database,users,clock);app=create_app({'TESTING':True,'DATABASE':str(database),'CLOCK':clock})
 origin='http://127.0.0.1:8000'
 def actor(username):
  user=next(u for u in users if u['username']==username);client=app.test_client()
  page=client.get('/login',base_url=origin);csrf=re.search(r'name="csrf_token" value="([^"]+)"',page.text).group(1)
  result=client.post('/api/login',base_url=origin,headers={'Origin':origin,'X-CSRF-Token':csrf},json={'username':username,'password':user['password']})
  assert result.status_code==200
  return auth.actor_for_token(client.get_cookie(auth.COOKIE_NAME,domain='127.0.0.1').value)
 with app.app_context():
  admin=actor('demo_admin');member=actor('demo_member_a');other=actor('demo_member_b')
  rooms=[services.create_room(admin,dict(name=name,location=location,capacity=capacity)) for name,location,capacity in [('研讨室 A','科研楼 301',12),('讨论室 B','科研楼 302',8),('视频会议室','科研楼 305',16)]]
  reservations=[]
  for owner,room,start,end,title,purpose,count in [
   (member,rooms[0],'2026-11-13T10:00','2026-11-13T11:00','研究进展讨论','交换实验进展与下周计划',6),
   (other,rooms[1],'2026-11-13T14:00','2026-11-13T15:00','论文讨论小组','讨论方法与复现实验',5),
   (member,rooms[2],'2026-11-12T09:30','2026-11-12T10:30','远程合作交流','与合作方核对数据处理方案',8),
   (member,rooms[0],'2026-11-13T16:00','2026-11-13T17:00','已取消的方案讨论','合成历史示例',4)]:
   reservations.append(services.create_booking(owner,dict(room_id=room['id'],start=start,end=end,title=title,purpose=purpose,attendees=count,intent_key='demo-seed-booking-intent-'+str(len(reservations))))['booking'])
  services.member_cancel_booking(member,reservations[-1]['id'])
  services.create_block(admin,dict(room_id=rooms[1]['id'],start='2026-11-14T09:00',end='2026-11-14T12:00',reason='投影设备维护'))
 with db.write_transaction(database) as conn:conn.execute('DELETE FROM sessions')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--scenes',type=Path,required=True);parser.add_argument('--viewer',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--browser-executable',type=Path,required=True);parser.add_argument('--ffmpeg-executable',type=Path,help='Optional tested FFmpeg supplied in a private Playwright recorder cache');parser.add_argument('--preflight',action='store_true',help='Run actions quickly without recording or claiming a ten-minute video');a=parser.parse_args()
 scenes=json.loads(a.scenes.read_text());assert scenes['status']=='FINAL_AUDITED'
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip();assert head==scenes['source_commit']
 output=a.output.resolve();assert not output.exists(),'Preserve earlier recordings';output.mkdir(parents=True)
 facts={'result':'INCOMPLETE','source_commit':head,'started_at_utc':datetime.now(timezone.utc).isoformat(),'app_files_sha256':fingerprint(),
  'scenes_sha256':hashlib.sha256(a.scenes.read_bytes()).hexdigest(),'viewer_sha256':hashlib.sha256(a.viewer.read_bytes()).hexdigest(),
  'data':'isolated synthetic fixture','operator':'AI browser automation','narration':'synthetic; composed separately','mode':'preflight' if a.preflight else 'recording','runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'driver_sha256':hashlib.sha256((WORK/'record.cjs').read_bytes()).hexdigest()}
 target=output/'runner.json';target.write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
 with tempfile.TemporaryDirectory(prefix='grb-course-recording-') as directory:
  tmp=Path(directory);viewer=tmp/'viewer';viewer.mkdir();(viewer/'index.html').write_bytes(a.viewer.read_bytes())
  users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
  credentials=tmp/'demo.credentials.json';credentials.touch(mode=0o600);credentials.write_text(json.dumps({'users':users}))
  database=tmp/'demo.sqlite3';seed_demonstration(database,users)
  app_port=free_port();origin=f'http://127.0.0.1:{app_port}'
  env=dict(os.environ,BOOKING_DB_PATH=str(database),APP_ORIGIN=origin,COOKIE_SECURE='false',TRUSTED_HOSTS='127.0.0.1',NODE_PATH=str(REPO/'work/browser-tools/node_modules'))
  if a.ffmpeg_executable:
   binary=a.ffmpeg_executable.resolve(strict=True)
   browsers=json.loads((REPO/'work/browser-tools/node_modules/playwright-core/browsers.json').read_text())['browsers']
   revision=next(item['revision'] for item in browsers if item['name']=='ffmpeg')
   cache=tmp/'recorder-cache';directory=cache/f'ffmpeg-{revision}';directory.mkdir(parents=True)
   filename='ffmpeg-mac' if sys.platform=='darwin' else 'ffmpeg-win64.exe' if sys.platform=='win32' else 'ffmpeg-linux'
   (directory/filename).symlink_to(binary)
   env['PLAYWRIGHT_BROWSERS_PATH']=str(cache)
   facts['recorder_ffmpeg']={'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'version':subprocess.check_output([str(binary),'-version'],text=True).splitlines()[0],'selection':'explicit executable in isolated temporary cache; not the Playwright-distributed build','playwright_registry_revision':revision}
   target.write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
  handler=functools.partial(QuietHandler,directory=str(viewer));httpd=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
  thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
  with (tmp/'server.log').open('w') as log:
   server=subprocess.Popen([sys.executable,'-m','waitress',f'--listen=127.0.0.1:{app_port}','--threads=8','--call','scripts.verify_auth_browser:create_schedule_verification_app'],cwd=REPO,env=env,stdout=log,stderr=log,start_new_session=True)
   try:
    for _ in range(100):
     if server.poll() is not None:raise RuntimeError('Demonstration server exited')
     try:
      with socket.create_connection(('127.0.0.1',app_port),timeout=.1):break
     except OSError:time.sleep(.05)
    else:raise RuntimeError('Demonstration server startup timed out')
    wrapper,registry=browser_wrapper(tmp,a.browser_executable.resolve())
    result=run_driver(['node',str(WORK/'record.cjs'),str(a.scenes.resolve()),f'http://127.0.0.1:{httpd.server_port}',origin,str(credentials),str(output),str(wrapper),*(['--preflight'] if a.preflight else [])],env,registry,timeout=700)
    (output/'driver-progress.jsonl').write_text(result.stdout)
    if result.returncode:raise RuntimeError('Browser recording failed; inspect its INCOMPLETE report')
    assert fingerprint()==facts['app_files_sha256'],'Application changed during recording'
    recording=json.loads((output/'recording.json').read_text());assert recording['result']=='PASS'
    assert recording['mode']==('preflight' if a.preflight else 'recording')
    if not a.preflight:assert recording['actual_recording_seconds']>=600
   finally:
    stop_process_group(server.pid,server);httpd.shutdown();httpd.server_close();thread.join(timeout=3)
 facts.update(result='PASS',completed_at_utc=datetime.now(timezone.utc).isoformat(),)
 if not a.preflight:facts['video_sha256']=hashlib.sha256((output/'actual-browser.webm').read_bytes()).hexdigest()
 target.write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'result':'PASS','output':str(output)},ensure_ascii=False))
if __name__=='__main__':main()

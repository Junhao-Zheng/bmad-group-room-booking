"""Story 3.4: real production Waitress restart, all-route permissions and private backups."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from zoneinfo import ZoneInfo

from booking_app import ROOT, create_app, db
from booking_app.domain import SystemClock
from scripts.backup_db import backup_database
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_availability_performance import Client, environment, write_json
from scripts.verify_history_browser import stop_process_group

TABLES=('rooms','reservations','occupancy_slots','audit_events')

def source_hashes():
    files=[p for folder in ('booking_app','scripts') for p in (ROOT/folder).rglob('*') if p.suffix in ('.py','.js','.cjs','.html','.css','.sql')]
    files += [ROOT / name for name in ('tests/legacy_fixture.py', 'tests/fixtures/schema_v1.sql')]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def facts(database):
    with db.read_transaction(database) as conn:
        result={table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1,2')] for table in TABLES}
        result['schema_version']=conn.execute('PRAGMA user_version').fetchone()[0]
        assert conn.execute('PRAGMA integrity_check').fetchall()[0][0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    for record in result['reservations']:
        slots=[s for s in result['occupancy_slots'] if s['reservation_id']==record['id']]
        assert all(s['room_id']==record['room_id'] for s in slots)
        assert sorted(s['slot_start'] for s in slots)==([] if record['cancelled_at'] is not None else list(range(record['start_at'],record['end_at'],1800)))
    return result

def evidence_facts(value):
    return dict(counts={table:len(value[table]) for table in TABLES},schema_version=value['schema_version'],
        business_and_relationship_sha256=digest(value),
        **{table:[{k:v for k,v in row.items() if k!='intent_key'} | ({'intent_key_sha256':hashlib.sha256(row['intent_key'].encode()).hexdigest()} if row.get('intent_key') else {}) for row in value[table]] for table in TABLES})

class LiveServer:
    def __init__(self,database,temporary):
        with socket.socket() as probe:probe.bind(('127.0.0.1',0));self.port=probe.getsockname()[1]
        self.origin=f'http://127.0.0.1:{self.port}';self.database=database;self.temporary=temporary;self.process=None;self.pids=[]
        self.command=[sys.executable,'-m','waitress',f'--listen=127.0.0.1:{self.port}','--threads=8','--call','booking_app:create_app']
    def start(self):
        env=dict(os.environ,BOOKING_DB_PATH=str(self.database),APP_ORIGIN=self.origin,COOKIE_SECURE='false',TRUSTED_HOSTS='127.0.0.1')
        self.log=(self.temporary/f'waitress-{len(self.pids)}.log').open('w')
        self.process=subprocess.Popen(self.command,cwd=ROOT,env=env,stdout=self.log,stderr=self.log,start_new_session=True);self.pids.append(self.process.pid)
        for _ in range(200):
            if self.process.poll() is not None:raise RuntimeError('Waitress startup failed')
            try:
                with socket.create_connection(('127.0.0.1',self.port),timeout=.1):return
            except OSError:time.sleep(.025)
        raise RuntimeError('Waitress startup timeout')
    def stop(self):
        if self.process is not None:
            stop_process_group(self.process.pid,self.process);assert self.process.poll() is not None;self.log.close();self.process=None


def populate(server,users,output):
    clients=[Client(server.origin) for _ in users]
    for client,user in zip(clients,users):client.login(user)
    member,_,admin=clients;steps=[]
    def call(client,path,payload=None,status=200):
        code,body,elapsed=client.request(path,payload)
        steps.append(dict(path=path,status=code,response=body,duration_ms=elapsed));write_json(output/'operations.json',steps)
        assert code==status
        return body['data']
    room=call(admin,'/api/admin/rooms',dict(name='<img src=x onerror="window.auditXss=1">合成房间',location='L',capacity=20),201)
    call(admin,f"/api/admin/rooms/{room['id']}",dict(name=room['name'],location='已修改 <script>text</script>',capacity=18))
    day=(datetime.now(ZoneInfo('Asia/Shanghai'))+timedelta(days=1)).date()
    payload=dict(room_id=room['id'],title='合成审计活动',purpose='<svg onload="window.auditXss=2">'+'证据'*200,attendees=4,
        start=f'{day}T12:00',end=f'{day}T13:00',intent_key=secrets.token_urlsafe(32))
    first=call(member,'/api/bookings',payload,201)['booking'];call(member,f"/api/bookings/{first['id']}/cancel",{})
    second=call(member,'/api/bookings',payload|dict(intent_key=secrets.token_urlsafe(32)),201)['booking']
    call(admin,f"/api/admin/bookings/{second['id']}/cancel",dict(reason='管理员取消 <img src=x>'+'长'*200))
    block_payload=dict(room_id=room['id'],start=payload['start'],end=payload['end'],reason='合成维护')
    block=call(admin,'/api/admin/blocks',block_payload,201);call(admin,f"/api/admin/blocks/{block['id']}/revoke",dict(reason='完成维护'))
    call(member,'/api/bookings',payload|dict(intent_key=secrets.token_urlsafe(32)),201)
    call(admin,'/api/admin/blocks',block_payload|dict(start=f'{day+timedelta(days=1)}T12:00',end=f'{day+timedelta(days=1)}T14:00'),201)
    before=facts(server.database)
    call(member,'/api/bookings',payload);call(member,f"/api/bookings/{first['id']}/cancel",{})
    call(admin,f"/api/admin/bookings/{second['id']}/cancel",dict(reason='ignored'))
    call(admin,f"/api/admin/blocks/{block['id']}/revoke",dict(reason='ignored'))
    call(admin,f"/api/admin/rooms/{room['id']}",dict(name=room['name'],location='已修改 <script>text</script>',capacity=18))
    assert facts(server.database)==before
    audits=call(admin,'/api/admin/audit')
    assert audits['total']==10 and len({e['action'] for e in audits['items']})==7
    return clients,payload,first['id']

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def permission_matrix(server,users,booking_id,output):
    get_paths=['/login','/','/my','/admin','/static/app.css','/api/me','/api/rooms','/api/availability?start=bad',
        '/api/schedule?room_id=1&date=2000-01-01','/api/bookings/mine',f'/api/bookings/{booking_id}',
        '/api/admin/bookings','/api/admin/blocks','/api/admin/audit']
    post_paths=['/api/login','/api/bookings',f'/api/bookings/{booking_id}/cancel',
        f'/api/admin/bookings/{booking_id}/cancel','/api/admin/rooms','/api/admin/rooms/1',
        '/api/admin/blocks','/api/admin/blocks/3/revoke','/api/logout']
    # Every implemented application route is represented, including HTML and auth routes.
    app=create_app({'DATABASE':str(server.database),'APP_ORIGIN':server.origin})
    expected_rules={'/login','/','/my','/admin','/static/<path:filename>','/api/me','/api/rooms','/api/availability','/api/schedule',
        '/api/bookings/mine','/api/bookings/<booking_id>','/api/admin/bookings','/api/admin/blocks','/api/admin/audit',
        '/api/login','/api/bookings','/api/bookings/<booking_id>/cancel','/api/admin/bookings/<booking_id>/cancel',
        '/api/admin/rooms','/api/admin/rooms/<room_id>','/api/admin/blocks/<block_id>/revoke','/api/logout'}
    assert {r.rule for r in app.url_map.iter_rules()}==expected_rules
    before=facts(server.database);matrix=[]
    for role in ('anonymous','expired','logged_out','member_a','member_b','admin'):
        client=Client(server.origin)
        client.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(client.jar),NoRedirect())
        if role!='anonymous':
            client.login(users[2] if role in ('admin','expired','logged_out') else users[0 if role=='member_a' else 1])
            if role=='expired':
                from booking_app.auth import token_digest
                raw=next(c.value for c in client.jar if c.name=='grb_session')
                with db.write_transaction(server.database) as conn:conn.execute('UPDATE sessions SET created_at=?,expires_at=? WHERE token_hash=?',(int(time.time())-1,int(time.time()),token_digest(raw)))
            if role=='logged_out':
                old=list(client.jar);assert client.request('/api/logout',{})[0]==200
                for cookie in old:client.jar.set_cookie(cookie)
        authenticated=role in ('member_a','member_b','admin')
        for method,paths in (('GET',get_paths),('POST',post_paths)):
            for path in paths:
                status,body,_=client.request(path,{} if method=='POST' else None)
                if path.startswith('/static'):expected=200
                elif path=='/login':expected=302 if authenticated else 200
                elif path in ('/','/my','/admin'):
                    expected=302 if not authenticated else 403 if path=='/admin' and role!='admin' else 200
                elif path=='/api/login':expected=401 if authenticated else 403  # GET /login rotated invalid credentials, old CSRF rejected.
                elif not authenticated:expected=401
                elif path.startswith('/api/admin') and role!='admin':expected=403
                elif method=='POST':
                    expected=200 if path=='/api/logout' or path==f'/api/bookings/{booking_id}/cancel' and role=='member_a' else 404 if path==f'/api/bookings/{booking_id}/cancel' else 400
                elif path.startswith('/api/availability'):expected=400
                elif path==f'/api/bookings/{booking_id}' and role=='member_b':expected=404
                else:expected=200
                matrix.append(dict(role=role,method=method,path=path,status=status,expected=expected,code=body.get('error',{}).get('code') if isinstance(body,dict) else None))
                write_json(output/'permissions.json',matrix)
                assert status==expected,(role,method,path,status,expected)
    assert facts(server.database)==before
    return len(matrix)


def run(output,meta):
    with tempfile.TemporaryDirectory(prefix='audit-restart-') as directory:
        temporary=Path(directory);database=temporary/'test.sqlite3'
        users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
        seed_users(database,users,SystemClock());server=LiveServer(database,temporary)
        try:
            server.start();write_json(output/'environment.json',environment(server,meta)|dict(server_start=server.command,database_path=str(database),schema_version=2,clock='production SystemClock',fixed_clock_injection=False,
                invocation=[sys.executable,'-m','scripts.verify_audit_http',*sys.argv[1:]]))
            clients,payload,record_id=populate(server,users,output)
            before=facts(database);write_json(output/'before-restart.json',evidence_facts(before))
            old_pid=server.process.pid;server.stop();assert server.process is None
            server.start();new_pid=server.process.pid;assert old_pid!=new_pid
            after=facts(database);write_json(output/'after-restart.json',evidence_facts(after));assert after==before
            for client in clients:assert client.request('/api/me')[0]==200
            status,body,_=clients[0].request('/api/bookings',payload)
            write_json(output/'replay-after-restart.json',dict(status=status,response=body))
            assert status==200 and body['data']['replayed'] and body['data']['booking']['id']==record_id and body['data']['booking']['status']=='cancelled'
            assert facts(database)==before
            backup=backup_database(database,temporary/'verified-backup.sqlite3')
            assert facts(temporary/'verified-backup.sqlite3')==before
            write_json(output/'backup.json',backup|dict(matches_live_business_and_relationships=True))
            total=permission_matrix(server,users,record_id,output)
            write_json(output/'restart.json',dict(old_pid=old_pid,new_pid=new_pid,old_process_stopped_before_start=True,old_sessions_valid=True,identical_business_and_relationships=True,audit_count_unchanged=True,original_intent_cancelled_record_id=record_id))
        finally:
            server.stop();write_json(output/'process-cleanup.json',dict(pids=server.pids,completed=server.process is None))
    return dict(result='PASS',completed=True,permission_cases=total,all_seven_actions=True,unchanged_retries=True,real_restart=True,backup_checked=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'docs/evidence/story-3.4/http')
    args=parser.parse_args(argv);args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat());output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True)
    meta['artifact_directory']='runs/'+meta['run_id'];target=args.output_dir/'result.json';write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    try:
        meta['source_sha256']=source_hashes();result=run(output,meta);meta['source_sha256_after']=source_hashes();assert meta['source_sha256']==meta['source_sha256_after']
        report=meta|result|dict(finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        report=meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__)
        write_json(output/'result.json',report);write_json(target,report);raise
    write_json(output/'result.json',report);write_json(target,report);print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())

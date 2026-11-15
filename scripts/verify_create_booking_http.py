"""Story 2.1: 20 independent real HTTP sessions, full storage oracle and audit rollback."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import hashlib
import multiprocessing
from pathlib import Path
import secrets
import tempfile
import threading

from booking_app import ROOT, create_app, db
# 当前直接创建/本人直接取消场景使用合成导师；学生审批另有独立runner。
from tests.direct_booking_fixture import seed_users
from scripts.verify_availability_performance import Client, Server, environment, source_fingerprints, write_json
from tests.schedule_fixtures import NOW, epoch

class FixedClock:
    def now_epoch(self): return NOW

def failed_writer(conn, event):
    raise RuntimeError('injected audit failure')

def server_main(database,port,fail):
    from waitress import serve
    config={'TESTING':True,'DATABASE':database,'CLOCK':FixedClock(),
            'APP_ORIGIN':f'http://127.0.0.1:{port}','TRUSTED_HOSTS':['127.0.0.1']}
    if fail: config['AUDIT_WRITER']=failed_writer
    serve(create_app(config),host='127.0.0.1',port=port,threads=8)

class BookingServer(Server):
    def __init__(self,database,fail=False):
        super().__init__(database)
        self.process=multiprocessing.get_context('spawn').Process(target=server_main,args=(str(database),self.port,fail))

def storage(database):
    with db.read_transaction(database) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        records=[dict(r) for r in conn.execute('SELECT * FROM reservations ORDER BY id')]
        slots=[dict(r) for r in conn.execute('SELECT * FROM occupancy_slots ORDER BY room_id,slot_start')]
        audits=[dict(r) for r in conn.execute('SELECT * FROM audit_events ORDER BY id')]
        for record in records:
            actual=[r['slot_start'] for r in slots if r['reservation_id']==record['id']]
            assert actual==list(range(record['start_at'],record['end_at'],1800))
            events=[a for a in audits if a['target_id']==record['id'] and a['action']=='booking.created']
            assert len(events)==1
            event=events[0]
            assert event['actor_id']==record['user_id'] and event['occurred_at']==NOW
            assert event['before_json'] is None and event['reason'] is None and event['target_type']=='booking'
            snapshot=json.loads(event['after_json'])
            assert snapshot==dict(id=record['id'],room_id=record['room_id'],owner_id=record['user_id'],
                title=record['title'],purpose=record['purpose'],attendees=record['attendees'],
                start_at=record['start_at'],end_at=record['end_at'],created_at=NOW,
                cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
            assert json.loads(record['request_payload'])==dict(room_id=record['room_id'],title=record['title'],
                purpose=record['purpose'],attendees=record['attendees'],start_at=record['start_at'],end_at=record['end_at'])
        return dict(reservations=records,slots=slots,audit_events=audits,integrity_check='ok',foreign_key_check='ok')

def run(output,run):
    with tempfile.TemporaryDirectory(prefix='grb-create-http-') as temp:
        database=Path(temp)/'booking.sqlite3'
        users=[dict(username=f'create_synthetic_{i:02}',display_name=f'合成成员 {i:02}',role='teacher',
                    password=secrets.token_urlsafe(24)) for i in range(20)]
        seed_users(database,users+[dict(username='fixture_admin',display_name='合成管理员',role='admin',password=secrets.token_urlsafe(24))],FixedClock())
        with db.write_transaction(database) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'合成并发会议室','测试楼',20,?,?)",(NOW,NOW))
        server=BookingServer(database)
        responses=[]
        payload=dict(room_id=1,title='合成并发活动 🧪',purpose='仅用于测试',attendees=10,
                     start='2026-11-12T12:00',end='2026-11-12T14:00')
        try:
            server.start()
            env=environment(server,run)
            env.update(server_start="spawn scripts.verify_create_booking_http.server_main; Waitress threads=8",
                       invocation=['.venv/bin/python','-m','scripts.verify_create_booking_http','--output-dir',str(output)],
                       fixed_now=NOW,independent_members=20)
            write_json(output/'create-http-environment.json',env)
            clients=[Client(server.origin) for _ in users]
            for client,user in zip(clients,users): client.login(user)
            barrier=threading.Barrier(20)
            def one(i):
                data=payload|dict(intent_key=f'independent-intent-{i:03}')
                try:
                    barrier.wait(timeout=30)
                    status,body,elapsed=clients[i].request('/api/bookings',data)
                    return dict(index=i,http_status=status,response=body,duration_ms=elapsed)
                except Exception as error:
                    return dict(index=i,http_status=None,response=None,error_type=type(error).__name__)
            with ThreadPoolExecutor(max_workers=20) as pool:
                futures=[pool.submit(one,i) for i in range(20)]
                with (output/'create-http-responses.jsonl').open('w') as raw:
                    for future in futures:
                        result=future.result(); responses.append(result)
                        raw.write(json.dumps(result,ensure_ascii=False)+'\n'); raw.flush()
            codes=[r['http_status'] for r in responses]
            assert codes.count(201)==1 and codes.count(409)==19
            for row in responses:
                if row['http_status']==409:
                    assert row['response']['error']['code']=='OCCUPANCY_CONFLICT'
                    conflicts=row['response']['error']['conflicts']; assert len(conflicts)==1
                    assert set(conflicts[0])=={'type','room_id','start_at','start_local','end_at','end_local','status'}
            after_race=storage(database)
            assert len(after_race['reservations'])==1 and len(after_race['slots'])==4 and len(after_race['audit_events'])==1
            winner=next(row for row in responses if row['http_status']==201)
            assert winner['response']['data']['booking']['id']==after_race['reservations'][0]['id']
            assert after_race['reservations'][0]['user_id']==winner['index']+1
            write_json(output/'create-http-storage.json',after_race)
        finally: server.stop()
        # Restart with a test-only failing writer, then retry the exact failed key after a clean restart.
        retry=payload|dict(start='2026-11-13T12:00',end='2026-11-13T14:00',intent_key='audit-failed-key-reusable')
        faults=[]
        server=BookingServer(database,fail=True)
        try:
            server.start(); client=Client(server.origin); client.login(users[0])
            status,body,elapsed=client.request('/api/bookings',retry)
            faults.append(dict(phase='audit_failure',http_status=status,response=body,duration_ms=elapsed))
            assert status==500 and body['error']['code']=='INTERNAL_ERROR'
            assert storage(database)==after_race
        finally: server.stop()
        server=BookingServer(database)
        try:
            server.start(); client=Client(server.origin); client.login(users[0])
            assert storage(database)==after_race
            status,body,elapsed=client.request('/api/bookings',retry)
            faults.append(dict(phase='same_key_after_failure_and_restart',http_status=status,response=body,duration_ms=elapsed))
            assert status==201
            final=storage(database)
            assert len(final['reservations'])==2 and len(final['slots'])==8 and len(final['audit_events'])==2
            write_json(output/'create-http-final-storage.json',final)
        finally:
            write_json(output/'create-http-fault-responses.json',faults)
            server.stop()
    return dict(result='PASS',completed=True,concurrent_requests=20,successes=1,occupancy_conflicts=19,
                race_records=1,race_slots=4,race_creation_audits=1,audit_failure_rollback=True,
                failed_key_reusable=True,restart_preserves_business=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'work/create-booking-http')
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    path=args.output_dir/'create-http-result.json'
    write_json(path,meta|dict(result='INCOMPLETE',completed=False))
    try:
        fingerprints=source_fingerprints()
        fingerprints.pop('performance_script_sha256',None)
        meta.update(fingerprints)
        meta['create_http_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report=run(args.output_dir,meta)
        write_json(path,meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat()))
    except BaseException as error:
        write_json(path,meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__))
        print(json.dumps(dict(result='INCOMPLETE',error_type=type(error).__name__)))
        raise
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())

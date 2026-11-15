"""Story 2.4 real HTTP cancellation race, atomic audit fault and process restart."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import threading

from booking_app import ROOT, db
from tests.legacy_fixture import seed_users
from scripts.verify_availability_performance import Client, environment, write_json
from scripts.verify_create_booking_http import BookingServer, FixedClock
from scripts.verify_history_browser import facts, source_fingerprints
from tests.history_fixtures import FULL_KEYS
from tests.schedule_fixtures import NOW


def checked_storage(database):
    value=facts(database)
    for record in value['reservations']:
        slots=sorted(s['slot_start'] for s in value['occupancy_slots'] if s['reservation_id']==record['id'])
        assert slots==([] if record['cancelled_at'] is not None else list(range(record['start_at'],record['end_at'],1800)))
        events=[a for a in value['audit_events'] if a['target_id']==record['id']]
        assert sum(a['action']=='booking.created' for a in events)==1
        assert sum(a['action']=='booking.cancelled_by_member' for a in events)==int(record['cancelled_at'] is not None)
        if record['cancelled_at'] is not None:
            event=next(a for a in events if a['action']=='booking.cancelled_by_member')
            before,after=json.loads(event['before_json']),json.loads(event['after_json'])
            assert before==dict(id=record['id'],room_id=record['room_id'],owner_id=record['user_id'],
                title=record['title'],purpose=record['purpose'],attendees=record['attendees'],
                start_at=record['start_at'],end_at=record['end_at'],created_at=record['created_at'],
                cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
            assert after==before|dict(cancelled_at=record['cancelled_at'],cancelled_by_id=record['user_id'],cancel_reason=None)
            assert event['reason'] is None and event['occurred_at']==NOW
    return value


def fingerprints():
    result=source_fingerprints()
    for name in ('scripts/verify_member_cancel_http.py','scripts/verify_create_booking_http.py','scripts/verify_availability_performance.py'):
        result['verification_source_files_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return result


def collect_race_responses(futures, output, database):
    """Drain every submitted worker and preserve facts before checking race outcomes."""
    responses=[]
    with (output/'concurrent-responses.jsonl').open('w') as raw:
        for index, future in enumerate(futures):
            try:
                row=future.result() | dict(index=index)
            except Exception as error:
                status=getattr(error,'status',None)
                row=dict(index=index,http_status=status if type(status) is int and 100<=status<=599 else None,
                         error_type=type(error).__name__)
            responses.append(row)
            raw.write(json.dumps(row,ensure_ascii=False)+'\n');raw.flush()
    write_json(output/'after-race.json',facts(database))
    return responses


def run(output,meta):
    with tempfile.TemporaryDirectory(prefix='grb-cancel-http-') as directory:
        database=Path(directory)/'booking.sqlite3'
        user=dict(username='cancel_synthetic',display_name='合成取消成员',role='member',password=secrets.token_urlsafe(24))
        seed_users(database,[user,dict(username='other_synthetic',display_name='合成成员乙',role='member',password=secrets.token_urlsafe(24)),
            dict(username='admin_synthetic',display_name='合成管理员',role='admin',password=secrets.token_urlsafe(24))],FixedClock())
        with db.write_transaction(database) as conn: conn.execute("INSERT INTO rooms VALUES(1,'合成取消会议室','测试楼',20,?,?)",(NOW,NOW))
        payload=dict(room_id=1,title='合成取消活动',purpose='测试用途',attendees=5,start='2026-11-12T12:00',
                     end='2026-11-12T14:00',intent_key='cancel-http-original-intent')
        steps=[]
        def capture(client,phase,path,body):
            status,response,elapsed=client.request(path,body)
            steps.append(dict(phase=phase,path=path,http_status=status,response=response,duration_ms=elapsed))
            write_json(output/'http-steps.json',steps)
            return status,response
        server=BookingServer(database)
        try:
            server.start(); client=Client(server.origin);client.login(user)
            write_json(output/'environment.json',environment(server,meta)|dict(fixed_now=NOW,threads=8,
                independent_sessions=20,server_start='spawn scripts.verify_create_booking_http.server_main',
                invocation=['.venv/bin/python','-m','scripts.verify_member_cancel_http','--output-dir',str(output)]))
            status,result=capture(client,'create','/api/bookings',payload);assert status==201
            booking_id=result['data']['booking']['id'];cancel_path=f'/api/bookings/{booking_id}/cancel'
            saved=checked_storage(database);write_json(output/'before-fault.json',saved)
        finally: server.stop()
        server=BookingServer(database,fail=True)
        try:
            server.start();client=Client(server.origin);client.login(user)
            assert checked_storage(database)==saved
            status,result=capture(client,'cancel_audit_failure',cancel_path,{})
            assert status==500 and result['error']['code']=='INTERNAL_ERROR'
            assert checked_storage(database)==saved
            write_json(output/'after-fault.json',checked_storage(database))
        finally: server.stop()
        server=BookingServer(database)
        try:
            server.start();clients=[Client(server.origin) for _ in range(20)]
            for client in clients: client.login(user)
            assert len({id(client.jar) for client in clients})==20
            barrier=threading.Barrier(20)
            def cancel(index):
                barrier.wait(timeout=30)
                status,result,elapsed=clients[index].request(cancel_path,{})
                return dict(index=index,http_status=status,response=result,duration_ms=elapsed)
            with ThreadPoolExecutor(max_workers=20) as pool:
                futures=[pool.submit(cancel,i) for i in range(20)]
                responses=collect_race_responses(futures,output,database)
            assert all(row['http_status']==200 for row in responses)
            cancelled=responses[0]['response']['data']
            assert set(cancelled)==FULL_KEYS and cancelled['status']=='cancelled'
            assert all(row['response']['data']==cancelled for row in responses)
            saved=checked_storage(database)
            assert (len(saved['reservations']),len(saved['occupancy_slots']),len(saved['audit_events']))==(1,0,2)
            write_json(output/'after-race.json',saved)
        finally: server.stop()
        server=BookingServer(database,fail=True)
        try:
            server.start();client=Client(server.origin);client.login(user)
            assert checked_storage(database)==saved
            status,result=capture(client,'repeat_after_restart_failing_writer',cancel_path,{})
            assert status==200 and result['data']==cancelled
            status,result=capture(client,'old_successful_intent_replay_cancelled','/api/bookings',payload)
            assert status==200 and result['data']==dict(booking=cancelled,replayed=True)
            assert checked_storage(database)==saved
        finally: server.stop()
        server=BookingServer(database)
        try:
            server.start();client=Client(server.origin);client.login(user)
            status,result=capture(client,'slot_reuse','/api/bookings',payload|dict(intent_key='cancel-http-replacement-intent'))
            assert status==201 and result['data']['booking']['id']!=booking_id
            final=checked_storage(database)
            assert (len(final['reservations']),len(final['occupancy_slots']),len(final['audit_events']))==(2,4,3)
            write_json(output/'final-storage.json',final)
        finally: server.stop()
    return dict(result='PASS',completed=True,simultaneous_cancels=20,http_200=20,independent_sessions=20,
                cancellation_transitions=1,cancellation_audits=1,audit_failure_full_rollback=True,
                restart_persistence=True,repeat_writer_calls=0,old_intent_returns_cancelled=True,slot_reuse=True,
                member_admin_competition='NOT TESTED: reserved for Story 2.5')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'work/member-cancel-http')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    target=args.output_dir/'http-result.json';write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True)
    meta['artifact_directory']='runs/'+meta['run_id']
    try:
        meta.update(fingerprints());report=run(output,meta)
        assert all(meta[key]==value for key,value in fingerprints().items()),'Sources changed during verification'
        write_json(target,meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat()))
    except BaseException as error:
        write_json(target,meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__));raise
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

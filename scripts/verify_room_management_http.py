"""Story 3.1: 20 real booking/capacity races, full storage oracle, fault and restart."""
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
from scripts.init_demo import DEMO_IDENTITIES, seed_users
from scripts.verify_availability_performance import Client, environment, write_json
from scripts.verify_create_booking_http import BookingServer, FixedClock
from scripts.verify_history_browser import source_fingerprints
from tests.schedule_fixtures import NOW


def facts(database):
    with db.read_transaction(database) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        return {table:[dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('rooms','reservations','occupancy_slots','audit_events')}


def checked_storage(database):
    value=facts(database); rooms={r['id']:r for r in value['rooms']}
    for record in value['reservations']:
        slots=sorted(s['slot_start'] for s in value['occupancy_slots'] if s['reservation_id']==record['id'])
        assert slots==([] if record['cancelled_at'] is not None else list(range(record['start_at'],record['end_at'],1800)))
        if record['cancelled_at'] is None and record['end_at']>NOW: assert record['attendees']<=rooms[record['room_id']]['capacity']
        events=[a for a in value['audit_events'] if a['target_type']=='booking' and a['target_id']==record['id']]
        assert sum(a['action']=='booking.created' for a in events)==1
        assert sum(a['action']=='booking.cancelled_by_member' for a in events)==int(record['cancelled_at'] is not None)
    for room in rooms.values():
        events=[a for a in value['audit_events'] if a['target_type']=='room' and a['target_id']==room['id']]
        assert events and events[0]['action']=='room.created' and events[0]['before_json'] is None
        last=None
        for event in events:
            before=json.loads(event['before_json']) if event['before_json'] else None
            after=json.loads(event['after_json'])
            assert before==last and set(after)=={'id','name','location','capacity'}
            assert event['reason'] is None and event['occurred_at']==NOW and event['actor_display_name']=='演示管理员'
            last=after
        assert last=={key:room[key] for key in ('id','name','location','capacity')}
    return value


def fingerprints():
    value=source_fingerprints()
    for name in ('scripts/verify_room_management_http.py','scripts/verify_create_booking_http.py','scripts/verify_availability_performance.py'):
        value['verification_source_files_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return value


def run(output,meta):
    responses=[]
    def capture(client,phase,path,body):
        status,result,elapsed=client.request(path,body)
        row=dict(phase=phase,path=path,http_status=status,response=result,duration_ms=elapsed)
        responses.append(row);write_json(output/'http-steps.json',responses)
        return status,result
    with tempfile.TemporaryDirectory(prefix='grb-room-http-') as directory:
        database=Path(directory)/'booking.sqlite3'
        users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
        seed_users(database,users,FixedClock());server=BookingServer(database)
        wins={'booking':0,'capacity':0}
        try:
            server.start();admin,member=Client(server.origin),Client(server.origin)
            admin.login(users[2]);member.login(users[0])
            write_json(output/'environment.json',environment(server,meta)|dict(fixed_now=NOW,threads=8,
                independent_sessions=2,rounds=20,server_start='spawn scripts.verify_create_booking_http.server_main',
                invocation=['.venv/bin/python','-m','scripts.verify_room_management_http','--output-dir',str(output)]))
            for round_number in range(20):
                room_values=dict(name=f'合成竞争房间 {round_number:02}',location='测试楼',capacity=20)
                status,result=capture(admin,'setup_room','/api/admin/rooms',room_values);assert status==201
                room_id=result['data']['id'];barrier=threading.Barrier(2)
                jobs=[(member,'booking','/api/bookings',dict(room_id=room_id,title='并发预约',purpose='合成测试',attendees=10,
                    start='2026-11-12T12:00',end='2026-11-12T13:00',intent_key=f'capacity-race-intent-{round_number:03}')),
                    (admin,'capacity',f'/api/admin/rooms/{room_id}',room_values|dict(capacity=5))]
                def compete(job):
                    client,phase,path,body=job;barrier.wait(timeout=30)
                    status,response,elapsed=client.request(path,body)
                    return dict(round=round_number,phase=phase,path=path,http_status=status,response=response,duration_ms=elapsed)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(compete,job) for job in jobs];rows=[]
                    for future in futures:
                        try:row=future.result()
                        except Exception as error:row=dict(round=round_number,http_status=None,error_type=type(error).__name__)
                        rows.append(row)
                        with (output/'concurrent-responses.jsonl').open('a') as raw:raw.write(json.dumps(row,ensure_ascii=False)+'\n')
                write_json(output/f'round-{round_number:02}-storage.json',facts(database))
                codes=[row['http_status'] for row in rows]
                assert codes in ([201,409],[409,200]),codes
                loser=next(row for row in rows if row['http_status']==409)
                assert loser['response']['error']['code']=='CAPACITY_CONFLICT'
                winner='booking' if codes[0]==201 else 'capacity';wins[winner]+=1
                final=checked_storage(database)
                room_events=[e for e in final['audit_events'] if e['target_type']=='room' and e['target_id']==room_id]
                assert len(room_events)==(1 if winner=='booking' else 2)
                assert sum(r['room_id']==room_id for r in final['reservations'])==int(winner=='booking')
            # A real successful intent, cancelled and then lowered below its historical attendees.
            status,result=capture(admin,'replay_room','/api/admin/rooms',dict(name='重放房间',location='测试楼',capacity=20));assert status==201
            replay_room=result['data'];payload=dict(room_id=replay_room['id'],title='旧意图',purpose='合成测试',attendees=10,
                start='2026-11-12T12:00',end='2026-11-12T13:00',intent_key='room-management-replay-intent')
            status,result=capture(member,'replay_create','/api/bookings',payload);assert status==201
            booking_id=result['data']['booking']['id']
            assert capture(member,'cancel_for_replay',f'/api/bookings/{booking_id}/cancel',{})[0]==200
            lowered={key:replay_room[key] for key in ('name','location','capacity')}|dict(capacity=1)
            assert capture(admin,'lower_after_cancel',f'/api/admin/rooms/{replay_room["id"]}',lowered)[0]==200
            saved=checked_storage(database);write_json(output/'before-restart-fault.json',saved)
        finally:server.stop()
        server=BookingServer(database,fail=True)
        try:
            server.start();admin,member=Client(server.origin),Client(server.origin);admin.login(users[2]);member.login(users[0])
            assert checked_storage(database)==saved
            for path,body in [('/api/admin/rooms',dict(name='故障新增',location='测试楼',capacity=20)),
                              (f'/api/admin/rooms/{replay_room["id"]}',lowered|dict(name='故障修改',capacity=2))]:
                status,result=capture(admin,'audit_failure',path,body)
                assert status==500 and result['error']['code']=='INTERNAL_ERROR'
                assert checked_storage(database)==saved
            assert capture(admin,'no_change_failing_writer',f'/api/admin/rooms/{replay_room["id"]}',lowered)[0]==200
            status,result=capture(member,'old_intent_lowered_restart','/api/bookings',payload)
            assert status==200 and result['data']['replayed'] and result['data']['booking']['id']==booking_id
            assert result['data']['booking']['room']['capacity']==1
            assert checked_storage(database)==saved
            write_json(output/'after-restart-fault.json',checked_storage(database))
        finally:server.stop()
    return dict(result='PASS',completed=True,rounds=20,concurrent_responses=40,wins=wins,
        no_unfinished_overcapacity=True,exact_room_audit_chain=True,full_fault_rollback=True,
        restart_preserves_business_slots_audits=True,old_intent_replay_after_lowering=True,no_change_writer_calls=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'work/room-management-http')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    target=args.output_dir/'http-result.json';write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True);meta['artifact_directory']='runs/'+meta['run_id']
    try:
        meta.update(fingerprints());report=run(output,meta)
        assert all(meta[key]==value for key,value in fingerprints().items()),'Sources changed during verification'
        write_json(target,meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat()))
    except BaseException as error:
        write_json(target,meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__));raise
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

"""Story 3.2 real HTTP booking/block races, final facts, rollback and restart."""
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
# 当前直接创建/本人直接取消场景使用合成导师；学生审批另有独立runner。
from tests.direct_booking_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_availability_performance import Client, environment, write_json
from scripts.verify_create_booking_http import BookingServer, FixedClock
from scripts.verify_history_browser import source_fingerprints
from scripts.verify_room_management_http import facts
from tests.schedule_fixtures import NOW
from tests.maintenance_contract import BLOCK_KEYS, BOOKING_KEYS, BLOCK_SNAPSHOT_KEYS


def checked_storage(database):
    value=facts(database)
    slots=value['occupancy_slots'];assert len({(s['room_id'],s['slot_start']) for s in slots})==len(slots)
    for record in value['reservations']:
        actual=sorted(s['slot_start'] for s in slots if s['reservation_id']==record['id'])
        assert actual==list(range(record['start_at'],record['end_at'],1800))
        assert all(s['room_id']==record['room_id'] for s in slots if s['reservation_id']==record['id'])
        events=[event for event in value['audit_events'] if event['target_type']==record['kind'] and event['target_id']==record['id']]
        assert len(events)==1;event=events[0]
        assert event['action']==record['kind']+'.created' and event['actor_id']==record['user_id'] and event['occurred_at']==NOW
        assert event['before_json'] is None
        snapshot=json.loads(event['after_json'])
        if record['kind']=='block':
            assert all(record[key] is None for key in ('title','purpose','attendees','intent_key','request_payload'))
            assert set(snapshot)==BLOCK_SNAPSHOT_KEYS
            assert snapshot==dict(id=record['id'],room_id=record['room_id'],creator_id=record['user_id'],reason=record['reason'],
                start_at=record['start_at'],end_at=record['end_at'],created_at=NOW,revoked_at=None,revoked_by_id=None,revoke_reason=None)
            assert event['reason']==record['reason'] and event['actor_display_name']=='演示管理员'
        else:
            assert event['reason'] is None
            assert snapshot==dict(id=record['id'],room_id=record['room_id'],owner_id=record['user_id'],title=record['title'],
                purpose=record['purpose'],attendees=record['attendees'],start_at=record['start_at'],end_at=record['end_at'],
                created_at=NOW,cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
    return value


def fingerprints():
    value=source_fingerprints()
    for name in ('scripts/verify_maintenance_block_http.py','scripts/verify_room_management_http.py',
                 'scripts/verify_create_booking_http.py','scripts/verify_availability_performance.py','tests/maintenance_contract.py'):
        value['verification_source_files_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return value


def run(output,meta):
    responses=[]
    def capture(client,phase,path,body=None):
        status,response,elapsed=client.request(path,body)
        responses.append(dict(phase=phase,path=path,http_status=status,response=response,duration_ms=elapsed))
        write_json(output/'http-steps.json',responses);return status,response
    with tempfile.TemporaryDirectory(prefix='grb-block-http-') as directory:
        database=Path(directory)/'booking.sqlite3'
        users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
        seed_users(database,users,FixedClock());server=BookingServer(database);wins={'booking':0,'block':0}
        try:
            server.start();admin,member=Client(server.origin),Client(server.origin);admin.login(users[2]);member.login(users[0])
            write_json(output/'environment.json',environment(server,meta)|dict(fixed_now=NOW,threads=8,independent_sessions=2,rounds=20,
                server_start='spawn scripts.verify_create_booking_http.server_main',
                invocation=['.venv/bin/python','-m','scripts.verify_maintenance_block_http','--output-dir',str(output)]))
            for round_number in range(20):
                status,response=capture(admin,'room','/api/admin/rooms',dict(name=f'合成停用竞争 {round_number:02}',location='测试楼',capacity=20));assert status==201
                room_id=response['data']['id'];barrier=threading.Barrier(2)
                interval=dict(room_id=room_id,start='2026-11-12T12:00',end='2026-11-12T13:00')
                jobs=[(member,'booking','/api/bookings',interval|dict(title='合成活动',purpose='私密用途',attendees=5,intent_key=f'block-booking-race-{round_number:03}')),
                      (admin,'block','/api/admin/blocks',interval|dict(reason='维护'))]
                def compete(job):
                    client,kind,path,body=job;barrier.wait(timeout=30)
                    status,response,elapsed=client.request(path,body)
                    return dict(round=round_number,kind=kind,path=path,http_status=status,response=response,duration_ms=elapsed)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(compete,job) for job in jobs];rows=[]
                    for future in futures:
                        try:row=future.result()
                        except Exception as error:row=dict(round=round_number,http_status=None,error_type=type(error).__name__)
                        rows.append(row)
                        with (output/'concurrent-responses.jsonl').open('a') as raw:raw.write(json.dumps(row,ensure_ascii=False)+'\n')
                final=checked_storage(database);write_json(output/f'round-{round_number:02}-storage.json',final)
                assert sorted(row['http_status'] for row in rows)==[201,409]
                winner=next(row for row in rows if row['http_status']==201);loser=next(row for row in rows if row['http_status']==409)
                wins[winner['kind']]+=1;assert loser['response']['error']['code']=='OCCUPANCY_CONFLICT'
                records=[row for row in final['reservations'] if row['room_id']==room_id];assert len(records)==1
                assert records[0]['kind']==winner['kind']
                assert set(winner['response']['data'] if winner['kind']=='block' else winner['response']['data']['booking'])==(BLOCK_KEYS if winner['kind']=='block' else BOOKING_KEYS)
                conflict=loser['response']['error']['conflicts'][0]
                assert set(conflict)==({'type','room_id','start_at','start_local','end_at','end_local','status'} |
                                      ({'id','attendees','reason'} if loser['kind']=='block' else set()))
            status,response=capture(admin,'adjacency_room','/api/admin/rooms',dict(name='合成边界房间',location='测试楼',capacity=20));assert status==201
            room_id=response['data']['id']
            booking=dict(room_id=room_id,start='2026-11-13T10:00',end='2026-11-13T11:00',title='原安排',purpose='私密',attendees=5,intent_key='block-persistence-booking')
            status,response=capture(member,'booking','/api/bookings',booking);assert status==201;booking_id=response['data']['booking']['id']
            saved=checked_storage(database)
            long_block=dict(room_id=room_id,start='2026-11-13T10:30',end='2026-11-14T16:00',reason='跨日长维护 <img src=x>')
            assert capture(admin,'protect_booking','/api/admin/blocks',long_block)[0]==409;assert checked_storage(database)==saved
            long_block['start']='2026-11-13T11:00';status,response=capture(admin,'adjacent_long_block','/api/admin/blocks',long_block);assert status==201;block_id=response['data']['id']
            saved=checked_storage(database)
            assert capture(admin,'block_overlap','/api/admin/blocks',long_block)[0]==409
            assert capture(member,'member_direct_write','/api/admin/blocks',{})[0]==403
            for kind in ('bookings','blocks'):
                assert capture(member,'member_direct_list',f'/api/admin/{kind}?status=bad')[0]==403
                status,response=capture(admin,'admin_full_list',f'/api/admin/{kind}');assert status==200
                data=response['data'];assert data['total']==len(data['items'])
                assert all(set(row)==(BOOKING_KEYS if kind=='bookings' else BLOCK_KEYS) for row in data['items'])
                assert [(row['start_at'],row['id']) for row in data['items']]==sorted((row['start_at'],row['id']) for row in data['items'])
                assert capture(admin,'illegal_status',f'/api/admin/{kind}?status=invalid')[0]==400
            for date in ('2026-11-13','2026-11-14'):
                status,response=capture(admin,'cross_day_query',f'/api/admin/blocks?room_id={room_id}&date={date}')
                assert status==200 and [row['id'] for row in response['data']['items']]==[block_id]
            assert checked_storage(database)==saved;write_json(output/'before-restart-fault.json',saved)
        finally:server.stop()
        server=BookingServer(database,fail=True)
        try:
            server.start();admin,member=Client(server.origin),Client(server.origin);admin.login(users[2]);member.login(users[0])
            assert checked_storage(database)==saved
            retry=long_block|dict(start='2026-11-15T12:00',end='2026-11-16T14:00')
            status,response=capture(admin,'audit_failure','/api/admin/blocks',retry);assert status==500 and response['error']['code']=='INTERNAL_ERROR'
            assert checked_storage(database)==saved
            status,response=capture(member,'old_intent_after_restart','/api/bookings',booking)
            assert status==200 and response['data']['replayed'] and response['data']['booking']['id']==booking_id
            assert checked_storage(database)==saved;write_json(output/'after-restart-fault.json',checked_storage(database))
        finally:server.stop()
        server=BookingServer(database)
        try:
            server.start();admin=Client(server.origin);admin.login(users[2]);assert checked_storage(database)==saved
            assert capture(admin,'retry_after_failure','/api/admin/blocks',retry)[0]==201
            final=checked_storage(database);assert len(final['reservations'])==len(saved['reservations'])+1
            write_json(output/'final-storage.json',final)
        finally:server.stop()
    return dict(result='PASS',completed=True,rounds=20,concurrent_responses=40,wins=wins,shared_slot_integrity=True,
        original_booking_preserved=True,adjacent_long_cross_day_block=True,admin_exact_dtos=True,member_rejected=True,
        full_audit_failure_rollback=True,restart_preserves_business_slots_audits=True,old_intent_replay=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'work/maintenance-block-http')
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

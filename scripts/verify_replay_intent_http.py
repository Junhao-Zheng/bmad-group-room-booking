"""Story 2.2: independent clients sharing one identity, real file DB/restarts/faults."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import threading

from booking_app import ROOT, db
from tests.legacy_fixture import seed_users
from scripts.verify_availability_performance import Client, environment, source_fingerprints, write_json
from scripts.verify_create_booking_http import BookingServer, FixedClock, storage
from tests.schedule_fixtures import NOW


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def safe_storage(value):
    return value | {'reservations': [{k: v for k, v in record.items() if k != 'intent_key'}
        | {'intent_key_sha256': digest(record['intent_key'])} for record in value['reservations']]}


def run(output, meta):
    with tempfile.TemporaryDirectory(prefix='grb-replay-http-') as temporary:
        database = Path(temporary) / 'booking.sqlite3'
        users = [dict(username=f'replay_synthetic_{i}', display_name=f'合成成员{i}', role='member',
                      password=secrets.token_urlsafe(24)) for i in range(2)]
        users.append(dict(username='replay_admin', display_name='合成管理员', role='admin', password=secrets.token_urlsafe(24)))
        seed_users(database, users, FixedClock())
        with db.write_transaction(database) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'合成重放会议室','测试楼',20,?,?)", (NOW,NOW))
        payload = dict(room_id=1,title='合成重放活动 🧪',purpose='测试用途',attendees=10,
                       start='2026-11-12T12:00',end='2026-11-12T14:00',intent_key=secrets.token_urlsafe(32))
        responses = []
        server = BookingServer(database)
        try:
            server.start()
            env = environment(server,meta)
            env.update(server_start='spawn scripts.verify_create_booking_http.server_main; Waitress threads=8',
                invocation=['.venv/bin/python','-m','scripts.verify_replay_intent_http','--output-dir',str(output)],
                fixed_now=NOW, independent_clients=20, shared_identity=True,
                independent_cookie_jars=True, intent_key_sha256=digest(payload['intent_key']))
            write_json(output/'replay-http-environment.json',env)
            authenticated = Client(server.origin)
            authenticated.login(users[0])
            clients = [Client(server.origin) for _ in range(20)]
            for client in clients:
                client.csrf = authenticated.csrf
                for cookie in authenticated.jar: client.jar.set_cookie(copy.copy(cookie))
            assert len({id(c.jar) for c in clients}) == 20
            barrier = threading.Barrier(20)
            def submit(i):
                try:
                    barrier.wait(timeout=30)
                    status, body, elapsed = clients[i].request('/api/bookings',payload)
                    return dict(index=i,http_status=status,response=body,duration_ms=elapsed)
                except Exception as error:
                    return dict(index=i,http_status=None,error_type=type(error).__name__)
            with ThreadPoolExecutor(max_workers=20) as pool:
                futures = [pool.submit(submit,i) for i in range(20)]
                with (output/'replay-http-responses.jsonl').open('w') as raw:
                    for future in futures:
                        result = future.result()
                        responses.append(result)
                        raw.write(json.dumps(result,ensure_ascii=False)+'\n'); raw.flush()
            codes = [row['http_status'] for row in responses]
            assert codes.count(201)==1 and codes.count(200)==19
            ids = {row['response']['data']['booking']['id'] for row in responses}
            assert len(ids)==1
            for row in responses:
                assert row['response']['data']['replayed'] is (row['http_status']==200)
            saved = storage(database)
            assert (len(saved['reservations']),len(saved['slots']),len(saved['audit_events'])) == (1,4,1)
            assert saved['reservations'][0]['id'] in ids
            write_json(output/'replay-http-storage.json',safe_storage(saved))
        finally: server.stop()
        steps = []
        def capture(client,phase,data):
            status,body,elapsed = client.request('/api/bookings',data)
            steps.append(dict(phase=phase,http_status=status,response=body,duration_ms=elapsed,
                              intent_key_sha256=digest(data['intent_key'])))
            write_json(output/'replay-http-restart-fault-responses.json',steps)
            return status,body
        failed_payload = payload | dict(start='2026-11-13T12:00',end='2026-11-13T14:00',intent_key=secrets.token_urlsafe(32))
        # A writer that always throws proves replay never invokes it even after process restart.
        server = BookingServer(database,fail=True)
        try:
            server.start(); client=Client(server.origin); client.login(users[0])
            assert storage(database)==saved
            status,body=capture(client,'replay_after_restart_with_failing_writer',payload)
            assert status==200 and body['data']['booking']['id'] in ids
            status,body=capture(client,'new_intent_audit_failure',failed_payload)
            assert status==500 and body['error']['code']=='INTERNAL_ERROR'
            assert storage(database)==saved
        finally: server.stop()
        server = BookingServer(database)
        try:
            server.start(); client=Client(server.origin); client.login(users[0])
            assert storage(database)==saved
            status,body=capture(client,'failed_key_retry_after_second_restart',failed_payload)
            assert status==201 and body['data']['replayed'] is False
            new_id=body['data']['booking']['id']
            status,body=capture(client,'confirmed_original_key_after_second_restart',payload)
            assert status==200 and body['data']['booking']['id'] in ids
            status,body=capture(client,'confirmed_corrected_intent',failed_payload)
            assert status==200 and body['data']['booking']['id']==new_id
            final=storage(database)
            assert (len(final['reservations']),len(final['slots']),len(final['audit_events'])) == (2,8,2)
            write_json(output/'replay-http-final-storage.json',safe_storage(final))
        finally: server.stop()
    return dict(result='PASS',completed=True,requests=20,newly_created=1,replayed=19,unique_booking_ids=1,
                race_reservations=1,race_slots=4,race_creation_audits=1,independent_cookie_jars=20,
                restart_preserves_intents=True,replay_writer_calls=0,audit_failure_rollback=True,failed_key_reusable=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'work/replay-intent-http')
    args=parser.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    target=args.output_dir/'replay-http-result.json'
    write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    try:
        meta.update(source_fingerprints())
        meta['replay_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        meta['verification_dependencies_sha256'] = {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                'scripts/verify_create_booking_http.py', 'scripts/verify_availability_performance.py',
                'scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/fixtures/schema_v1.sql', 'tests/schedule_fixtures.py',
            )
        }
        report=run(args.output_dir,meta)
        write_json(target,meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat()))
    except BaseException as error:
        write_json(target,meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__))
        raise
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

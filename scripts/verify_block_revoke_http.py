"""Twenty real HTTP races between two independent administrator sessions."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import secrets
import tempfile
import threading

from booking_app import ROOT, create_app, db
from booking_app.audit import audit_writer
# 当前直接创建/本人直接取消场景使用合成导师；学生审批另有独立runner。
from tests.direct_booking_fixture import seed_users
from scripts.verify_availability_performance import Client, Server, environment, write_json
from scripts.verify_create_booking_http import FixedClock
from scripts.verify_room_management_http import facts
from tests.maintenance_contract import BLOCK_KEYS, BLOCK_SNAPSHOT_KEYS
from tests.schedule_fixtures import NOW


def server_main(database, port, fault):
    from waitress import serve
    def writer(conn, event):
        if fault == 'after': audit_writer(conn, event)
        if fault: raise RuntimeError('injected audit failure')
        audit_writer(conn, event)
    app = create_app(dict(TESTING=True, DATABASE=database, CLOCK=FixedClock(), AUDIT_WRITER=writer,
                          APP_ORIGIN=f'http://127.0.0.1:{port}', TRUSTED_HOSTS=['127.0.0.1']))
    serve(app, host='127.0.0.1', port=port, threads=8)


class RevokeServer(Server):
    def __init__(self, database, fault=None):
        super().__init__(database)
        self.process = multiprocessing.get_context('spawn').Process(target=server_main, args=(str(database), self.port, fault))


def snapshot(database):
    value = facts(database)
    with db.read_transaction(database) as conn:
        value['observed_transitions'] = [dict(row) for row in conn.execute('SELECT * FROM observed_transitions ORDER BY id')]
    for record in value['reservations']:
        slots = sorted(row['slot_start'] for row in value['occupancy_slots'] if row['reservation_id'] == record['id'])
        assert slots == ([] if record['cancelled_at'] is not None else list(range(record['start_at'], record['end_at'], 1800)))
    return value


def source_hashes():
    paths = [path for path in (ROOT/'booking_app').rglob('*') if path.suffix in {'.py','.sql','.js','.css','.html'}]
    paths += [ROOT/name for name in (
        'scripts/verify_block_revoke_http.py','scripts/verify_block_revoke_browser.py','scripts/verify_block_revoke_browser.cjs',
        'scripts/verify_create_booking_http.py','scripts/verify_availability_performance.py',
        'scripts/verify_room_management_http.py','scripts/verify_history_browser.py','scripts/verify_auth_browser.py','scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/direct_booking_fixture.py', 'tests/fixtures/schema_v1.sql',
        'tests/__init__.py','tests/history_fixtures.py','tests/schedule_fixtures.py','tests/maintenance_contract.py','pyproject.toml','uv.lock')]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def run(output):
    steps = []
    def request(client, phase, url, body):
        status, result, duration = client.request(url, body)
        steps.append(dict(phase=phase, path=url, http_status=status, response=result, duration_ms=duration))
        write_json(output/'http-steps.json', steps)
        return status, result
    with tempfile.TemporaryDirectory(prefix='revoke-http-') as directory:
        database = Path(directory)/'test.sqlite3'
        users = [dict(username=f'revoke_admin_{i}',display_name=f'合成撤销管理员 {i}',role='admin',password=secrets.token_urlsafe(24)) for i in (1,2)]
        members = [dict(username=f'revoke_member_{i}',display_name=f'合成成员 {i}',role='teacher',password=secrets.token_urlsafe(24)) for i in (1,2)]
        seed_users(database, users + members, FixedClock())
        with db.write_transaction(database) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'合成并发会议室','测试楼',20,?,?)", (NOW, NOW))
            # Test-only observer detects actual null -> revoked transitions independently of audit counts.
            conn.execute('CREATE TABLE observed_transitions(id INTEGER PRIMARY KEY,block_id INTEGER,actor_id INTEGER,at INTEGER,reason TEXT)')
            conn.execute('CREATE TRIGGER observe_revoke AFTER UPDATE OF cancelled_at ON reservations '
                         "WHEN OLD.kind='block' AND OLD.cancelled_at IS NULL AND NEW.cancelled_at IS NOT NULL "
                         'BEGIN INSERT INTO observed_transitions(block_id,actor_id,at,reason) '
                         'VALUES(NEW.id,NEW.cancelled_by,NEW.cancelled_at,NEW.cancel_reason); END')
        server = RevokeServer(database); race_results = []
        payload = dict(room_id=1,start='2026-11-13T12:00',end='2026-11-14T14:00',reason='原始停用原因 <维护>')
        try:
            server.start(); clients = [Client(server.origin), Client(server.origin)]
            write_json(output/'environment.json', environment(server, dict(run_id=output.name)) | dict(
                invocation=['.venv/bin/python','-m','scripts.verify_block_revoke_http','--output-dir',str(output)],
                server_start='spawn scripts.verify_block_revoke_http.server_main; Waitress 1 process, 8 threads',
                fixed_now=NOW,independent_admin_sessions=2,rounds=20,
                concurrency_scope='Client barrier synchronizes dispatch; server write-lock waiting is not directly observed.'))
            for client, user in zip(clients, users): client.login(user)
            assert clients[0].jar is not clients[1].jar
            assert {c.value for c in clients[0].jar}.isdisjoint({c.value for c in clients[1].jar})
            identities = [client.request('/api/me')[1]['data']['id'] for client in clients]
            assert identities == [1,2]
            for index in range(20):
                status, created = request(clients[0], 'create', '/api/admin/blocks', payload)
                assert status == 201
                block = created['data']; block_id = block['id']; url = f'/api/admin/blocks/{block_id}/revoke'
                before = snapshot(database); barrier = threading.Barrier(2)
                reasons = [f'第 {index+1} 轮 · 管理员 {i+1} 完成维护' for i in range(2)]
                def compete(i):
                    barrier.wait(timeout=30)
                    status, response, duration = clients[i].request(url, {'reason': f' {reasons[i]} '})
                    return dict(round=index+1, requester_id=identities[i], submitted_reason=reasons[i],
                                http_status=status, response=response, duration_ms=duration)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(compete, i) for i in range(2)]
                    rows = [future.result() for future in as_completed(futures)]
                final = snapshot(database)
                write_json(output/f'round-{index+1:02}.json', dict(responses_in_completion_order=rows,before=before,after=final))
                assert all(row['http_status']==200 for row in rows)
                result = rows[0]['response']['data']
                assert all(row['response']==dict(ok=True,data=result) for row in rows)
                assert set(result)==BLOCK_KEYS and result['status']=='revoked'
                winner = next(row for row in rows if row['requester_id']==result['revoked_by_id'])
                assert result['revoke_reason']==winner['submitted_reason'] and result['revoked_at']==NOW
                assert result['revoked_by_display_name']==users[result['revoked_by_id']-1]['display_name']
                expected_record = next(row for row in before['reservations'] if row['id']==block_id) | dict(
                    cancelled_at=result['revoked_at'],cancelled_by=result['revoked_by_id'],cancel_reason=result['revoke_reason'])
                assert final['reservations']==[expected_record if row['id']==block_id else row for row in before['reservations']]
                assert final['occupancy_slots']==[row for row in before['occupancy_slots'] if row['reservation_id']!=block_id]
                changes = [row for row in final['observed_transitions'] if row['block_id']==block_id]
                assert len(changes)==1 and changes[0]==dict(id=index+1,block_id=block_id,actor_id=result['revoked_by_id'],at=result['revoked_at'],reason=result['revoke_reason'])
                events = [row for row in final['audit_events'] if row['target_type']=='block' and row['target_id']==block_id]
                assert [row['action'] for row in events]==['block.created','block.revoked']
                event = events[-1]; previous = json.loads(event['before_json']); after = json.loads(event['after_json'])
                assert set(previous)==set(after)==BLOCK_SNAPSHOT_KEYS
                assert previous==json.loads(events[0]['after_json'])
                assert after==previous|dict(revoked_at=result['revoked_at'],revoked_by_id=result['revoked_by_id'],revoke_reason=result['revoke_reason'])
                assert (event['actor_id'],event['occurred_at'],event['reason'])==(result['revoked_by_id'],result['revoked_at'],result['revoke_reason'])
                assert len(final['audit_events'])==len(before['audit_events'])+1
                assert request(clients[1], 'repeat', url, {'reason':'后续不同原因'})[1]['data']==result
                assert snapshot(database)==final
                race_results.append(dict(round=index+1,block_id=block_id,first_actor_id=result['revoked_by_id'],
                    first_at=result['revoked_at'],first_reason=result['revoke_reason'],transitions=1,revoke_audits=1,http_200=2))
            status, created = request(clients[0], 'fault_setup', '/api/admin/blocks', payload)
            assert status==201; fault_url=f"/api/admin/blocks/{created['data']['id']}/revoke"
            saved = snapshot(database)
        finally:
            server.stop()
        for mode in ('before','after'):
            server=RevokeServer(database, fault=mode)
            try:
                server.start(); client=Client(server.origin);client.login(users[1])
                status, response=request(client, f'audit_fault_{mode}', fault_url, {'reason':'测试原子回滚'})
                assert status==500 and response['error']['code']=='INTERNAL_ERROR'
                assert snapshot(database)==saved
                write_json(output/f'rollback-{mode}.json', snapshot(database))
            finally:
                server.stop()
        server=RevokeServer(database)
        try:
            server.start();client=Client(server.origin);client.login(users[1])
            assert snapshot(database)==saved
            status,response=request(client,'retry_after_restart',fault_url,{'reason':'故障解除后成功'})
            assert status==200 and response['data']['revoked_by_id']==2
            final=snapshot(database);write_json(output/'final-database-facts.json',final)
            assert len(final['observed_transitions'])==21
        finally:
            server.stop()
    return dict(result='PASS',completed=True,rounds=20,independent_admin_sessions=2,concurrent_http_200=40,
                actual_race_transitions=20,race_revoke_audits=20,first_metadata_verified=True,
                rollback_before_and_after_audit_insert=True,restart_and_retry=True,round_results=race_results)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'work/quality-review-fixes/block-revoke-http')
    args=parser.parse_args(argv);args.output_dir.mkdir(parents=True,exist_ok=True)
    result_path=args.output_dir/'http-result.json'
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(result_path,meta|dict(result='INCOMPLETE',completed=False))
    output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True)
    meta['artifact_directory']='runs/'+meta['run_id']
    write_json(output/'http-result.json',meta|dict(result='INCOMPLETE',completed=False))
    try:
        meta['source_sha256']=source_hashes();report=run(output)
        meta['source_sha256_after']=source_hashes()
        assert meta['source_sha256_after']==meta['source_sha256'], 'Sources changed during verification'
        report=meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        if 'source_sha256' in meta and 'source_sha256_after' not in meta:
            try: meta['source_sha256_after']=source_hashes()
            except OSError: pass
        report=meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__)
    write_json(output/'http-result.json',report);write_json(result_path,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('round_results','source_sha256','source_sha256_after')},ensure_ascii=False,indent=2))
    return 0 if report['completed'] else 1


if __name__=='__main__':
    raise SystemExit(main())

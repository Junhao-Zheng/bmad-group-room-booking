"""Managed desktop/mobile verification with isolated evidence and safe failure reports."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

from booking_app import ROOT, db
from booking_app.audit import audit_writer
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_availability_performance import environment, write_json
from scripts.verify_block_revoke_http import source_hashes
from scripts.verify_create_booking_http import FixedClock
from scripts.verify_history_browser import (browser_wrapper, environment_metadata,
    require_process_groups, run_driver, stop_process_group)
from tests.schedule_fixtures import NOW, insert_record, seed_schedule_fixture

STAGES = {'startup','fault','login','select','validation','csrf','waiting','success','unknown','expired','complete','storage','cleanup','fingerprints'}
SAFE_TYPES = {'AssertionError','Error','TypeError','TimeoutError','SyntaxError','RangeError',
              'RuntimeError','FileNotFoundError','PermissionError','OSError','JSONDecodeError'}
TARGET_REASONS = {112: '<img src=x onerror="window.revokeXss=1">完成维护 390',
                  113: '<img src=x onerror="window.revokeXss=1">完成维护 1280',
                  114: '首次撤销原因', 115: '首次撤销原因'}


class BrowserDriverFailure(RuntimeError):
    def __init__(self, diagnostics):
        super().__init__('Browser verification failed; private driver output omitted')
        self.diagnostics = diagnostics


def failure_diagnostics(output, *, error_type=None, timeout=False):
    def read(name):
        try:
            value = json.loads((output/name).read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}
    value, progress = read('failure-diagnostics.json'), read('progress.json')
    stage = value.get('stage', progress.get('stage', 'startup'))
    kind = 'TimeoutError' if timeout else error_type or value.get('error_type', 'Error')
    source = value.get('source')
    if not (isinstance(source, dict) and source.get('file') == 'scripts/verify_block_revoke_browser.cjs'
            and all(type(source.get(key)) is int and 0 < source[key] < 1000000 for key in ('line','column'))):
        source = None
    else:
        source = {key: source[key] for key in ('file','line','column')}
    result = dict(stage=stage if isinstance(stage,str) and stage in STAGES else 'startup',
                  error_type=kind if isinstance(kind,str) and kind in SAFE_TYPES else 'Error', source=source)
    write_json(output/'failure-diagnostics.json', result)
    return result


def database_facts(database):
    # Capture business facts even when an integrity/oracle check will fail. Never read users/sessions.
    with db.read_transaction(database) as conn:
        return {table: [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('rooms','reservations','occupancy_slots','audit_events')} | dict(
                    integrity_check=conn.execute('PRAGMA integrity_check').fetchone()[0],
                    foreign_key_check=[list(row) for row in conn.execute('PRAGMA foreign_key_check')])


def block_snapshot(row):
    return dict(id=row['id'],room_id=row['room_id'],creator_id=row['user_id'],reason=row['reason'],
                start_at=row['start_at'],end_at=row['end_at'],created_at=row['created_at'],
                revoked_at=row['cancelled_at'],revoked_by_id=row['cancelled_by'],revoke_reason=row['cancel_reason'])


def verify_storage(before, after):
    assert before['integrity_check'] == after['integrity_check'] == 'ok'
    assert before['foreign_key_check'] == after['foreign_key_check'] == []
    assert after['rooms'] == before['rooms'], 'Room directory changed'
    original = {row['id']: row for row in before['reservations']}
    observed = {row['id']: row for row in after['reservations']}
    assert len(original) == len(before['reservations']) == len(after['reservations']) == len(observed)
    assert original.keys() == observed.keys(), 'Record IDs changed or missing'
    assert set(TARGET_REASONS) <= original.keys(), 'Expected targets missing'
    for key, row in original.items():
        expected = row | dict(cancelled_at=NOW,cancelled_by=3,cancel_reason=TARGET_REASONS[key]) if key in TARGET_REASONS else row
        assert observed[key] == expected, f'Record {key} changed beyond its three revocation fields'
    assert after['occupancy_slots'] == [row for row in before['occupancy_slots'] if row['reservation_id'] not in TARGET_REASONS]
    for row in after['reservations']:
        slots = sorted(slot['slot_start'] for slot in after['occupancy_slots'] if slot['reservation_id'] == row['id'])
        assert slots == ([] if row['cancelled_at'] is not None else list(range(row['start_at'],row['end_at'],1800)))
    old_events = {row['id']: row for row in before['audit_events']}
    all_events = {row['id']: row for row in after['audit_events']}
    assert len(all_events) == len(after['audit_events']) == len(old_events) + len(TARGET_REASONS)
    assert {key: all_events.get(key) for key in old_events} == old_events, 'Old audits changed or missing'
    new_events = [row for row in after['audit_events'] if row['id'] not in old_events]
    assert {row['target_id'] for row in new_events} == set(TARGET_REASONS)
    for event in new_events:
        key = event['target_id']
        assert event == dict(id=event['id'],actor_id=3,actor_display_name='演示管理员',action='block.revoked',
            target_type='block',target_id=key,occurred_at=NOW,before_json=event['before_json'],
            after_json=event['after_json'],reason=TARGET_REASONS[key])
        assert json.loads(event['before_json']) == block_snapshot(original[key])
        assert json.loads(event['after_json']) == block_snapshot(observed[key])
    return dict(storage_verified=True,revocations=4,revoke_audits=4,other_records_preserved=True,
                full_target_rows_and_ids_verified=True,rooms_and_old_audits_preserved=True)


def live_group_pids(group_id):
    rows = subprocess.check_output(['ps','-axo','pid=,pgid=,state='],text=True).splitlines()
    return [int(pid) for line in rows for pid, group, state in [line.split()]
            if int(group) == group_id and not state.startswith('Z')]


def run(args):
    require_process_groups()
    with tempfile.TemporaryDirectory(prefix='revoke-browser-') as directory:
        temporary=Path(directory); database=temporary/'test.sqlite3'
        users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
        credentials=temporary/'credentials.json';credentials.touch(mode=0o600);credentials.write_text(json.dumps(dict(users=users)))
        seed_users(database,users,FixedClock());seed_schedule_fixture(database)
        with db.write_transaction(database) as conn:
            for record,room,start,end in [(112,30,'09:00','11:00'),(113,20,'12:00','14:00'),(114,30,'12:00','13:00'),(115,20,'14:00','15:00')]:
                insert_record(conn,record,room,'2026-11-12T'+start,'2026-11-12T'+end,kind='block')
            room=conn.execute('SELECT id,name,location,capacity FROM rooms WHERE id=10').fetchone()
            audit_writer(conn,dict(actor_id=3,actor_display_name='演示管理员',action='room.created',target_type='room',
                                  target_id=10,occurred_at=NOW,before=None,after=dict(room),reason=None))
        before=database_facts(database);write_json(args.output_dir/'database-facts.json',dict(before=before,after=None))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        env=dict(os.environ,BOOKING_DB_PATH=str(database),APP_ORIGIN=origin,COOKIE_SECURE='false',TRUSTED_HOSTS='127.0.0.1',
                 NODE_PATH=str(args.playwright_root.resolve()),REVOKE_BROWSER_FAULT=args.driver_fault or '')
        wrapper,registry=browser_wrapper(temporary,args.browser_executable.resolve())
        command=[sys.executable,'-m','waitress',f'--listen=127.0.0.1:{port}','--threads=8','--call','scripts.verify_auth_browser:create_schedule_verification_app']
        write_json(args.output_dir/'environment.json',environment(SimpleNamespace(origin=origin),dict(run_id=args.output_dir.name)) | dict(
            server_start=command,invocation=['.venv/bin/python','-m','scripts.verify_block_revoke_browser'],
            fixed_now=NOW,viewports=[dict(width=1280,height=800),dict(width=390,height=844)],
            browser=environment_metadata(args),browser_executable=str(args.browser_executable),
            node=subprocess.check_output(['node','--version'],text=True).strip()))
        with (temporary/'waitress.log').open('w') as log:
            server=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True)
            try:
                for _ in range(100):
                    if server.poll() is not None: raise RuntimeError('Verification server startup failed')
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1): break
                    except OSError: time.sleep(.05)
                else: raise RuntimeError('Verification server startup timeout')
                try:
                    process=run_driver(['node',str(ROOT/'scripts/verify_block_revoke_browser.cjs'),origin,str(credentials),str(args.output_dir),str(wrapper)],
                                       env,registry,timeout=args.driver_timeout)
                except subprocess.TimeoutExpired:
                    raise BrowserDriverFailure(failure_diagnostics(args.output_dir,timeout=True)) from None
                if process.returncode:
                    raise BrowserDriverFailure(failure_diagnostics(args.output_dir))
                result=json.loads(process.stdout)
                assert result['result']=='PASS' and [(r['width'],r['height']) for r in result['viewports']]==[(1280,800),(390,844)]
            finally:
                try:
                    after=database_facts(database)
                    write_json(args.output_dir/'database-facts.json',dict(before=before,after=after))
                finally:
                    groups=[int(value) for value in registry.read_text().splitlines()]
                    cleanup=dict(server_group=server.pid,browser_groups=groups,completed=False)
                    write_json(args.output_dir/'process-cleanup.json',cleanup)
                    write_json(args.output_dir/'progress.json',dict(stage='cleanup'))
                    try:
                        stop_process_group(server.pid,server)
                    finally:
                        for group in groups: stop_process_group(group)
                    assert not live_group_pids(server.pid)
                    assert all(not live_group_pids(group) for group in groups)
                    write_json(args.output_dir/'process-cleanup.json',cleanup|dict(completed=True))
        write_json(args.output_dir/'progress.json',dict(stage='storage'))
        result.update(verify_storage(before,after))
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable',type=Path,default=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    parser.add_argument('--playwright-root',type=Path,default=ROOT/'work/browser-tools/node_modules')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'work/quality-review-fixes/block-revoke-browser')
    parser.add_argument('--driver-timeout',type=float,default=120)
    parser.add_argument('--driver-fault',choices=('timeout','secret-error'),help='Verification-only lifecycle fault injection')
    args=parser.parse_args(argv);args.output_dir=args.output_dir.resolve();args.output_dir.mkdir(parents=True,exist_ok=True)
    target=args.output_dir/'browser-result.json'
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True)
    meta['artifact_directory']='runs/'+meta['run_id']
    write_json(output/'browser-result.json',meta|dict(result='INCOMPLETE',completed=False))
    try:
        meta.update(source_sha256=source_hashes(),environment=environment_metadata(args))
        report=run(argparse.Namespace(**(vars(args)|dict(output_dir=output))))
        write_json(output/'progress.json',dict(stage='fingerprints'))
        meta['source_sha256_after']=source_hashes()
        assert meta['source_sha256_after']==meta['source_sha256'], 'Sources changed during verification'
        report=meta|report|dict(result='PASS',completed=True,finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        if 'source_sha256' in meta and 'source_sha256_after' not in meta:
            try: meta['source_sha256_after']=source_hashes()
            except OSError: pass
        diagnostics=error.diagnostics if isinstance(error,BrowserDriverFailure) else failure_diagnostics(output,error_type=type(error).__name__)
        report=meta|dict(result='INCOMPLETE',completed=False,diagnostics=diagnostics)
    write_json(output/'browser-result.json',report);write_json(target,report)
    print(json.dumps({key:value for key,value in report.items() if key not in ('source_sha256','source_sha256_after')},ensure_ascii=False,indent=2))
    return 0 if report['completed'] else 1


if __name__=='__main__':
    raise SystemExit(main())

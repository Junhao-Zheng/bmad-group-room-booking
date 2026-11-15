"""Story 3.2 isolated maintenance-block browser validation with shared verified process lifecycle."""
import argparse
from datetime import datetime, timezone
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

from booking_app import ROOT, db
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_auth_browser import write_report
from tests.history_fixtures import FixedClock
from tests.schedule_fixtures import seed_schedule_fixture, insert_record, NOW
from tests.maintenance_contract import BLOCK_SNAPSHOT_KEYS



from scripts.verify_history_browser import (require_process_groups, stop_process_group,
    browser_wrapper, run_driver, environment_metadata)
from scripts.verify_room_management_http import facts


STAGES = {'startup','open','no-script','room-options','lists','query-errors','csrf','create-wait','invalid','conflict','unknown','session','member','existing-paths'}
SAFE_ERROR_TYPES = {'AssertionError','Error','TypeError','TimeoutError','SyntaxError','RangeError'}


class BrowserDriverFailure(RuntimeError):
    def __init__(self, diagnostics):
        super().__init__('Browser verification failed')
        self.diagnostics = diagnostics


def failure_diagnostics(output, *, timeout=False):
    """Copy only controlled stage/type and the driver's own source coordinates."""
    def read(name):
        try:
            value = json.loads((output / name).read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}
    value, progress = read('failure-diagnostics.json'), read('progress.json')
    stage = value.get('stage', progress.get('stage'))
    error_type = 'TimeoutError' if timeout else value.get('error_type')
    source = value.get('source')
    if not (isinstance(source, dict) and source.get('file') == 'scripts/verify_maintenance_block_browser.cjs'
            and all(type(source.get(key)) is int and 0 < source[key] < 1000000 for key in ('line','column'))):
        source = None
    elif source is not None:
        source = {key: source[key] for key in ('file','line','column')}
    diagnostic = dict(stage=stage if isinstance(stage,str) and stage in STAGES else 'startup',
                      error_type=error_type if isinstance(error_type,str) and error_type in SAFE_ERROR_TYPES else 'Error', source=source)
    write_report(output / 'failure-diagnostics.json', diagnostic)
    return diagnostic


def check_driver_result(result, output):
    if result.returncode:
        raise BrowserDriverFailure(failure_diagnostics(output))
    return json.loads(result.stdout)


def source_fingerprints():
    app_files = sorted(path for path in (ROOT / 'booking_app').rglob('*')
                       if path.is_file() and path.suffix in {'.py','.sql','.js','.css','.html'})
    helpers = [ROOT / path for path in (
        'scripts/verify_maintenance_block_browser.py', 'scripts/verify_maintenance_block_browser.cjs',
        'scripts/verify_history_browser.py',
        'scripts/verify_auth_browser.py', 'scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/fixtures/schema_v1.sql',
        'tests/history_fixtures.py', 'tests/schedule_fixtures.py', 'tests/maintenance_contract.py', 'tests/maintenance_render_contract.cjs', 'scripts/verify_room_management_http.py')]
    def hashes(paths):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'app_source_files_sha256': hashes(app_files), 'verification_source_files_sha256': hashes(helpers)}


def assert_originals_preserved(before, after):
    """Require every original ID, row and slot, not merely surviving rows."""
    for table in ('rooms', 'reservations', 'audit_events'):
        original = {row['id']: row for row in before[table]}
        observed = {row['id']: row for row in after[table] if row['id'] in original}
        assert observed == original, f'Original {table} changed or missing'
    original_ids = {row['id'] for row in before['reservations']}
    original_slots = [row for row in after['occupancy_slots'] if row['reservation_id'] in original_ids]
    ordered = lambda rows: sorted(rows, key=lambda row: (row['room_id'], row['slot_start'], row['reservation_id']))
    assert ordered(original_slots) == ordered(before['occupancy_slots']), 'Original slots changed or missing'


def verify_storage(before, after):
    assert_originals_preserved(before, after)
    original_rooms = {row['id'] for row in before['rooms']}
    original_records = {row['id'] for row in before['reservations']}
    original_events = {row['id'] for row in before['audit_events']}
    rooms = [row for row in after['rooms'] if row['id'] not in original_rooms]
    blocks = [row for row in after['reservations'] if row['id'] not in original_records]
    events = [row for row in after['audit_events'] if row['id'] not in original_events]
    assert len(rooms) == 2 and len(blocks) == 4 and len(events) == 6
    assert {row['name'] for row in rooms} == {'新增选项 1280 <房间>', '新增选项 390 <房间>'}
    for row in rooms:
        assert row['location'] == '新测试楼' and row['capacity'] == 9
        assert row['created_at'] == NOW and row['updated_at'] == NOW
        matches = [event for event in events if event['target_type'] == 'room' and event['target_id'] == row['id']]
        assert len(matches) == 1
        event = matches[0]
        assert event['action'] == 'room.created' and event['before_json'] is None and event['reason'] is None
        assert event['actor_id'] == 3 and event['occurred_at'] == NOW
        assert json.loads(event['after_json']) == {key: row[key] for key in ('id','name','location','capacity')}
    expected = set()
    from tests.schedule_fixtures import epoch
    for width, day, next_day in ((1280, '13', '14'), (390, '17', '18')):
        expected.add((epoch(f'2026-11-{day}T10:00'), epoch(f'2026-11-{next_day}T16:00'), f'<img src=x onerror="window.blockXss=1">维护 {width}'))
        expected.add((epoch(f'2026-11-{next_day}T16:00'), epoch(f'2026-11-{next_day}T17:00'), '响应未知维护'))
    assert {(row['start_at'], row['end_at'], row['reason']) for row in blocks} == expected
    for row in after['reservations']:
        slots = sorted(s['slot_start'] for s in after['occupancy_slots'] if s['reservation_id'] == row['id'])
        assert slots == ([] if row['cancelled_at'] is not None else list(range(row['start_at'], row['end_at'], 1800)))
    for row in blocks:
        assert row['kind'] == 'block' and row['room_id'] == 30 and row['user_id'] == 3 and row['created_at'] == NOW
        matches = [event for event in events if event['target_type'] == 'block' and event['target_id'] == row['id']]
        assert len(matches) == 1
        event = matches[0]
        assert event['action'] == 'block.created' and event['actor_id'] == 3 and event['occurred_at'] == NOW
        assert event['before_json'] is None and event['reason'] == row['reason']
        snapshot = json.loads(event['after_json'])
        assert set(snapshot) == BLOCK_SNAPSHOT_KEYS
        assert snapshot == dict(id=row['id'], room_id=30, creator_id=3, reason=row['reason'], start_at=row['start_at'],
                                end_at=row['end_at'], created_at=NOW, revoked_at=None, revoked_by_id=None, revoke_reason=None)
    return {'slot_audit_invariants_verified': True, 'original_facts_preserved': True,
            'new_rooms': len(rooms), 'new_blocks': len(blocks), 'new_audits': len(events)}


def run(args):
    require_process_groups()
    origin = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe: probe.bind(('127.0.0.1', args.port))
    with tempfile.TemporaryDirectory(prefix='grb-block-browser-') as directory:
        temporary = Path(directory)
        users = [dict(username=u, display_name=d, role=r, password=secrets.token_urlsafe(24)) for u,d,r in (*DEMO_IDENTITIES, ('demo_empty', '合成空记录成员', 'member'))]
        credentials = temporary / 'demo.credentials.json'
        credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'users': users}), encoding='utf-8')
        database = temporary / 'history.sqlite3'
        seed_users(database, users, FixedClock())
        seed_schedule_fixture(database)
        with db.write_transaction(database) as conn:
            insert_record(conn,112,30,'2026-11-12T10:00','2026-11-12T11:00',kind='block')
            # Distinct rendered facts expose missing rows/fields across all four states.
            for row in conn.execute('SELECT * FROM reservations').fetchall():
                conn.execute('UPDATE reservations SET created_at=? WHERE id=?', (NOW-6*86400-row['id']*60, row['id']))
                if row['kind'] == 'booking':
                    values = json.loads(row['request_payload'])
                    values['purpose'] = row['purpose'] + f" #{row['id']}"
                    conn.execute('UPDATE reservations SET purpose=?,request_payload=? WHERE id=?',
                                 (values['purpose'], json.dumps(values, ensure_ascii=False, sort_keys=True), row['id']))
                else:
                    conn.execute('UPDATE reservations SET reason=? WHERE id=?', (row['reason']+f" #{row['id']}", row['id']))
        before = facts(database)
        env = dict(os.environ, BOOKING_DB_PATH=str(database), APP_ORIGIN=origin, COOKIE_SECURE='false',
                   TRUSTED_HOSTS='127.0.0.1', NODE_PATH=str(args.playwright_root.resolve()))
        executable = args.browser_executable
        if executable is None:
            resolved = subprocess.run(['node', '-e', 'process.stdout.write(require("playwright").chromium.executablePath())'],
                env=env, cwd=ROOT, capture_output=True, text=True, check=True, timeout=10, start_new_session=True)
            executable = Path(resolved.stdout)
        wrapper, registry = browser_wrapper(temporary, executable.resolve())
        command = [sys.executable, '-m', 'waitress', f'--listen=127.0.0.1:{args.port}', '--threads=8',
                   '--call', 'scripts.verify_auth_browser:create_schedule_verification_app']
        with (temporary / 'waitress.log').open('w') as log:
            server = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True)
            try:
                for _ in range(100):
                    if server.poll() is not None: raise RuntimeError('Waitress startup failed')
                    try:
                        with socket.create_connection(('127.0.0.1', args.port), timeout=.1): break
                    except OSError: time.sleep(.05)
                else: raise RuntimeError('Waitress startup timeout')
                try:
                    result = run_driver(['node', str(ROOT / 'scripts/verify_maintenance_block_browser.cjs'), origin,
                        str(credentials), str(args.output_dir), str(wrapper)], env, registry)
                except subprocess.TimeoutExpired:
                    raise BrowserDriverFailure(failure_diagnostics(args.output_dir, timeout=True)) from None
                report = check_driver_result(result, args.output_dir)
                after = facts(database)
                report['storage'] = verify_storage(before, after)
                write_report(args.output_dir / 'storage.json', {'before': before, 'after': after, **report['storage']})
                report['server'] = {'command': command, 'threads': 8, 'processes': 1}
                return report
            finally:
                stop_process_group(server.pid, server)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8008)
    parser.add_argument('--playwright-root', type=Path, default=ROOT / 'work/browser-tools/node_modules')
    parser.add_argument('--browser-executable', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/maintenance-block-browser')
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    meta = {'run_id': secrets.token_hex(16), 'started_at_utc': datetime.now(timezone.utc).isoformat()}
    target = args.output_dir / 'browser-results.json'
    write_report(target, meta | {'result': 'INCOMPLETE', 'completed': False})
    run_args = argparse.Namespace(**(vars(args) | {'output_dir': args.output_dir / 'runs' / meta['run_id']}))
    run_args.output_dir.mkdir(parents=True)
    meta['artifact_directory'] = f"runs/{meta['run_id']}"
    try:
        meta.update(environment=environment_metadata(args), **source_fingerprints())
        observed = run(run_args)
        if any(meta[key] != value for key, value in source_fingerprints().items()):
            raise RuntimeError('Verification sources changed during this run')
        report = observed | meta | {'result': 'PASS', 'completed': True,
                                       'finished_at_utc': datetime.now(timezone.utc).isoformat()}
    except BaseException as error:
        report = meta | {'result': 'INCOMPLETE', 'completed': False, 'error_type': type(error).__name__}
        if isinstance(error, BrowserDriverFailure):
            report['diagnostics'] = error.diagnostics
        write_report(target, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    write_report(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__': raise SystemExit(main())

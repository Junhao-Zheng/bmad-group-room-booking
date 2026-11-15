"""Story 3.1 isolated room-management browser validation with shared verified process lifecycle."""
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
from tests.history_fixtures import FixedClock, seed_history_fixture



from scripts.verify_history_browser import (require_process_groups, stop_process_group,
    browser_wrapper, run_driver, environment_metadata)
from scripts.verify_room_management_http import facts


STAGES = {'startup','open','multiline','csrf','create-wait','unchanged','invalid','duplicate',
          'capacity','unknown','session','member','existing-paths'}
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
    if not (isinstance(source, dict) and source.get('file') == 'scripts/verify_room_management_browser.cjs'
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
        'scripts/verify_room_management_browser.py', 'scripts/verify_room_management_browser.cjs',
        'scripts/verify_history_browser.py',
        'scripts/verify_auth_browser.py', 'scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/direct_booking_fixture.py', 'tests/fixtures/schema_v1.sql',
        'tests/history_fixtures.py', 'tests/schedule_fixtures.py', 'scripts/verify_room_management_http.py')]
    def hashes(paths):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'app_source_files_sha256': hashes(app_files), 'verification_source_files_sha256': hashes(helpers)}


def run(args):
    require_process_groups()
    origin = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe: probe.bind(('127.0.0.1', args.port))
    with tempfile.TemporaryDirectory(prefix='grb-room-browser-') as directory:
        temporary = Path(directory)
        users = [dict(username=u, display_name=d, role=r, password=secrets.token_urlsafe(24)) for u,d,r in (*DEMO_IDENTITIES, ('demo_empty', '合成空记录成员', 'member'))]
        credentials = temporary / 'demo.credentials.json'
        credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'users': users}), encoding='utf-8')
        database = temporary / 'history.sqlite3'
        seed_users(database, users, FixedClock())
        seed_history_fixture(database)
        with db.write_transaction(database) as conn:
            for room_id, newline in zip((10,11,12), ('\n','\r','\r\n')):
                conn.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?)',
                             (room_id, f'合成多行 {room_id}上{newline}下', f'东{newline}西', 20,
                              FixedClock().now_epoch(), FixedClock().now_epoch()))
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
                    result = run_driver(['node', str(ROOT / 'scripts/verify_room_management_browser.cjs'), origin,
                        str(credentials), str(args.output_dir), str(wrapper)], env, registry)
                except subprocess.TimeoutExpired:
                    raise BrowserDriverFailure(failure_diagnostics(args.output_dir, timeout=True)) from None
                report = check_driver_result(result, args.output_dir)
                after = facts(database)
                for table in ('reservations','occupancy_slots'):
                    assert after[table] == before[table], 'Room UI cannot change booking facts or slots'
                assert len(after['rooms']) == len(before['rooms']) + 4
                assert len(after['audit_events']) == 12
                assert sum(a['action']=='room.created' for a in after['audit_events']) == 4
                assert sum(a['action']=='room.updated' for a in after['audit_events']) == 8
                for room_id in (10,11,12):
                    old = next(room for room in before['rooms'] if room['id']==room_id)
                    new = next(room for room in after['rooms'] if room['id']==room_id)
                    assert (new['name'],new['location']) == (old['name'],old['location'])
                for event in after['audit_events']:
                    assert event['target_type']=='room' and event['reason'] is None
                    assert set(json.loads(event['after_json']))=={'id','name','location','capacity'}
                write_report(args.output_dir / 'storage.json', {'before': before, 'after': after, 'room_invariants_verified': True})
                report['storage'] = {'room_invariants_verified': True, 'rooms': len(after['rooms']),
                                     'audits': len(after['audit_events'])}
                report['server'] = {'command': command, 'threads': 8, 'processes': 1}
                return report
            finally:
                stop_process_group(server.pid, server)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8007)
    parser.add_argument('--playwright-root', type=Path, default=ROOT / 'work/browser-tools/node_modules')
    parser.add_argument('--browser-executable', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/room-management-browser')
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

"""Story 2.4 isolated cancellation browser validation with shared verified process lifecycle."""
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
    browser_wrapper, run_driver, environment_metadata, facts)


def source_fingerprints():
    app_files = sorted(path for path in (ROOT / 'booking_app').rglob('*')
                       if path.is_file() and path.suffix in {'.py','.sql','.js','.css','.html'})
    helpers = [ROOT / path for path in (
        'scripts/verify_member_cancel_browser.py', 'scripts/verify_member_cancel_browser.cjs',
        'scripts/verify_history_browser.py',
        'scripts/verify_auth_browser.py', 'scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/fixtures/schema_v1.sql',
        'tests/history_fixtures.py', 'tests/schedule_fixtures.py')]
    def hashes(paths):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'app_source_files_sha256': hashes(app_files), 'verification_source_files_sha256': hashes(helpers)}


def run(args):
    require_process_groups()
    origin = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe: probe.bind(('127.0.0.1', args.port))
    with tempfile.TemporaryDirectory(prefix='grb-cancel-browser-') as directory:
        temporary = Path(directory)
        users = [dict(username=u, display_name=d, role=r, password=secrets.token_urlsafe(24)) for u,d,r in (*DEMO_IDENTITIES, ('demo_empty', '合成空记录成员', 'member'))]
        credentials = temporary / 'demo.credentials.json'
        credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({'users': users}), encoding='utf-8')
        database = temporary / 'history.sqlite3'
        seed_users(database, users, FixedClock())
        seed_history_fixture(database)
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
                result = run_driver(['node', str(ROOT / 'scripts/verify_member_cancel_browser.cjs'), origin,
                    str(credentials), str(args.output_dir), str(wrapper)], env, registry)
                if result.returncode: raise RuntimeError('Browser verification failed; private diagnostics omitted')
                report = json.loads(result.stdout)
                after = facts(database)
                originals = {r['id']: r for r in before['reservations']}
                for row in after['reservations']:
                    slots = sorted(s['slot_start'] for s in after['occupancy_slots'] if s['reservation_id']==row['id'])
                    assert slots == ([] if row['cancelled_at'] is not None else list(range(row['start_at'],row['end_at'],1800)))
                    if row['id'] in (103,104):
                        assert row == originals[row['id']] | dict(cancelled_at=FixedClock().now_epoch(),cancelled_by=1,cancel_reason=None)
                    elif row['id'] in originals: assert row == originals[row['id']]
                    else: assert row['cancelled_at']==FixedClock().now_epoch() and row['cancelled_by']==1
                assert len(after['reservations'])==len(before['reservations'])+2
                audits=after['audit_events']
                assert len(audits)==6
                assert sum(a['action']=='booking.cancelled_by_member' for a in audits)==4
                assert sum(a['action']=='booking.created' for a in audits)==2
                write_report(args.output_dir / 'storage.json', {'before': before, 'after': after, 'cancellation_invariants_verified': True})
                report['storage'] = {'cancellation_invariants_verified': True, 'reservations': len(after['reservations']),
                                     'slots': len(after['occupancy_slots']), 'audits': len(after['audit_events'])}
                report['server'] = {'command': command, 'threads': 8, 'processes': 1}
                return report
            finally:
                stop_process_group(server.pid, server)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8006)
    parser.add_argument('--playwright-root', type=Path, default=ROOT / 'work/browser-tools/node_modules')
    parser.add_argument('--browser-executable', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/member-cancel-browser')
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
        write_report(target, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    write_report(target, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__': raise SystemExit(main())

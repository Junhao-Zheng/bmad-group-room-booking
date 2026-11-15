"""Story 2.3 isolated file DB, real Waitress/Chromium, private ephemeral credentials."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import shlex
import signal
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time

from booking_app import ROOT, db
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_auth_browser import write_report
from tests.history_fixtures import FixedClock, seed_history_fixture



def require_process_groups():
    if sys.platform not in ('darwin', 'linux'):
        raise RuntimeError('Browser verification supports macOS/Linux POSIX process groups only')


def stop_process_group(group_id, process=None, grace=1):
    """Only a group created by this runner or its private browser wrapper is accepted."""
    if group_id <= 1 or group_id == os.getpgrp():
        raise ValueError('Refusing to signal the caller process group')
    def send(sig):
        try: os.killpg(group_id, sig)
        except ProcessLookupError: return False
        except PermissionError:
            # macOS can report EPERM while a just-terminated group contains only zombies.
            # A live member still means cleanup failed; never blanket-ignore denied signals.
            if process is not None: process.poll()
            rows = subprocess.check_output(['ps', '-axo', 'pgid=,state='], text=True).splitlines()
            if any(int(group) == group_id and not state.startswith('Z')
                   for group, state in (row.split() for row in rows)):
                raise
            return False
        return True
    if send(signal.SIGTERM):
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if process is not None: process.poll()  # Reap the group leader when it exits.
            if not send(0): break
            time.sleep(.02)
        # Also handles a leader that exited while its children ignored SIGTERM.
        send(signal.SIGKILL)
    if process is not None:
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def browser_wrapper(temporary, executable):
    """Register Chromium's own detached group before exec; survives a killed Node parent."""
    registry = temporary / 'browser-groups.txt'
    registry.touch(mode=0o600)
    launcher = temporary / 'launch_browser.py'
    launcher.write_text('import os, sys\n'
        'if os.getpgrp() != os.getpid(): os.setsid()\n'
        f'with open({str(registry)!r}, "a") as stream: stream.write(str(os.getpgrp()) + "\\n")\n'
        f'os.execv({str(executable)!r}, [{str(executable)!r}, *sys.argv[1:]])\n', encoding='utf-8')
    launcher.chmod(0o600)
    wrapper = temporary / 'browser-wrapper'
    wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(launcher))} "$@"\n', encoding='utf-8')
    wrapper.chmod(0o700)
    return wrapper, registry


def run_driver(command, env, registry, timeout=120):
    """Reap Node and every registered browser group on success, failure and timeout."""
    require_process_groups()
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        stop_process_group(process.pid, process)
        # Playwright starts Chromium in a separate detached group; killing Node alone is insufficient.
        for value in registry.read_text().splitlines():
            stop_process_group(int(value))
        if process.stdout: process.stdout.close()
        if process.stderr: process.stderr.close()


def source_fingerprints():
    app_files = sorted(path for path in (ROOT / 'booking_app').rglob('*')
                       if path.is_file() and path.suffix in {'.py','.sql','.js','.css','.html'})
    helpers = [ROOT / path for path in (
        'scripts/verify_history_browser.py', 'scripts/verify_history_browser.cjs',
        'scripts/verify_auth_browser.py', 'scripts/init_demo.py', 'scripts/migrate_db.py', 'scripts/backup_db.py', 'tests/legacy_fixture.py', 'tests/fixtures/schema_v1.sql',
        'tests/history_fixtures.py', 'tests/schedule_fixtures.py')]
    def hashes(paths):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'app_source_files_sha256': hashes(app_files), 'verification_source_files_sha256': hashes(helpers)}


def environment_metadata(args):
    return {'platform': platform.platform(), 'supported_runtime': 'macOS/Linux POSIX process groups; Playwright 1.58.2',
            'python': sys.version, 'sqlite': sqlite3.sqlite_version,
            'packages': {name: importlib.metadata.version(name) for name in ('Flask','Jinja2','Werkzeug','waitress')},
            'playwright': json.loads((args.playwright_root / 'playwright/package.json').read_text())['version']}


def facts(database):
    with db.read_transaction(database) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        return {table: [dict(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('reservations', 'occupancy_slots', 'audit_events')}


def run(args):
    require_process_groups()
    origin = f'http://127.0.0.1:{args.port}'
    with socket.socket() as probe: probe.bind(('127.0.0.1', args.port))
    with tempfile.TemporaryDirectory(prefix='grb-history-browser-') as directory:
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
                result = run_driver(['node', str(ROOT / 'scripts/verify_history_browser.cjs'), origin,
                    str(credentials), str(args.output_dir), str(wrapper)], env, registry)
                if result.returncode: raise RuntimeError('Browser verification failed; private diagnostics omitted')
                report = json.loads(result.stdout)
                after = facts(database)
                assert before == after, 'History queries must not mutate bookings, slots or audits'
                write_report(args.output_dir / 'storage.json', {'before': before, 'after': after, 'unchanged': True})
                report['storage'] = {'unchanged': True, 'reservations': len(after['reservations']),
                                     'slots': len(after['occupancy_slots']), 'audits': len(after['audit_events'])}
                report['server'] = {'command': command, 'threads': 8, 'processes': 1}
                return report
            finally:
                stop_process_group(server.pid, server)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8004)
    parser.add_argument('--playwright-root', type=Path, default=ROOT / 'work/browser-tools/node_modules')
    parser.add_argument('--browser-executable', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/history-browser')
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

"""Real Chrome checks for management confirmation handoff, using private temporary data."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from zoneinfo import ZoneInfo

from booking_app import ROOT, db
from booking_app.domain import SystemClock
from tests.legacy_fixture import DEMO_IDENTITIES, seed_users
from scripts.verify_audit_http import LiveServer, facts, evidence_facts, source_hashes
from scripts.verify_availability_performance import write_json
from scripts.verify_history_browser import browser_wrapper, run_driver, environment_metadata


def run(args, output):
    with tempfile.TemporaryDirectory(prefix='epic3-followup-') as directory:
        temporary = Path(directory)
        database = temporary / 'verification.sqlite3'
        users = [dict(username=u, display_name=d, role=r, password=secrets.token_urlsafe(24))
                 for u, d, r in DEMO_IDENTITIES]
        credentials = temporary / 'credentials.json'
        credentials.touch(mode=0o600)
        day = str((datetime.now(ZoneInfo('Asia/Shanghai')) + timedelta(days=1)).date())
        credentials.write_text(json.dumps(dict(users=users, day=day)))
        seed_users(database, users, SystemClock())
        now = SystemClock().now_epoch()
        with db.write_transaction(database) as conn:
            for room_id in (1, 2):
                conn.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?)',
                             (room_id, f'合成会议室 {room_id}', '合成楼', 20, now, now))
        before = facts(database)
        server = LiveServer(database, temporary)
        env = dict(os.environ, NODE_PATH=str(args.playwright_root.resolve()))
        wrapper, registry = browser_wrapper(temporary, args.browser_executable.resolve())
        try:
            server.start()
            write_json(output / 'environment.json', dict(environment_metadata(args),
                server_command=server.command, browser_executable=str(args.browser_executable.resolve()),
                clock='production SystemClock', temporary_database=True,
                invocation=[sys.executable, '-m', 'scripts.verify_epic3_followup_browser', *sys.argv[1:]]))
            result = run_driver(['node', str(ROOT / 'scripts/verify_epic3_followup_browser.cjs'),
                server.origin, str(credentials), str(output), str(wrapper)], env, registry, timeout=180)
            if result.returncode:
                raise RuntimeError('Browser verification failed; see sanitized failure.json')
            report = json.loads(result.stdout)
            assert report['result'] == 'PASS' and len(report['viewports']) == 2
            after = facts(database)
            assert len(after['rooms']) == 2
            for row in after['rooms']:
                assert row['name'] == f'更新后的会议室 {row["id"]}'
            assert len(after['reservations']) == 2 and len(after['occupancy_slots']) == 4
            assert all(row['kind'] == 'block' and row['cancelled_at'] is None for row in after['reservations'])
            assert sorted(row['action'] for row in after['audit_events']) == ['block.created'] * 2 + ['room.updated'] * 2
            write_json(output / 'database-facts.json', dict(before=evidence_facts(before), after=evidence_facts(after),
                final_storage_verified=True))
        finally:
            server.stop()
            write_json(output / 'process-cleanup.json', dict(server_pids=server.pids,
                browser_groups=[int(value) for value in registry.read_text().splitlines()], completed=True))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs/evidence/epic-3-followup/browser')
    parser.add_argument('--browser-executable', type=Path,
                        default=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    parser.add_argument('--playwright-root', type=Path, default=ROOT / 'work/browser-tools/node_modules')
    args = parser.parse_args(argv)
    meta = dict(run_id=secrets.token_hex(16), started_at_utc=datetime.now(timezone.utc).isoformat())
    output = args.output_dir.resolve() / 'runs' / meta['run_id']
    output.mkdir(parents=True)
    target = output / 'result.json'
    write_json(target, meta | dict(result='INCOMPLETE', completed=False))
    try:
        meta['source_sha256_before'] = source_hashes()
        write_json(output / 'source-before.json', meta['source_sha256_before'])
        report = run(args, output)
        meta['source_sha256_after'] = source_hashes()
        write_json(output / 'source-after.json', meta['source_sha256_after'])
        assert meta['source_sha256_before'] == meta['source_sha256_after']
        report = meta | report | dict(finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        write_json(target, meta | dict(result='INCOMPLETE', completed=False, error_type=type(error).__name__))
        print(json.dumps(dict(result='INCOMPLETE', artifact_directory=str(output), error_type=type(error).__name__)))
        return 1
    write_json(target, report)
    print(json.dumps(dict(result='PASS', artifact_directory=str(output), viewports=report['viewports']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Portable browser verification using a separately installed pinned Playwright."""

import argparse
from datetime import datetime, timezone
import json
import hashlib
import importlib.metadata
import platform
import sqlite3
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from booking_app import ROOT
from scripts.init_demo import DEMO_IDENTITIES


def create_schedule_verification_app():
    """Waitress test factory; the production factory has no clock environment switch."""
    from booking_app import create_app
    from tests.schedule_fixtures import NOW

    class FixtureClock:
        def now_epoch(self):
            return NOW

    return create_app({"TESTING": True, "CLOCK": FixtureClock()})


def verify_committed_response_loss(database, report):
    """Read the real file DB after browser delivery loss; no test HTTP endpoints."""
    from booking_app import db

    verified = []
    with db.read_transaction(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        for result in report["results"]:
            expected = result["booking"]["committed_response_lost"]
            assert expected["http_status"] == 201 and expected["request_count"] == 1
            rows = conn.execute(
                "SELECT * FROM reservations WHERE room_id=? AND start_at=? AND end_at=?",
                (expected["room_id"], expected["start_at"], expected["end_at"]),
            ).fetchall()
            assert len(rows) == 1
            booking = rows[0]
            assert booking["id"] == expected["booking_id"] and booking["title"] == expected["title"]
            assert booking["kind"] == "booking" and booking["cancelled_at"] is None
            slots = [dict(row) for row in conn.execute(
                "SELECT room_id,slot_start,reservation_id FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start",
                (booking["id"],),
            )]
            assert slots == [dict(room_id=booking["room_id"], slot_start=t, reservation_id=booking["id"])
                             for t in range(booking["start_at"], booking["end_at"], 1800)]
            audits = [dict(row) for row in conn.execute(
                "SELECT id,actor_id,action,target_type,target_id,occurred_at,before_json,after_json,reason "
                "FROM audit_events WHERE target_type='booking' AND target_id=?", (booking["id"],),
            )]
            assert len(audits) == 1 and audits[0]["action"] == "booking.created"
            assert audits[0]["actor_id"] == booking["user_id"]
            assert audits[0]["before_json"] is None and audits[0]["reason"] is None
            assert json.loads(audits[0]["after_json"]) == dict(
                id=booking["id"],room_id=booking["room_id"],owner_id=booking["user_id"],
                title=booking["title"],purpose=booking["purpose"],attendees=booking["attendees"],
                start_at=booking["start_at"],end_at=booking["end_at"],created_at=booking["created_at"],
                cancelled_at=None,cancelled_by_id=None,cancel_reason=None)
            verified.append(dict(viewport=result["viewport"], booking_id=booking["id"], matching_reservations=1,
                                 slots=slots, creation_audits=audits, result="PASS"))
        for result in report["results"]:
            evidence = result["booking"]["explicit_retry_same_intent"]
            assert evidence["statuses"] == [201, 200, 201]
            assert evidence["original_id"] == evidence["replayed_id"] != evidence["new_id"]
            rows = conn.execute("SELECT * FROM reservations WHERE id IN (?,?) ORDER BY id",
                                (evidence["original_id"], evidence["new_id"])).fetchall()
            assert len(rows) == 2
            import hashlib
            hashes = [hashlib.sha256(row["intent_key"].encode()).hexdigest() for row in rows]
            assert hashes == [evidence["request_hashes"][0], evidence["request_hashes"][2]]
            assert evidence["request_hashes"][0] == evidence["request_hashes"][1] != evidence["request_hashes"][2]
            for row in rows:
                slots = [slot[0] for slot in conn.execute(
                    "SELECT slot_start FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start", (row["id"],))]
                assert slots == list(range(row["start_at"], row["end_at"], 1800))
                assert conn.execute("SELECT count(*) FROM audit_events WHERE target_type='booking' AND target_id=? AND action='booking.created'",
                                    (row["id"],)).fetchone()[0] == 1
            verified.append(dict(viewport=result["viewport"], original_id=evidence["original_id"],
                replayed_id=evidence["replayed_id"], edited_new_id=evidence["new_id"],
                key_hashes_match=True, records=2, creation_audits=2, slots_per_booking=2, result="PASS"))
        for result in report["results"]:
            expected = result["booking"]["not_delivered_retry"]
            assert expected["statuses"] == [None, 201]
            assert expected["pre_retry_matching_records"] == 0
            assert expected["request_hashes"][0] == expected["request_hashes"][1]
            rows = conn.execute("SELECT * FROM reservations WHERE room_id=? AND start_at=? AND end_at=?",
                                (expected["room_id"], expected["start_at"], expected["end_at"])).fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row["id"] == expected["booking_id"] and row["title"] == expected["title"]
            assert hashlib.sha256(row["intent_key"].encode()).hexdigest() == expected["request_hashes"][0]
            slots = [dict(slot) for slot in conn.execute(
                "SELECT room_id,slot_start,reservation_id FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start",
                (row["id"],))]
            assert slots == [dict(room_id=row["room_id"], slot_start=t, reservation_id=row["id"])
                             for t in range(row["start_at"], row["end_at"], 1800)]
            audits = [dict(event) for event in conn.execute(
                "SELECT id,action,target_id FROM audit_events WHERE target_type='booking' AND target_id=?", (row["id"],))]
            assert len(audits) == 1 and audits[0]["action"] == 'booking.created'
            verified.append(dict(viewport=result["viewport"], scenario='request_not_delivered_then_retry',
                booking_id=row["id"], matching_reservations=1, key_hash_match=True,
                slots=slots, creation_audits=audits, result='PASS'))
    return verified


def run_browser(args):
    origin = f"http://127.0.0.1:{args.port}"
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", args.port))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="grb-browser-") as directory:
        temporary = Path(directory)
        credentials = temporary / "demo.credentials.json"
        credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({"users": [
            {"username": username, "display_name": display, "role": role, "password": secrets.token_urlsafe(24)}
            for username, display, role in DEMO_IDENTITIES
        ]}), encoding="utf-8")
        env = dict(os.environ, BOOKING_DB_PATH=str(temporary / "booking.sqlite3"), APP_ORIGIN=origin,
                   COOKIE_SECURE="false", TRUSTED_HOSTS="127.0.0.1",
                   NODE_PATH=str(args.playwright_root.resolve()))
        subprocess.run([sys.executable, "-m", "scripts.init_demo", "--credentials-file", str(credentials)],
                       cwd=ROOT, env=env, check=True, capture_output=True, text=True)
        if args.schedule:
            from tests.schedule_fixtures import seed_schedule_fixture
            seed_schedule_fixture(temporary / "booking.sqlite3")
            # Browser-only variant: ID must differ from capacity to detect wrong DOM bindings.
            from booking_app import db
            with db.write_transaction(temporary / "booking.sqlite3") as conn:
                conn.execute("UPDATE rooms SET capacity=31 WHERE id=30")
                conn.execute("UPDATE reservations SET reason=? WHERE id=108", ("合成晚间维护 <校准投影>",))
        factory = "scripts.verify_auth_browser:create_schedule_verification_app" if args.schedule else "booking_app:create_app"
        command = [sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{args.port}",
                   "--threads=8", "--call", factory]
        with (temporary / "waitress.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Waitress failed to start.")
                    try:
                        with socket.create_connection(("127.0.0.1", args.port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError("Waitress startup timed out.")
                browser_command = ["node", str(ROOT / "scripts/verify_auth_browser.cjs"), origin,
                                   str(credentials), str(args.output_dir.resolve())]
                browser_command.append(str(args.browser_executable.resolve()) if args.browser_executable else "")
                browser_command.append("booking" if args.booking else "availability" if args.availability else "schedule" if args.schedule else "auth")
                result = subprocess.run(browser_command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
                if result.returncode:
                    # Browser failures may include input values; do not print raw diagnostics.
                    raise RuntimeError("Browser verification failed; no credential-bearing diagnostics were printed.")
                report = json.loads(result.stdout)
                executed_package = Path(report['execution']['playwright_package_path']).resolve()
                if executed_package != (args.playwright_root / 'playwright/package.json').resolve():
                    raise RuntimeError('Loaded Playwright differs from the requested installation')
                if args.booking:
                    report["committed_response_loss_storage"] = verify_committed_response_loss(temporary / "booking.sqlite3", report)
                report["server"] = {"processes": 1, "threads": 8, "origin": origin, "command": command}
                if args.schedule:
                    from booking_app.domain import local_time
                    from tests.schedule_fixtures import NOW
                    report["clock"] = {"kind": "fixed_fixture", "now_epoch": NOW, "now_local": local_time(NOW)}
            finally:
                server.terminate()
                server.wait(timeout=10)
    return report


def write_report(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def source_fingerprints():
    app_files = sorted(path for path in (ROOT / 'booking_app').rglob('*')
                       if path.is_file() and path.suffix in {'.py','.sql','.js','.css','.html'})
    helpers = [ROOT / path for path in ('scripts/verify_auth_browser.py',
        'scripts/verify_auth_browser.cjs', 'scripts/init_demo.py', 'tests/schedule_fixtures.py')]
    def hashes(paths):
        return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    return {'app_source_files_sha256': hashes(app_files), 'verification_source_files_sha256': hashes(helpers)}


def environment_metadata(args):
    return {'platform': platform.platform(), 'python': sys.version, 'sqlite': sqlite3.sqlite_version,
            'packages': {name: importlib.metadata.version(name) for name in ('Flask','Jinja2','Werkzeug','waitress')},
            'playwright': json.loads((args.playwright_root / 'playwright/package.json').read_text())['version']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--playwright-root", type=Path, default=ROOT / "work/browser-tools/node_modules")
    parser.add_argument("--browser-executable", type=Path, help="Optional existing Chrome/Chromium executable; default uses Playwright Chromium")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/browser-verification")
    parser.add_argument("--schedule", action="store_true", help="Include Story 1.2 synthetic schedule fixtures and checks")
    parser.add_argument("--availability", action="store_true", help="Include Story 1.3 availability plus login/logout and schedule checks")
    parser.add_argument("--booking", action="store_true", help="Include Story 2.1 booking creation and conflict checks")
    parser.add_argument("--replay", action="store_true", help="Include Story 2.2 lost-response replay and edited new intent checks")
    args = parser.parse_args()
    args.booking = args.booking or args.replay
    args.availability = args.availability or args.booking
    args.schedule = args.schedule or args.availability
    args.output_dir.mkdir(parents=True, exist_ok=True)
    meta = dict(run_id=secrets.token_hex(16), started_at_utc=datetime.now(timezone.utc).isoformat())
    meta['artifact_directory'] = f"runs/{meta['run_id']}"
    meta['configuration'] = {'port': args.port, 'schedule':args.schedule, 'availability':args.availability,
        'booking':args.booking, 'replay':args.replay, 'playwright_root':str(args.playwright_root.resolve()),
        'browser_executable':str(args.browser_executable.resolve()) if args.browser_executable else None}
    target = args.output_dir / 'browser-results.json'
    write_report(target, meta | dict(result='INCOMPLETE', completed=False))
    try:
        meta.update(environment=environment_metadata(args), **source_fingerprints())
        run_args = argparse.Namespace(**(vars(args) | {'output_dir': args.output_dir / meta['artifact_directory']}))
        run_args.output_dir.mkdir(parents=True)
        report = run_browser(run_args)
        if any(meta[key] != value for key, value in source_fingerprints().items()):
            raise RuntimeError('Verification sources changed during this run')
        meta['screenshots_sha256'] = {
            str(path.relative_to(args.output_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run_args.output_dir.glob('*.png'))}
        if not meta['screenshots_sha256']:
            raise RuntimeError('Browser verification produced no screenshots')
        report = report | meta | dict(result='PASS', completed=True, finished_at_utc=datetime.now(timezone.utc).isoformat())
        write_report(target, report)
    except BaseException as error:
        report = meta | dict(result='INCOMPLETE', completed=False, error_type=type(error).__name__,
                             finished_at_utc=datetime.now(timezone.utc).isoformat())
        write_report(target, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

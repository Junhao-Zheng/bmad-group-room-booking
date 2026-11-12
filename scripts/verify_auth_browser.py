"""Portable browser verification using a separately installed pinned Playwright."""

import argparse
import json
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--playwright-root", type=Path, default=ROOT / "work/browser-tools/node_modules")
    parser.add_argument("--browser-executable", type=Path, help="Optional existing Chrome/Chromium executable; default uses Playwright Chromium")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/browser-verification")
    parser.add_argument("--schedule", action="store_true", help="Include Story 1.2 synthetic schedule fixtures and checks")
    args = parser.parse_args()
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
                browser_command.append("schedule" if args.schedule else "auth")
                result = subprocess.run(browser_command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=120)
                if result.returncode:
                    # Browser failures may include input values; do not print raw diagnostics.
                    raise RuntimeError("Browser verification failed; no credential-bearing diagnostics were printed.")
                report = json.loads(result.stdout)
                report["server"] = {"processes": 1, "threads": 8, "origin": origin, "command": command}
                if args.schedule:
                    from booking_app.domain import local_time
                    from tests.schedule_fixtures import NOW
                    report["clock"] = {"kind": "fixed_fixture", "now_epoch": NOW, "now_local": local_time(NOW)}
                evidence = json.dumps(report, ensure_ascii=False, indent=2)
                (args.output_dir / "browser-results.json").write_text(evidence + "\n", encoding="utf-8")
                print(evidence)
            finally:
                server.terminate()
                server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

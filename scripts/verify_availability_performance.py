"""NFR-03: reproducible, real HTTP availability measurement, isolated from demo data."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import http.cookiejar
import importlib.metadata
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import random
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlencode
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

from booking_app import ROOT, db
from tests.legacy_fixture import seed_users

SEED = 20261112
BASE_LOCAL = datetime(2026, 11, 12, 8, tzinfo=ZoneInfo("Asia/Shanghai"))
BASE = int(BASE_LOCAL.timestamp())


class FixedClock:
    def now_epoch(self):
        return BASE


def strict_json_equal(actual, expected):
    """Compare the complete JSON contract without Python's bool/int/float coercion."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(strict_json_equal(actual[k], value) for k, value in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(strict_json_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


class ResponseParseError(Exception):
    """Safe response diagnostics, retaining status without retaining raw content."""
    def __init__(self, status, error_type, raw, duration_ms):
        super().__init__(error_type)
        self.status, self.error_type, self.duration_ms = status, error_type, duration_ms
        self.body_bytes = len(raw)
        self.body_sha256 = hashlib.sha256(raw).hexdigest()


def server_main(database, port):
    from booking_app import create_app
    from waitress import serve
    app = create_app({"TESTING": True, "DATABASE": database, "CLOCK": FixedClock(),
                      "APP_ORIGIN": f"http://127.0.0.1:{port}", "TRUSTED_HOSTS": ["127.0.0.1"],
                      "SESSION_COOKIE_SECURE": False})
    serve(app, host="127.0.0.1", port=port, threads=8)


class Server:
    def __init__(self, database):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.origin = f"http://127.0.0.1:{self.port}"
        self.process = multiprocessing.get_context("spawn").Process(
            target=server_main, args=(str(database), self.port))

    def start(self):
        self.process.start()
        for _ in range(200):
            if not self.process.is_alive():
                raise RuntimeError("Measurement server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=.1):
                    return
            except OSError:
                time.sleep(.025)
        raise RuntimeError("Measurement server startup timed out")

    def stop(self):
        if self.process.pid is not None:
            self.process.terminate()
            self.process.join(10)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(10)
            assert not self.process.is_alive()


class Client:
    def __init__(self, origin):
        self.origin, self.csrf = origin, None
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, path, body=None):
        headers = {} if body is None else {
            "Origin": self.origin, "X-CSRF-Token": self.csrf or "", "Content-Type": "application/json",
        }
        request = urllib.request.Request(self.origin + path, headers=headers,
            data=None if body is None else json.dumps(body).encode())
        started = time.perf_counter()
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                data = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw.decode()
            except (ValueError, UnicodeError) as error:
                raise ResponseParseError(response.status, type(error).__name__, raw,
                                         (time.perf_counter() - started) * 1000) from None
            elapsed = (time.perf_counter() - started) * 1000
            return response.status, data, elapsed

    def login(self, user):
        status, page, _ = self.request("/login")
        assert status == 200
        self.csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        status, data, _ = self.request("/api/login", {key: user[key] for key in ("username", "password")})
        assert status == 200 and data["ok"] is True
        self.csrf = data["data"]["csrf_token"]


def seed_fixture(database, user_ids):
    rng = random.Random(SEED)
    rooms, records = [], []
    with db.write_transaction(database) as conn:
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0
        for room_id in range(1, 11):
            room = {"id": room_id, "name": f"性能合成房间 {room_id:02}", "location": "固定负载", "capacity": room_id * 10}
            rooms.append(room)
            conn.execute("INSERT INTO rooms(id,name,location,capacity,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                         (*room.values(), BASE, BASE))
            cancelled_indexes = set(rng.sample(range(100), 20))
            for n in range(100):
                local = (BASE_LOCAL + timedelta(days=n // 2 - 25)).replace(hour=9 + n % 2)
                start, end = int(local.timestamp()), int(local.timestamp()) + 1800
                record_id = (room_id - 1) * 100 + n + 1
                owner, cancelled = rng.choice(user_ids), n in cancelled_indexes
                title = f"性能合成活动 {record_id}"
                created_at = min(start - 86400, BASE - 86400)
                cancelled_at = min(start - 3600, BASE - 3600) if cancelled else None
                payload = json.dumps(dict(room_id=room_id, title=title, purpose="固定合成负载", attendees=2,
                                          start_at=start, end_at=end), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                conn.execute(
                    "INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,"
                    "intent_key,request_payload,created_at,cancelled_at,cancelled_by,cancel_reason) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record_id, "booking", room_id, owner, title, "固定合成负载", 2, start, end,
                     f"performance-intent-{record_id:04}", payload, created_at,
                     cancelled_at, owner if cancelled else None, None),
                )
                if not cancelled:
                    conn.execute("INSERT INTO occupancy_slots VALUES(?,?,?)", (room_id, start, record_id))
                records.append(dict(id=record_id, room_id=room_id, start=start, end=end, cancelled=cancelled,
                                    created_at=created_at, cancelled_at=cancelled_at))
    return {"seed": SEED, "base_epoch": BASE, "rooms": rooms, "bookings": records}


def verify_fixture(database, fixture):
    with db.read_transaction(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 10
        rows = conn.execute("SELECT id,room_id,start_at,end_at,created_at,cancelled_at FROM reservations").fetchall()
        assert len(rows) == 1000
        expected_records = {r["id"]: r for r in fixture["bookings"]}
        for row in rows:
            record = expected_records[row["id"]]
            assert (row["room_id"], row["start_at"], row["end_at"], row["cancelled_at"] is not None) == (
                record["room_id"], record["start"], record["end"], record["cancelled"])
            assert row["created_at"] == record["created_at"] < min(BASE, row["start_at"])
            assert row["cancelled_at"] == record["cancelled_at"]
            if row["cancelled_at"] is not None:
                assert row["created_at"] < row["cancelled_at"] < min(BASE, row["start_at"])
            actual = [(r["room_id"], r["slot_start"]) for r in conn.execute(
                "SELECT room_id,slot_start FROM occupancy_slots WHERE reservation_id=? ORDER BY slot_start", (row["id"],))]
            expected = [] if record["cancelled"] else [(record["room_id"], t) for t in range(record["start"], record["end"], 1800)]
            assert actual == expected
        return {"rooms": 10, "bookings": 1000, "slots": conn.execute("SELECT count(*) FROM occupancy_slots").fetchone()[0],
                "integrity_check": "ok", "foreign_key_check": "ok", "all_slots_exact": True,
                "all_created_and_cancelled_before_fixed_now_in_order": True}


def measure(clients, fixture, output_dir, run_id):
    samples = []

    def one(index, phase, client, barrier):
        local = (BASE_LOCAL + timedelta(days=1 + index % 6)).replace(hour=9 + index % 3)
        end = local + timedelta(minutes=30)
        attendees = [5, 15, 25, 100, 1001][index % 5]
        query = dict(start=local.strftime("%Y-%m-%dT%H:%M"), end=end.strftime("%Y-%m-%dT%H:%M"), attendees=attendees)
        # Independent in-memory oracle, with no call to application query/domain code.
        expected = [room for room in fixture["rooms"] if room["capacity"] >= attendees and not any(
            r["room_id"] == room["id"] and not r["cancelled"] and r["start"] < int(end.timestamp())
            and int(local.timestamp()) < r["end"] for r in fixture["bookings"])]
        sample = dict(run_id=run_id, index=index, phase=phase, client=index % 10, query=query,
                      query_path="over_capacity_fast_path" if attendees > 1000 else "sql_availability",
                      expected={"ok": True, "data": {"items": expected, "total": len(expected)}})
        started = time.perf_counter()
        try:
            barrier.wait(timeout=30)
            status, body, duration = client.request("/api/availability?" + urlencode(query))
            sample.update(http_status=status, response=body, duration_ms=duration,
                          correct=status == 200 and strict_json_equal(body, sample["expected"]), error=None)
        except ResponseParseError as error:
            sample.update(http_status=error.status, response=None, duration_ms=error.duration_ms,
                          correct=False, error=error.error_type, body_bytes=error.body_bytes,
                          body_sha256=error.body_sha256)
        except Exception as error:
            sample.update(http_status=None, response=None, duration_ms=(time.perf_counter() - started) * 1000,
                          correct=False, error=type(error).__name__)
        return sample

    raw_path = output_dir / "performance-samples.jsonl"
    # Incrementally persist every result, including errors and slow samples.
    with raw_path.open("w", encoding="utf-8") as raw, ThreadPoolExecutor(max_workers=10) as pool:
        for batch in range(22):
            barrier = threading.Barrier(10)
            phase = "warmup" if batch < 2 else "measured"
            pending = [pool.submit(one, batch * 10 + j, phase, clients[j], barrier) for j in range(10)]
            for future in pending:
                sample = future.result()
                samples.append(sample)
                raw.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
                raw.flush()
    measured = [row for row in samples if row["phase"] == "measured"]
    ordered = sorted(row["duration_ms"] for row in measured)
    rank = math.ceil(.95 * len(ordered))
    errors = sum(row["http_status"] != 200 or row["error"] is not None for row in samples)
    wrong = sum(not row["correct"] for row in samples)
    by_path = {}
    for name in ("sql_availability", "over_capacity_fast_path"):
        all_path = [row for row in samples if row["query_path"] == name]
        path_measured = [row for row in measured if row["query_path"] == name]
        times = sorted(row["duration_ms"] for row in path_measured)
        by_path[name] = {"warmup_requests": len(all_path) - len(path_measured),
                         "measured_requests": len(path_measured), "all_requests": len(all_path),
                         "nearest_rank": math.ceil(.95 * len(times)),
                         "p95_ms": times[math.ceil(.95 * len(times)) - 1],
                         "errors": sum(row["http_status"] != 200 or row["error"] is not None for row in all_path),
                         "wrong_results": sum(not row["correct"] for row in all_path)}
    return {
        "result": "PASS" if len(measured) == 200 and not wrong and ordered[rank - 1] <= 1000 else "FAIL",
        "rooms": 10, "bookings": 1000, "seed": SEED, "fixed_now": BASE_LOCAL.isoformat(),
        "active_records": sum(not r["cancelled"] for r in fixture["bookings"]),
        "cancelled_records": sum(r["cancelled"] for r in fixture["bookings"]),
        "historical_records": sum(r["end"] <= BASE for r in fixture["bookings"]),
        "future_records": sum(r["start"] > BASE for r in fixture["bookings"]),
        "authenticated_clients": 10, "concurrent_batch_size": 10, "warmup_requests": 20, "measured_requests": len(measured),
        "errors": errors, "wrong_results": wrong, "error_rate": errors / len(samples),
        "all_220_responses_match_exact_fixture_dto": wrong == 0,
        "strict_json_types_checked": True, "by_query_path": by_path,
        "load_scope": "Registered 30-minute queries within the current seven-day window: 80% SQL availability, 20% attendees=1001 fast path; not a 4-hour/long-block worst-case benchmark",
        "p95_ms": ordered[rank - 1], "nearest_rank": rank, "nearest_rank_formula": "ceil(0.95 * 200) = 190; sorted_ms[189]",
        "min_ms": ordered[0], "max_ms": ordered[-1], "threshold_ms": 1000,
        "sorted_measured_ms": ordered, "samples_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "measurement": "Client perf_counter before HTTP send through complete response read and JSON parse; login excluded",
    }


def source_fingerprints():
    paths = sorted(path for path in (ROOT / "booking_app").rglob("*")
                   if path.is_file() and path.suffix in (".py", ".sql", ".html", ".css", ".js"))
    files = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"app_source_files_sha256": files, "app_source_sha256": digest,
            "performance_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def environment(server, run):
    def sysctl(key):
        try:
            return subprocess.check_output(["sysctl", "-n", key], text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return dict(**run, os=platform.platform(), machine=platform.machine(), cpu=sysctl("machdep.cpu.brand_string") or platform.processor(),
                logical_cpus=os.cpu_count(), memory_bytes=sysctl("hw.memsize"), python=sys.version, sqlite=sqlite3.sqlite_version,
                dependencies={name: importlib.metadata.version(name) for name in ("Flask", "Jinja2", "Werkzeug", "waitress")},
                server_processes=1, server_threads=8, origin=server.origin,
                invocation=[sys.executable, "-m", "scripts.verify_availability_performance", "--output-dir", "<chosen-output>"],
                server_start="spawn scripts.verify_availability_performance.server_main(database, port); waitress.serve(app, host='127.0.0.1', port=port, threads=8)",
                fixed_clock_injection="TESTING=True only, no HTTP clock endpoint", database="isolated temporary local file; WAL/FULL/foreign_keys; removed after run")


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_measurement(output_dir, run):
    with tempfile.TemporaryDirectory(prefix="grb-performance-") as temporary:
        database = Path(temporary) / "booking.sqlite3"
        users = [dict(username=f"perf_synthetic_{i:02}", display_name=f"性能演示账号 {i:02}",
                      role="admin" if i == 9 else "member", password=secrets.token_urlsafe(24)) for i in range(10)]
        seed_users(database, users, FixedClock())
        with db.read_transaction(database) as conn:
            user_ids = [row[0] for row in conn.execute("SELECT id FROM users ORDER BY id")]
        fixture = seed_fixture(database, user_ids)
        fixture["run_id"] = run["run_id"]
        write_json(output_dir / "performance-fixture.json", fixture)
        integrity = verify_fixture(database, fixture)
        server = Server(database)
        try:
            server.start()
            env = environment(server, run)
            env["invocation"] = [sys.executable, "-m", "scripts.verify_availability_performance", "--output-dir", str(output_dir.resolve())]
            write_json(output_dir / "performance-environment.json", env)
            clients = [Client(server.origin) for _ in users]
            for client, user in zip(clients, users):
                client.login(user)
            report = measure(clients, fixture, output_dir, run["run_id"])
            report["fixture_integrity_before"] = integrity
            report["fixture_integrity_after"] = verify_fixture(database, fixture)
            return report
        finally:
            server.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/availability-performance")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run = {"run_id": secrets.token_hex(16), "started_at_utc": datetime.now(timezone.utc).isoformat()}
    result_path = args.output_dir / "performance-result.json"
    # Invalidate an older PASS before seeding, starting a server, or any other fallible work.
    write_json(result_path, {**run, "result": "INCOMPLETE", "completed": False})
    try:
        write_json(args.output_dir / "performance-environment.json", {**run, "result": "INCOMPLETE"})
        run.update(source_fingerprints())
        write_json(args.output_dir / "performance-environment.json", {**run, "result": "INCOMPLETE"})
        report = run_measurement(args.output_dir, run)
        report.update(run, completed=True, finished_at_utc=datetime.now(timezone.utc).isoformat())
        write_json(result_path, report)  # PASS is published only after measurement, integrity, and cleanup.
    except BaseException as error:
        write_json(result_path, {**run, "result": "INCOMPLETE", "completed": False,
                                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                                "error_type": type(error).__name__})
        print(json.dumps({"result": "INCOMPLETE", "run_id": run["run_id"], "error_type": type(error).__name__}))
        return 1
    print(json.dumps({k: report[k] for k in ("result", "run_id", "warmup_requests", "measured_requests", "errors", "wrong_results", "p95_ms")}, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

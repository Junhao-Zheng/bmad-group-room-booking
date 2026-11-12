"""Repeatable real-Waitress smoke test; generates private temporary synthetic credentials."""

import argparse
import http.cookiejar
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from booking_app import ROOT, auth, db
from scripts.init_demo import DEMO_IDENTITIES


def run(port=8000):
    origin = f"http://127.0.0.1:{port}"
    # Fail clearly if another process owns the requested port; never contact its app.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    with tempfile.TemporaryDirectory(prefix="grb-auth-http-") as directory:
        path = Path(directory)
        database = path / "booking.sqlite3"
        password = secrets.token_urlsafe(24)
        credentials = path / "demo.credentials.json"
        credentials.touch(mode=0o600)
        credentials.write_text(json.dumps({"users": [
            {"username": name, "display_name": display, "role": role, "password": password}
            for name, display, role in DEMO_IDENTITIES
        ]}), encoding="utf-8")
        env = dict(os.environ, BOOKING_DB_PATH=str(database), APP_ORIGIN=origin,
                   COOKIE_SECURE="false", TRUSTED_HOSTS="127.0.0.1")
        for expected in (3, 0):
            result = subprocess.run([sys.executable, "-m", "scripts.init_demo", "--credentials-file", str(credentials)],
                                    env=env, cwd=ROOT, text=True, capture_output=True, check=True)
            assert f"新增 {expected} 个账号" in result.stdout
        command = [str(Path(sys.executable).parent / "waitress-serve"),
                   f"--listen=127.0.0.1:{port}", "--threads=8", "--call", "booking_app:create_app"]
        log_path = path / "waitress.log"
        with log_path.open("w+", encoding="utf-8") as logfile:
            server = subprocess.Popen(command, cwd=ROOT, env=env, stdout=logfile, stderr=logfile)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Waitress 启动失败。")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=.1):
                            break
                    except OSError:
                        time.sleep(.05)
                else:
                    raise RuntimeError("Waitress 启动超时。")
                samples = []
                def client():
                    jar = http.cookiejar.CookieJar()
                    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar
                def request(opener, route, body=None, csrf=None, cookie=None, origin_header=origin):
                    headers = {}
                    if body is not None:
                        headers.update({"Content-Type": "application/json"})
                        if origin_header is not None:
                            headers["Origin"] = origin_header
                        if csrf is not None:
                            headers["X-CSRF-Token"] = csrf
                    if cookie:
                        headers["Cookie"] = f"{auth.COOKIE_NAME}={cookie}"
                    req = urllib.request.Request(origin + route, headers=headers,
                                                 data=json.dumps(body).encode() if body is not None else None)
                    try:
                        response = opener.open(req, timeout=5)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        content = response.read().decode()
                        samples.append({"method": req.get_method(), "path": route, "status": response.status})
                        return response.status, content, response.headers
                clients = [client(), client()]
                sessions = []
                for opener, jar in clients:
                    status, html, _ = request(opener, "/login")
                    assert status == 200
                    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
                    status, _, headers = request(opener, "/api/login", {"username": "demo_member_a", "password": password}, csrf, origin_header=None)
                    assert status == 403 and "Set-Cookie" not in headers
                    status, content, headers = request(opener, "/api/login", {"username": "demo_member_a", "password": password}, csrf)
                    assert status == 200 and "HttpOnly" in headers["Set-Cookie"]
                    data = json.loads(content)["data"]
                    raw = next(c.value for c in jar if c.name == auth.COOKIE_NAME)
                    sessions.append((data["csrf_token"], raw))
                    assert set(data) == {"id", "display_name", "role", "csrf_token"}
                    assert password not in content and raw not in content
                    assert request(opener, "/api/me")[0] == 200
                    assert request(opener, "/")[0] == 200
                assert request(clients[0][0], "/api/logout", {}, sessions[0][0])[0] == 200
                status, content, headers = request(urllib.request.build_opener(), "/api/me", cookie=sessions[0][1])
                assert status == 401 and json.loads(content)["error"]["code"] == "AUTH_REQUIRED"
                assert "Set-Cookie" not in headers
                assert request(clients[1][0], "/api/me")[0] == 200
                conn = db.connect(database)
                try:
                    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 3
                    assert conn.execute("SELECT count(*) FROM sessions WHERE user_id IS NOT NULL").fetchone()[0] == 1
                finally:
                    conn.close()
            finally:
                server.terminate()
                server.wait(timeout=10)
            logfile.seek(0)
            log = logfile.read()
            assert password not in log
            for csrf, raw in sessions:
                assert csrf not in log and raw not in log and auth.token_digest(raw) not in log
        print(json.dumps({
            "result": "PASS", "initialization_added_counts": [3, 0], "requests": samples,
            "http_isolation": {"parent": {key: os.environ.get(key) for key in ("COOKIE_SECURE", "TRUSTED_HOSTS")},
                               "child": {key: env[key] for key in ("COOKIE_SECURE", "TRUSTED_HOSTS", "APP_ORIGIN")}},
            "final_users": 3, "final_authenticated_sessions": 1, "credential_log_check": "PASS",
            "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                        "platform": platform.platform(), "machine": platform.machine(),
                        "logical_cpu_count": os.cpu_count(),
                        "dependencies": {p: importlib.metadata.version(p) for p in ("Flask", "Jinja2", "Werkzeug", "waitress")}},
            "server": {"processes": 1, "threads": 8, "command": " ".join(command)},
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    run(parser.parse_args().port)

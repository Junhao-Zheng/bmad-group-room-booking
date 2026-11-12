"""Application factory for the single-process local course prototype."""

import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask
from werkzeug.security import generate_password_hash

from . import db
from .domain import SystemClock
from .audit import audit_writer

ROOT = Path(__file__).resolve().parent.parent


def default_database() -> str:
    return str(Path(os.environ.get("BOOKING_DB_PATH", ROOT / "instance/booking.sqlite3")).resolve())


def check_runtime() -> None:
    if sqlite3.sqlite_version_info < (3, 51, 3):
        raise RuntimeError("需要 SQLite ≥3.51.3；请使用记录的 Python 3.12.14 / SQLite 3.53.1 基线。")
    try:
        ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError("缺少 Asia/Shanghai 时区，请安装系统 IANA 时区数据。") from exc


def canonical_origin(value: str) -> str:
    """Validate configured ports and match the browser's default-port serialization."""
    try:
        if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError
        origin = urlsplit(value)
        port = origin.port  # Raises for nonnumeric and out-of-range ports.
        if (not origin.hostname or origin.path or origin.query or origin.fragment
                or origin.username is not None or origin.password is not None
                or origin.scheme not in ("http", "https") or origin.netloc.endswith(":")
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError
        host = origin.hostname.encode("idna").decode("ascii")
        if ":" in host:
            host = f"[{host}]"
        suffix = "" if port is None or (origin.scheme, port) in (("http", 80), ("https", 443)) else f":{port}"
        return f"{origin.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("APP_ORIGIN 必须是有效的 scheme://host[:port]；端口须为 1—65535，不含路径。") from error


def create_app(test_config=None) -> Flask:
    app = Flask(__name__, instance_path=str(ROOT / "instance"))
    app.config.from_mapping(
        DATABASE=default_database(),
        CLOCK=SystemClock(),
        AUDIT_WRITER=audit_writer,
        APP_ORIGIN=os.environ.get("APP_ORIGIN", "http://127.0.0.1:8000"),
        TRUSTED_HOSTS=os.environ.get("TRUSTED_HOSTS", "127.0.0.1,localhost").split(","),
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=16 * 1024,
        DEBUG=False,
    )
    if test_config:
        if not test_config.get("TESTING", False) and {"CLOCK", "AUDIT_WRITER"} & test_config.keys():
            raise RuntimeError("替代 Clock / audit writer 仅允许在 TESTING=True 时注入。")
        app.config.update(test_config)
    app.config["APP_ORIGIN"] = canonical_origin(app.config["APP_ORIGIN"])
    origin = urlsplit(app.config["APP_ORIGIN"])
    if origin.scheme == "http" and origin.hostname != "127.0.0.1":
        raise RuntimeError("HTTP 演示仅支持 127.0.0.1；其他部署必须使用 HTTPS。")
    if origin.scheme == "https" and not app.config["SESSION_COOKIE_SECURE"]:
        raise RuntimeError("HTTPS 部署必须配置 COOKIE_SECURE=true。")
    check_runtime()
    db.check_database(app.config["DATABASE"])
    app.extensions["dummy_password_hash"] = generate_password_hash(
        secrets.token_urlsafe(32), method="scrypt:32768:8:1"
    )
    app.teardown_appcontext(db.close_db)
    from .web import bp, install_handlers
    app.register_blueprint(bp)
    install_handlers(app)
    return app

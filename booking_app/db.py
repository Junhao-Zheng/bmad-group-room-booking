"""Explicit SQLite connections and short transactions; never writes audit events."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from flask import current_app, g

SCHEMA_VERSION = 1
REQUIRED_COLUMNS = {
    "users": {"id", "username", "display_name", "password_hash", "role", "created_at"},
    "sessions": {"token_hash", "user_id", "csrf_token", "created_at", "expires_at"},
    "rooms": {"id", "name", "location", "capacity", "created_at", "updated_at"},
    "reservations": {"id", "kind", "room_id", "user_id", "title", "purpose", "attendees",
                     "reason", "start_at", "end_at", "intent_key", "request_payload", "created_at",
                     "cancelled_at", "cancelled_by", "cancel_reason"},
    "occupancy_slots": {"room_id", "slot_start", "reservation_id"},
}


def connect(database: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(database), isolation_level=None, timeout=15,
        autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("无法启用 SQLite 外键约束。")
        return conn
    except BaseException:
        conn.close()
        raise


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def read_transaction(database: str | Path | None = None):
    """One consistent, read-only snapshot, closed before DTOs reach the renderer."""
    conn = connect(database or current_app.config["DATABASE"])
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def write_transaction(database: str | Path | None = None):
    conn = connect(database or current_app.config["DATABASE"])
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def initialize_database(database: str | Path) -> None:
    path = Path(database).resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Restrict a newly created DB before SQLite opens WAL/SHM sidecars.
    if not path.exists():
        path.touch(mode=0o600, exist_ok=False)
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError("数据库版本不兼容；请勿覆盖现有数据。")
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if version == 0 and tables:
            raise RuntimeError("发现未识别的数据表；请使用空数据库或已初始化的数据库。")
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            if conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("无法启用 SQLite WAL；请使用本地磁盘。")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        # executescript controls its own transaction, including on first initialization.
        conn.executescript("BEGIN IMMEDIATE;\n" + schema + f"\nPRAGMA user_version={SCHEMA_VERSION};\nCOMMIT;")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    check_database(path)


def check_database(database: str | Path) -> None:
    path = Path(database)
    if not path.is_file():
        raise RuntimeError("数据库未初始化。请先运行 uv run python -m scripts.init_demo。")
    conn = connect(path)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise RuntimeError("数据库 schema 版本不兼容；启动已停止，不会自动迁移。")
        for table, required in REQUIRED_COLUMNS.items():
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not required.issubset(columns):
                raise RuntimeError("数据库 schema 不完整；请核对初始化与应用版本。")
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise RuntimeError("数据库必须使用 WAL 模式，请重新运行初始化命令。")
    finally:
        conn.close()

"""Explicit SQLite connections and short transactions; never writes audit events."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import re

from flask import current_app, g

SCHEMA_VERSION = 3
REQUIRED_COLUMNS = {
    "applications": {"id", "owner_id", "owner_display_name", "supervisor_id", "supervisor_display_name", "room_id", "title", "purpose", "attendees", "start_at", "end_at", "weeks", "intent_key", "request_payload", "status", "created_at", "decided_at", "decided_by", "decision_reason"},
    "application_occurrences": {"application_id", "occurrence", "reservation_id"},
    "booking_supervisors": {"reservation_id", "supervisor_id", "supervisor_display_name", "source"},
    "users": {"id", "username", "display_name", "password_hash", "role", "created_at", "supervisor_id"},
    "sessions": {"token_hash", "user_id", "csrf_token", "created_at", "expires_at"},
    "rooms": {"id", "name", "location", "capacity", "created_at", "updated_at"},
    "reservations": {"id", "kind", "room_id", "user_id", "title", "purpose", "attendees",
                     "reason", "start_at", "end_at", "intent_key", "request_payload", "created_at",
                     "cancelled_at", "cancelled_by", "cancel_reason"},
    "occupancy_slots": {"room_id", "slot_start", "reservation_id"},
    "audit_events": {"id", "actor_id", "actor_display_name", "action", "target_type", "target_id",
                     "occurred_at", "before_json", "after_json", "reason"},
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


def check_identity_schema(conn) -> None:
    """Reject missing, altered, or misattached identity guards, including collisions."""
    expected_names = {"users_supervisor_insert", "users_supervisor_update", "users_teacher_role_update"}
    statement = ""
    for line in Path(__file__).with_name("schema.sql").read_text(encoding="utf-8").splitlines(keepends=True):
        statement += line
        if not sqlite3.complete_statement(statement):
            continue
        sql = statement.strip().removesuffix(";")
        statement = ""
        prefix = "CREATE TRIGGER IF NOT EXISTS "
        if not sql.startswith(prefix):
            continue
        name = sql[len(prefix):].split()[0]
        if name not in expected_names:
            continue
        row = conn.execute("SELECT tbl_name,sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
        expected = sql.replace(prefix, "CREATE TRIGGER ", 1)
        if row is None or row[0] != "users" or row[1] != expected:
            raise RuntimeError("数据库身份约束不兼容；导师触发器缺失或已修改。")
        expected_names.remove(name)
    if expected_names:
        raise RuntimeError("应用 schema 缺少导师身份约束定义。")
    if conn.execute("SELECT 1 FROM users s LEFT JOIN users t ON t.id=s.supervisor_id "
                    "WHERE s.supervisor_id IS NOT NULL AND "
                    "(s.role!='member' OR t.role IS NULL OR t.role!='teacher' OR s.id=t.id) LIMIT 1").fetchone():
        raise RuntimeError("数据库存在无效导师归属；启动已停止。")


def schema_sql_tokens(sql):
    """Compare known definitions without treating spaces inside SQL literals as formatting."""
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[^\s]", sql)
    return tuple(token if token.startswith("'") else token.strip('"').lower()
                 for token in tokens if token != ';')


def check_critical_schema(conn):
    """Column names alone cannot prove CHECK, FK, primary-key or unique guarantees."""
    reference = sqlite3.connect(":memory:")
    try:
        reference.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        for name in ("users", "applications", "application_occurrences", "booking_supervisors", "audit_events", "occupancy_slots"):
            expected = reference.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0]
            actual = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            if actual is None or schema_sql_tokens(actual[0]) != schema_sql_tokens(expected):
                raise RuntimeError("数据库关键表约束不兼容；启动已停止。")
            def unique_indexes(connection):
                return sorted((row[2], row[3], row[4], tuple(tuple(part)[1:] for part in connection.execute(
                    'PRAGMA index_xinfo("' + row[1].replace('"', '""') + '")')))
                    for row in connection.execute(f"PRAGMA index_list({name})") if row[2])
            if unique_indexes(conn) != unique_indexes(reference):
                raise RuntimeError("数据库唯一约束不兼容；启动已停止。")
        for name in ("reservations_user_intent", "applications_supervisor", "audit_events_target_time"):
            expected = reference.execute("SELECT tbl_name,sql FROM sqlite_master WHERE type='index' AND name=?", (name,)).fetchone()
            actual = conn.execute("SELECT tbl_name,sql FROM sqlite_master WHERE type='index' AND name=?", (name,)).fetchone()
            if actual is None or actual[0] != expected[0] or schema_sql_tokens(actual[1]) != schema_sql_tokens(expected[1]):
                raise RuntimeError("数据库关键索引不兼容；启动已停止。")
    finally:
        reference.close()


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
        check_identity_schema(conn)
        check_critical_schema(conn)
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            raise RuntimeError("数据库必须使用 WAL 模式，请重新运行初始化命令。")
    finally:
        conn.close()

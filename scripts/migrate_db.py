"""Explicit, backed-up schema 1/2/3/4 to 5 migration; run with the application stopped."""
import argparse
import json
from pathlib import Path
import sqlite3

from booking_app import db
from scripts.backup_db import backup_database, validate_backup_paths


def _validate_v1(conn):
    if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise ValueError("Migration requires schema version 1")
    baseline = {
        "users": {"id","username","display_name","password_hash","role","created_at"},
        "sessions": {"token_hash","user_id","csrf_token","created_at","expires_at"},
        "rooms": {"id","name","location","capacity","created_at","updated_at"},
        "reservations": {"id","kind","room_id","user_id","title","purpose","attendees","reason","start_at","end_at","intent_key","request_payload","created_at","cancelled_at","cancelled_by","cancel_reason"},
        "occupancy_slots": {"room_id","slot_start","reservation_id"},
        "audit_events": {"id","actor_id","actor_display_name","action","target_type","target_id","occurred_at","before_json","after_json","reason"},
    }
    for table, expected in baseline.items():
        actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if actual != expected:
            raise ValueError("Unrecognized schema 1 columns")
    # Rebuilding an altered users table could silently discard local constraints.
    original_users = ("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE "
                      "CHECK (length(trim(username)) > 0), display_name TEXT NOT NULL "
                      "CHECK (length(trim(display_name)) > 0), password_hash TEXT NOT NULL, "
                      "role TEXT NOT NULL CHECK (role IN ('member', 'admin')), created_at INTEGER NOT NULL)")
    actual = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
    compact = lambda text: ''.join(text.replace('IF NOT EXISTS', '').split()).rstrip(';')
    if compact(actual) != compact(original_users):
        raise ValueError("Unrecognized schema 1 users definition")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE tbl_name='users' AND type IN ('trigger','index') AND sql IS NOT NULL").fetchone():
        raise ValueError("Custom users objects require a separate migration")
    _check_integrity(conn)


# Frozen schema 1/2 audit definitions; rebuilding any local variation requires a separate migration.
_LEGACY_AUDIT_SQL = "CREATE TABLE audit_events (\n    id INTEGER PRIMARY KEY,\n    actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,\n    actor_display_name TEXT NOT NULL CHECK (length(trim(actor_display_name)) > 0),\n    action TEXT NOT NULL CHECK (action IN ('room.created','room.updated','booking.created',\n        'booking.cancelled_by_member','booking.cancelled_by_admin','block.created','block.revoked')),\n    target_type TEXT NOT NULL CHECK (target_type IN ('room','booking','block')),\n    target_id INTEGER NOT NULL CHECK (typeof(target_id) = 'integer' AND target_id > 0),\n    occurred_at INTEGER NOT NULL CHECK (typeof(occurred_at) = 'integer'),\n    before_json TEXT CHECK (before_json IS NULL OR (json_valid(before_json) AND json_type(before_json) = 'object')),\n    after_json TEXT NOT NULL CHECK (json_valid(after_json) AND json_type(after_json) = 'object' AND after_json != '{}'),\n    reason TEXT CHECK (reason IS NULL OR length(trim(reason)) BETWEEN 1 AND 500)\n);"
_LEGACY_AUDIT_INDEX_SQL = 'CREATE INDEX audit_events_target_time ON audit_events(target_type, occurred_at, id);'
_V3_AUDIT_SQL = """CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    actor_display_name TEXT NOT NULL CHECK (length(trim(actor_display_name)) > 0),
    action TEXT NOT NULL CHECK (action IN ('room.created','room.updated','booking.created',
        'booking.cancelled_by_member','booking.cancelled_by_admin','block.created','block.revoked',
        'application.created','application.approved','application.rejected','application.withdrawn')),
    target_type TEXT NOT NULL CHECK (target_type IN ('room','booking','block','application')),
    target_id INTEGER NOT NULL CHECK (typeof(target_id) = 'integer' AND target_id > 0),
    occurred_at INTEGER NOT NULL CHECK (typeof(occurred_at) = 'integer'),
    before_json TEXT CHECK (before_json IS NULL OR (json_valid(before_json) AND json_type(before_json) = 'object')),
    after_json TEXT NOT NULL CHECK (json_valid(after_json) AND json_type(after_json) = 'object' AND after_json != '{}'),
    reason TEXT CHECK (reason IS NULL OR length(trim(reason)) BETWEEN 1 AND 500)
);"""


def _validate_legacy_audit(conn, version):
    actual = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='audit_events'").fetchone()
    if actual is None or db.schema_sql_tokens(actual[0]) != db.schema_sql_tokens(_V3_AUDIT_SQL if version == 3 else _LEGACY_AUDIT_SQL):
        raise ValueError("Unrecognized legacy audit definition")
    objects = list(conn.execute("SELECT type,name,sql FROM sqlite_master WHERE tbl_name='audit_events' AND type IN ('trigger','index')"))
    if (len(objects) != 1 or objects[0][0] != 'index' or objects[0][1] != 'audit_events_target_time'
            or db.schema_sql_tokens(objects[0][2]) != db.schema_sql_tokens(_LEGACY_AUDIT_INDEX_SQL)):
        raise ValueError("Custom or altered audit objects require a separate migration")


def _check_integrity(conn):
    if [r[0] for r in conn.execute("PRAGMA integrity_check")] != ["ok"] or list(conn.execute("PRAGMA foreign_key_check")):
        raise ValueError("Database integrity or foreign key check failed")


def migrate_database(source, backup):
    source, backup = validate_backup_paths(source, backup)
    conn = db.connect(source)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, 2, 3, 4):
            raise ValueError("Migration requires schema version 1, 2, 3 or 4")
        # Restored backup files may use DELETE journaling. Establish WAL before
        # changing schema so journal-mode failure cannot follow a committed upgrade.
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            if conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("Migration requires local WAL storage")
        # SQLite requires this before BEGIN when rebuilding a referenced table.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        if version == 1:
            _validate_v1(conn)
        elif version == 2:
            for table in ("users","sessions","rooms","reservations","occupancy_slots","audit_events"):
                if {r[1] for r in conn.execute(f"PRAGMA table_info({table})")} != db.REQUIRED_COLUMNS[table]:
                    raise ValueError("Unrecognized schema 2 columns")
            db.check_identity_schema(conn)
            _check_integrity(conn)
        else:
            for table, expected in db.REQUIRED_COLUMNS.items():
                if table == "cancellation_requests" and version == 3:
                    continue
                if {r[1] for r in conn.execute(f"PRAGMA table_info({table})")} != expected:
                    raise ValueError("Unrecognized schema 3/4 columns")
            db.check_identity_schema(conn)
            _check_integrity(conn)
            if version == 4:
                old_schema = Path(db.__file__).with_name("schema.sql").read_text(encoding="utf-8")
                old_schema = old_schema.replace("CHECK(typeof(weeks)='integer' AND weeks BETWEEN 1 AND 8)", "CHECK(weeks=1)")
                old_schema = old_schema.replace("CHECK(occurrence BETWEEN 1 AND 8)", "CHECK(occurrence=1)")
                db.check_critical_schema(conn, old_schema)
        if version < 4:
            _validate_legacy_audit(conn, version)
        destinations = ['users_v3', 'audit_events_v3', 'applications_old', 'application_occurrences_old']
        if version < 4:
            destinations.append('cancellation_requests')
        if version < 3:
            destinations += ['applications','application_occurrences','booking_supervisors']
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name IN (" + ','.join('?' for _ in destinations) + ")",destinations).fetchone():
            raise ValueError("Migration destination tables already exist")
        # A separate read-only backup connection sees committed WAL while this
        # writer lock prevents changes between the backup and the migration.
        saved = backup_database(source, backup)
        schema = Path(db.__file__).with_name("schema.sql").read_text(encoding="utf-8")
        statements, statement = [], ""
        for line in schema.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                statements.append(statement.strip())
                statement = ""
        if version == 1:
            conn.execute(statements[0].replace("IF NOT EXISTS users", "users_v3", 1))
            conn.execute("INSERT INTO users_v3(id,username,display_name,password_hash,role,created_at) "
                         "SELECT id,username,display_name,password_hash,role,created_at FROM users")
            conn.execute("DROP TABLE users")
            conn.execute("ALTER TABLE users_v3 RENAME TO users")
        if version < 4:
            audit_sql = next(sql for sql in statements if sql.startswith("CREATE TABLE IF NOT EXISTS audit_events"))
            conn.execute(audit_sql.replace("IF NOT EXISTS audit_events", "audit_events_v3", 1))
            conn.execute("INSERT INTO audit_events_v3 SELECT * FROM audit_events")
            conn.execute("DROP TABLE audit_events")
            conn.execute("ALTER TABLE audit_events_v3 RENAME TO audit_events")
        if version >= 3:
            conn.execute("ALTER TABLE application_occurrences RENAME TO application_occurrences_old")
            conn.execute("ALTER TABLE applications RENAME TO applications_old")
        for sql in statements:
            conn.execute(sql)
        if version >= 3:
            conn.execute("INSERT INTO applications SELECT * FROM applications_old")
            conn.execute("INSERT INTO application_occurrences SELECT * FROM application_occurrences_old")
            conn.execute("DROP TABLE application_occurrences_old")
            conn.execute("DROP TABLE applications_old")
            conn.execute(next(sql for sql in statements if sql.startswith("CREATE INDEX IF NOT EXISTS applications_supervisor")))
        conn.execute(f"PRAGMA user_version={db.SCHEMA_VERSION}")
        db.check_identity_schema(conn)
        db.check_critical_schema(conn)
        _check_integrity(conn)
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys=ON")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    db.check_database(source)
    return {"database": str(source), "schema_version": db.SCHEMA_VERSION,
            "backup": saved, "integrity_check": ["ok"], "foreign_key_check": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Explicit path to a stopped schema 1, 2, 3 or 4 database")
    parser.add_argument("--backup", required=True, type=Path, help="New independent backup file; never overwritten")
    args = parser.parse_args(argv)
    try:
        result = migrate_database(args.source, args.backup)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(1, f"Migration failed ({type(error).__name__}); check schema 1/2/3/4, integrity and a new independent backup path. No credentials are reported.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

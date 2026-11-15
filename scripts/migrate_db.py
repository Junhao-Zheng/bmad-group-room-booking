"""Explicit, backed-up schema 1 → 2 migration; run with the application stopped."""
import argparse
import json
from pathlib import Path
import sqlite3

from booking_app import db
from scripts.backup_db import backup_database, validate_backup_paths


def _validate_v1(conn):
    if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise ValueError("Migration requires schema version 1")
    for table, required in db.REQUIRED_COLUMNS.items():
        expected = required - {"supervisor_id"} if table == "users" else required
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


def _check_integrity(conn):
    if [r[0] for r in conn.execute("PRAGMA integrity_check")] != ["ok"] or list(conn.execute("PRAGMA foreign_key_check")):
        raise ValueError("Database integrity or foreign key check failed")


def migrate_database(source, backup):
    source, backup = validate_backup_paths(source, backup)
    conn = db.connect(source)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Migration requires schema version 1")
        # Restored backup files may use DELETE journaling. Establish WAL before
        # changing schema so journal-mode failure cannot follow a committed upgrade.
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
            if conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                raise RuntimeError("Migration requires local WAL storage")
        # SQLite requires this before BEGIN when rebuilding a referenced table.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN IMMEDIATE")
        _validate_v1(conn)
        # A separate read-only backup connection sees committed WAL while this
        # writer lock prevents changes between the backup and the migration.
        saved = backup_database(source, backup)
        schema = Path(db.__file__).with_name("schema.sql").read_text(encoding="utf-8")
        users_sql, remainder = schema.split(";", 1)
        conn.execute(users_sql.replace("IF NOT EXISTS users", "users_v2", 1))
        conn.execute("INSERT INTO users_v2(id,username,display_name,password_hash,role,created_at) "
                     "SELECT id,username,display_name,password_hash,role,created_at FROM users")
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_v2 RENAME TO users")
        # Execute trigger statements individually: executescript would commit early.
        statement = ""
        for line in remainder.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                conn.execute(statement)
                statement = ""
        conn.execute(f"PRAGMA user_version={db.SCHEMA_VERSION}")
        db.check_identity_schema(conn)
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
    parser.add_argument("--source", required=True, type=Path, help="Explicit path to a stopped schema 1 database")
    parser.add_argument("--backup", required=True, type=Path, help="New independent backup file; never overwritten")
    args = parser.parse_args(argv)
    try:
        result = migrate_database(args.source, args.backup)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        parser.exit(1, f"Migration failed ({type(error).__name__}); check schema 1, integrity and a new independent backup path. No credentials are reported.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

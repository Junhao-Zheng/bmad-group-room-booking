"""Explicit schema 1 fixtures for regression tests of retained historical facts.

These old accounts intentionally have no inferred supervisor after migration.
Production initialization must use scripts.init_demo with explicit supervisors.
"""
from pathlib import Path
from werkzeug.security import generate_password_hash
from booking_app import db
from booking_app.domain import SystemClock
from scripts.migrate_db import migrate_database

DEMO_IDENTITIES = (
    ("demo_member_a", "演示成员甲", "member"),
    ("demo_member_b", "演示成员乙", "member"),
    ("demo_admin", "演示管理员", "admin"),
)


def seed_users(database, users, clock=None):
    path = Path(database)
    if path.exists():
        raise ValueError("Legacy fixtures require a new database")
    path.parent.mkdir(parents=True, exist_ok=True)
    hashes = [(u['username'], u['display_name'], generate_password_hash(u['password'], method='scrypt:32768:8:1'),
               u['role'], (clock or SystemClock()).now_epoch()) for u in users]
    conn = db.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(Path(__file__).with_name('fixtures').joinpath('schema_v1.sql').read_text())
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES (?,?,?,?,?)", hashes)
        conn.execute("PRAGMA user_version=1")
        conn.execute("COMMIT")
    finally:
        conn.close()
    migrate_database(path, path.with_name(path.name + '.schema1-backup'))
    return len(users)

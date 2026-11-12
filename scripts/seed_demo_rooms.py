"""Add clearly synthetic demo rooms without replacing existing data."""

import argparse
from pathlib import Path

from booking_app import check_runtime, default_database
from booking_app.db import initialize_database, write_transaction
from booking_app.domain import Clock, SystemClock

DEMO_ROOMS = (
    ("合成演示 · 讨论室 A", "演示楼 201", 8),
    ("合成演示 · 讨论室 B", "演示楼 202", 16),
    ("合成演示 · 研讨室", "演示楼 301", 30),
)


def seed_rooms(database: str | Path, clock: Clock | None = None) -> int:
    initialize_database(database)
    added = 0
    with write_transaction(database) as conn:
        now = (clock or SystemClock()).now_epoch()
        for name, location, capacity in DEMO_ROOMS:
            if conn.execute("SELECT id FROM rooms WHERE name=? AND location=?", (name, location)).fetchone():
                continue
            conn.execute("INSERT INTO rooms(name,location,capacity,created_at,updated_at) VALUES (?,?,?,?,?)",
                         (name, location, capacity, now, now))
            added += 1
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(default_database()))
    args = parser.parse_args()
    check_runtime()
    added = seed_rooms(args.database)
    print(f"合成演示会议室初始化完成，新增 {added} 间；已有数据未覆盖。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

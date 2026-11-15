"""Idempotently initialize synthetic accounts; passwords only via getpass/private file."""

import argparse
import getpass
import json
from pathlib import Path
import stat
import sqlite3
import sys
import warnings

from werkzeug.security import generate_password_hash

from booking_app import check_runtime, default_database
from booking_app import db
from booking_app.domain import DomainError, SystemClock, validate_credentials

DEMO_IDENTITIES = (
    ("demo_member_a", "演示成员甲", "member"),
    ("demo_member_b", "演示成员乙", "member"),
    ("demo_admin", "演示管理员", "admin"),
    ("demo_teacher_a", "演示导师甲", "teacher"),
    ("demo_teacher_b", "演示导师乙", "teacher"),
)


DEMO_SUPERVISORS = {"demo_member_a": "demo_teacher_a", "demo_member_b": "demo_teacher_b"}


def seed_users(database, users, clock=None):
    if not isinstance(users, list):
        raise ValueError("账号配置必须是列表。")
    normalized = []
    seen = set()
    for user in users:
        if not isinstance(user, dict):
            raise ValueError("每个账号配置必须是对象。")
        username, display, password, role = (user.get(k) for k in ("username", "display_name", "password", "role"))
        username, password = validate_credentials(username, password)
        if (not isinstance(display, str) or not display.strip()
                or len(password) < 12
                or role not in ("member", "teacher", "admin")):
            raise ValueError("账号/显示名不能为空，角色须 member/teacher/admin，口令至少 12 字符。")
        username, display = username.strip(), display.strip()
        try:
            display.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("显示名包含无效 Unicode 字符。") from error
        if username in seen:
            raise ValueError("配置中存在重复账号。")
        seen.add(username)
        supervisor = user.get("supervisor_username")
        if role == "member":
            if not isinstance(supervisor, str) or not supervisor.strip():
                raise ValueError("新学生配置必须指定导师账号。")
            supervisor, _ = validate_credentials(supervisor, password)
        elif supervisor is not None:
            raise ValueError("导师和管理员不可绑定导师。")
        normalized.append((username, display, password, role, supervisor))
    # Validation and hashing happen before taking the write lock.
    hashes = [(name, display, generate_password_hash(password, method="scrypt:32768:8:1"), role, supervisor)
              for name, display, password, role, supervisor in normalized]
    db.initialize_database(database)
    added = 0
    with db.write_transaction(database) as conn:
        now = (clock or SystemClock()).now_epoch()
        existing = {row["username"]: row for row in conn.execute("SELECT * FROM users")}
        roles = {name: row["role"] for name, row in existing.items()}
        roles.update({name: role for name, _, _, role, _ in hashes if name not in existing})
        for _, _, _, role, supervisor in hashes:
            if role == "member" and roles.get(supervisor) != "teacher":
                raise ValueError("学生归属必须指向有效导师。")
        # Teachers are persisted first even when supplied after their students.
        for name, display, hashed, role, supervisor in sorted(hashes, key=lambda u: u[3] != "teacher"):
            if name in existing:
                continue
            supervisor_id = (conn.execute("SELECT id FROM users WHERE username=? AND role='teacher'",
                                          (supervisor,)).fetchone()[0] if supervisor else None)
            conn.execute("INSERT INTO users(username,display_name,password_hash,role,created_at,supervisor_id) VALUES (?,?,?,?,?,?)",
                         (name, display, hashed, role, now, supervisor_id))
            added += 1
    return added


def main():
    parser = argparse.ArgumentParser(description="初始化合成演示账号；重复运行只添加缺失账号。")
    parser.add_argument("--credentials-file", type=Path, help="权限 600 的私有 JSON 文件，含 users 列表")
    args = parser.parse_args()
    try:
        check_runtime()
        if args.credentials_file:
            if stat.S_IMODE(args.credentials_file.stat().st_mode) & 0o077:
                raise ValueError("私有口令文件不可供其他用户读取；请先 chmod 600。")
            config = json.loads(args.credentials_file.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("私有配置顶层必须是包含 users 的对象。")
            users = config["users"]
        else:
            users = []
            for name, display, role in DEMO_IDENTITIES:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    password = getpass.getpass(f"{display}（{name}）的演示口令（至少12字符；已有账号不会覆盖）：")
                users.append({"username": name, "display_name": display, "role": role, "password": password,
                              "supervisor_username": DEMO_SUPERVISORS.get(name)})
        database = Path(default_database())
        empty = not database.exists()
        if not empty:
            with db.read_transaction(database) as conn:
                uninitialized = (conn.execute("PRAGMA user_version").fetchone()[0] == 0
                                 and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone() is None)
            if uninitialized:
                empty = True
            else:
                db.check_database(database)
                with db.read_transaction(database) as conn:
                    empty = conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        if empty:
            if not isinstance(users, list) or any(not isinstance(u, dict) for u in users):
                raise ValueError("账号配置必须为对象列表。")
            if any(sum(u.get("role") == role for u in users) < minimum
                   for role, minimum in (("teacher", 2), ("member", 2), ("admin", 1))):
                raise ValueError("空库演示须包含两名导师、两名学生和一名管理员。")
        count = seed_users(database, users)
        print(f"合成演示数据初始化完成：新增 {count} 个账号，已有账号与数据保持不变。")
    except (getpass.GetPassWarning, EOFError):
        print("无法使用隐藏口令输入。请在可用终端运行，或使用权限 600 的私有文件及 --credentials-file。", file=sys.stderr)
        return 1
    except (DomainError, ValueError, KeyError, OSError, RuntimeError, sqlite3.Error) as error:
        # Configuration values and passwords are never printed, including parse failures.
        print(f"初始化失败（{type(error).__name__}）：请检查运行环境、文件权限和账号配置。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

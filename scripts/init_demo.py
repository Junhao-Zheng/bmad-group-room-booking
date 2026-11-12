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
)


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
                or role not in ("member", "admin")):
            raise ValueError("账号/显示名不能为空，角色须 member/admin，口令至少 12 字符。")
        username, display = username.strip(), display.strip()
        try:
            display.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("显示名包含无效 Unicode 字符。") from error
        if username in seen:
            raise ValueError("配置中存在重复账号。")
        seen.add(username)
        normalized.append((username, display, password, role))
    if sum(u[3] == "member" for u in normalized) < 2 or sum(u[3] == "admin" for u in normalized) < 1:
        raise ValueError("演示配置必须包含至少两个成员和一个管理员。")
    # Validation and hashing happen before taking the write lock.
    hashes = [(name, display, generate_password_hash(password, method="scrypt:32768:8:1"), role)
              for name, display, password, role in normalized]
    db.initialize_database(database)
    added = 0
    with db.write_transaction(database) as conn:
        now = (clock or SystemClock()).now_epoch()
        for name, display, hashed, role in hashes:
            if conn.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
                continue
            conn.execute("INSERT INTO users(username,display_name,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                         (name, display, hashed, role, now))
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
                users.append({"username": name, "display_name": display, "role": role, "password": password})
        count = seed_users(default_database(), users)
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

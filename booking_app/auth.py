"""Server-side authentication services. Tokens never enter domain output or logs."""

from dataclasses import dataclass
import hashlib
import secrets

from flask import current_app
from werkzeug.security import check_password_hash

from . import db
from .domain import DomainError, auth_required, validate_credentials

COOKIE_NAME = "grb_session"
PREAUTH_SECONDS = 600
SESSION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class Actor:
    id: int
    display_name: str
    role: str
    session_token_hash: str


@dataclass(frozen=True)
class Grant:
    token: str
    csrf_token: str
    created_at: int
    expires_at: int
    user: dict | None = None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def read_session(conn, token_hash: str, now: int):
    return conn.execute(
        "SELECT s.token_hash, s.user_id, s.csrf_token, s.created_at, s.expires_at, "
        "u.display_name, u.role FROM sessions s LEFT JOIN users u ON u.id=s.user_id "
        "WHERE s.token_hash=? AND s.expires_at>?", (token_hash, now),
    ).fetchone()


def session_for_token(token: str | None):
    if not token:
        return None
    try:
        digest = token_digest(token)
    except UnicodeEncodeError:
        return None
    return read_session(db.get_db(), digest, current_app.config["CLOCK"].now_epoch())


def require_session(token: str | None, *, temporary=False):
    session = session_for_token(token)
    if session is None or (session["user_id"] is None) != temporary:
        raise auth_required()
    return session


def check_csrf(session, submitted: str | None) -> None:
    try:
        valid = isinstance(submitted, str) and secrets.compare_digest(
            session["csrf_token"].encode("utf-8"), submitted.encode("utf-8")
        )
    except UnicodeEncodeError:
        valid = False
    if not valid:
        raise DomainError("CSRF_REJECTED", "请求验证失败，请重新打开页面后重试。")


def current_user(session) -> dict:
    return {"id": session["user_id"], "display_name": session["display_name"],
            "role": session["role"], "csrf_token": session["csrf_token"]}


def actor_for_token(token: str | None) -> Actor:
    row = require_session(token)
    return Actor(row["user_id"], row["display_name"], row["role"], row["token_hash"])


def prepare_login(token: str | None):
    existing = session_for_token(token)
    if existing is not None:
        return existing, None
    raw_token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES (?,NULL,?,?,?)",
            (token_digest(raw_token), csrf, now, now + PREAUTH_SECONDS),
        )
        session = read_session(conn, token_digest(raw_token), now)
    return session, Grant(raw_token, csrf, now, now + PREAUTH_SECONDS)


def login(token: str | None, csrf: str | None, payload: dict) -> Grant:
    preauth = require_session(token, temporary=True)
    check_csrf(preauth, csrf)
    username, password = validate_credentials(payload.get("username"), payload.get("password"))
    user = db.get_db().execute(
        "SELECT id,password_hash FROM users WHERE username=?", (username,),
    ).fetchone()
    stored_hash = user["password_hash"] if user else current_app.extensions["dummy_password_hash"]
    # scrypt is deliberately outside BEGIN IMMEDIATE, including unknown usernames.
    valid = check_password_hash(stored_hash, password)
    if user is None or not valid:
        raise DomainError("INVALID_CREDENTIALS", "账号或密码错误")
    raw_token, new_csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        original = read_session(conn, preauth["token_hash"], now)
        if original is None or original["user_id"] is not None:
            raise auth_required()
        check_csrf(original, csrf)
        fresh_user = conn.execute(
            "SELECT id,display_name,role,password_hash FROM users WHERE id=?", (user["id"],),
        ).fetchone()
        if fresh_user is None or fresh_user["password_hash"] != stored_hash:
            raise auth_required()
        deleted = conn.execute("DELETE FROM sessions WHERE token_hash=?", (preauth["token_hash"],))
        if deleted.rowcount != 1:
            raise auth_required()
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_token,created_at,expires_at) VALUES (?,?,?,?,?)",
            (token_digest(raw_token), user["id"], new_csrf, now, now + SESSION_SECONDS),
        )
        result = {"id": fresh_user["id"], "display_name": fresh_user["display_name"],
                  "role": fresh_user["role"], "csrf_token": new_csrf}
    return Grant(raw_token, new_csrf, now, now + SESSION_SECONDS, result)


def logout(token: str | None, csrf: str | None) -> dict:
    original = require_session(token)
    check_csrf(original, csrf)
    with db.write_transaction() as conn:
        now = current_app.config["CLOCK"].now_epoch()
        session = read_session(conn, original["token_hash"], now)
        if session is None or session["user_id"] is None:
            raise auth_required()
        check_csrf(session, csrf)
        deleted = conn.execute("DELETE FROM sessions WHERE token_hash=?", (original["token_hash"],))
        if deleted.rowcount != 1:
            raise auth_required()
    return {"logged_out": True}

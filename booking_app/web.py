"""HTTP adapters: no SQL, no transaction ownership, one response envelope."""

import sqlite3
import uuid

from flask import Blueprint, current_app, g, jsonify, make_response, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from . import auth, services
from .domain import DomainError

bp = Blueprint("web", __name__)
STATUS = {"INVALID_INPUT": 400, "AUTH_REQUIRED": 401, "INVALID_CREDENTIALS": 401,
          "FORBIDDEN": 403, "CSRF_REJECTED": 403, "NOT_FOUND": 404,
          "OCCUPANCY_CONFLICT": 409, "CAPACITY_CONFLICT": 409, "IDEMPOTENCY_MISMATCH": 409,
          "TRANSITION_CLOSED": 409, "ROOM_DUPLICATE": 409,
          "STORE_BUSY": 503, "INTERNAL_ERROR": 500}


def token():
    return request.cookies.get(auth.COOKIE_NAME)


def csrf():
    if request.mimetype == "application/x-www-form-urlencoded":
        return request.form.get("csrf_token")
    return request.headers.get("X-CSRF-Token")


def payload():
    if request.mimetype == "application/json":
        data = request.get_json()
    elif request.mimetype == "application/x-www-form-urlencoded":
        data = request.form.to_dict()
    else:
        raise DomainError("INVALID_INPUT", "请使用 JSON 或表单格式提交。")
    if not isinstance(data, dict):
        raise DomainError("INVALID_INPUT", "请求内容必须是一个对象。")
    return data


def issue_cookie(response, grant):
    response.set_cookie(
        auth.COOKIE_NAME, grant.token, max_age=grant.expires_at - grant.created_at,
        httponly=True, secure=current_app.config["SESSION_COOKIE_SECURE"],
        samesite="Lax", path="/",
    )
    return response


@bp.get("/login")
def login_page():
    session, grant = auth.prepare_login(token())
    if session["user_id"] is not None:
        return redirect(url_for("web.home"))
    response = make_response(render_template("login.html", csrf_token=session["csrf_token"]))
    return issue_cookie(response, grant) if grant else response


@bp.get("/")
def home():
    session = auth.require_session(token())
    actor = auth.Actor(session["user_id"], session["display_name"], session["role"], session["token_hash"])
    return render_template("home.html", user=auth.current_user(session), rooms=services.list_rooms(actor))


@bp.get("/my")
def my_page():
    return render_template("my.html", user=auth.current_user(auth.require_session(token())))


@bp.get("/admin")
def admin_page():
    session = auth.require_session(token())
    actor = services.require_admin(auth.actor_for_token(token()))
    return render_template("admin.html", user=auth.current_user(session), rooms=services.list_rooms(actor, admin_only=True))


@bp.post("/api/admin/rooms")
def create_room_api():
    actor = services.require_admin(auth.actor_for_token(token()))
    if request.mimetype != "application/json":
        raise DomainError("INVALID_INPUT", "请使用 JSON 格式提交会议室资料。")
    return jsonify(ok=True, data=services.create_room(actor, payload())), 201


@bp.post("/api/admin/rooms/<room_id>")
def update_room_api(room_id):
    actor = services.require_admin(auth.actor_for_token(token()))
    if request.mimetype != "application/json":
        raise DomainError("INVALID_INPUT", "请使用 JSON 格式提交会议室资料。")
    return jsonify(ok=True, data=services.update_room(actor, room_id, payload()))


@bp.get("/api/bookings/mine")
def my_bookings_api():
    actor = auth.actor_for_token(token())
    return jsonify(ok=True, data=services.my_bookings(actor, request.args.get("status")))


@bp.post("/api/admin/blocks")
def create_block_api():
    actor = services.require_admin(auth.actor_for_token(token()))
    if request.mimetype != "application/json":
        raise DomainError("INVALID_INPUT", "请使用 JSON 格式提交停用资料。")
    return jsonify(ok=True, data=services.create_block(actor, payload())), 201


@bp.get("/api/admin/bookings")
def admin_bookings_api():
    actor = services.require_admin(auth.actor_for_token(token()))
    return jsonify(ok=True, data=services.admin_bookings(actor, request.args.get("room_id"), request.args.get("date"), request.args.get("status")))


@bp.get("/api/admin/blocks")
def admin_blocks_api():
    actor = services.require_admin(auth.actor_for_token(token()))
    return jsonify(ok=True, data=services.admin_blocks(actor, request.args.get("room_id"), request.args.get("date"), request.args.get("status")))


@bp.get("/api/bookings/<booking_id>")
def booking_detail_api(booking_id):
    return jsonify(ok=True, data=services.booking_detail(auth.actor_for_token(token()), booking_id))


@bp.get("/api/rooms")
def rooms_api():
    return jsonify(ok=True, data=services.list_rooms(auth.actor_for_token(token())))


@bp.post("/api/bookings/<booking_id>/cancel")
def member_cancel_booking_api(booking_id):
    actor = auth.actor_for_token(token())
    if request.mimetype != "application/json" or payload() != {}:
        raise DomainError("INVALID_INPUT", "取消本人预约须提交空 JSON 对象，不接受原因或身份字段。")
    return jsonify(ok=True, data=services.member_cancel_booking(actor, booking_id))


@bp.get("/api/schedule")
def schedule_api():
    actor = auth.actor_for_token(token())
    return jsonify(ok=True, data=services.schedule(actor, request.args.get("room_id"), request.args.get("date")))


@bp.get("/api/availability")
def availability_api():
    actor = auth.actor_for_token(token())
    return jsonify(ok=True, data=services.availability(
        actor, request.args.get("start"), request.args.get("end"), request.args.get("attendees"),
    ))


@bp.get("/api/me")
def me():
    return jsonify(ok=True, data=auth.current_user(auth.require_session(token())))


@bp.post("/api/bookings")
def create_booking_api():
    actor = auth.actor_for_token(token())
    if request.mimetype != "application/json":
        raise DomainError("INVALID_INPUT", "请使用 JSON 格式提交预约。")
    result = services.create_booking(actor, payload())
    return jsonify(ok=True, data=result), 200 if result["replayed"] else 201


@bp.post("/api/login")
def login_api():
    grant = auth.login(token(), csrf(), payload())
    return issue_cookie(jsonify(ok=True, data=grant.user), grant)


@bp.post("/api/logout")
def logout_api():
    payload()  # Content-Type and object shape are required for every POST.
    result = auth.logout(token(), csrf())
    response = jsonify(ok=True, data=result)
    response.delete_cookie(auth.COOKIE_NAME, path="/", httponly=True,
                           secure=current_app.config["SESSION_COOKIE_SECURE"], samesite="Lax")
    return response


def install_handlers(app):
    @app.before_request
    def secure_post():
        g.request_id = uuid.uuid4().hex
        if request.method == "POST":
            if request.headers.get("Origin") != app.config["APP_ORIGIN"]:
                raise DomainError("CSRF_REJECTED", "请求来源验证失败，请从本站页面重试。")
            session = auth.require_session(token(), temporary=request.endpoint == "web.login_api")
            auth.check_csrf(session, csrf())

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(DomainError)
    def domain_error(error):
        if (error.code == "AUTH_REQUIRED" and request.method == "GET"
                and not request.path.startswith("/api")):
            return redirect(url_for("web.login_page", expired="1"))
        return jsonify(ok=False, error={"code": error.code, "message": error.message,
                                        "fields": error.fields, "conflicts": error.conflicts}), STATUS[error.code]

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            if error.code == 404:
                return domain_error(DomainError("NOT_FOUND", "页面或接口不存在。"))
            return domain_error(DomainError("INVALID_INPUT", "请求格式或请求方式不正确。"))
        if isinstance(error, sqlite3.OperationalError) and (
            getattr(error, "sqlite_errorcode", 0) & 0xFF
        ) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
            return domain_error(DomainError("STORE_BUSY", "存储暂忙，请稍后重试；本次操作未成功。"))
        # Never use logger.exception, request headers, payloads, SQL or exception messages.
        app.logger.error("request_id=%s action=%s error_type=%s",
                         getattr(g, "request_id", "unassigned"), request.endpoint or "unmatched", type(error).__name__)
        return domain_error(DomainError("INTERNAL_ERROR", "操作未完成，请稍后重试。"))

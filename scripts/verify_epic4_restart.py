"""Verify Epic 4 persistence across real Waitress process restarts."""

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
from zoneinfo import ZoneInfo

from booking_app import ROOT, db
from scripts.init_demo import DEMO_IDENTITIES, DEMO_SUPERVISORS, seed_users
from scripts.verify_audit_http import LiveServer, source_hashes
from scripts.verify_availability_performance import Client, write_json


TABLES = (
    "applications", "application_occurrences", "booking_supervisors",
    "cancellation_requests", "reservations", "occupancy_slots",
    "maintenance_previews", "audit_events",
)


def snapshot(database):
    with db.read_transaction(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 6
        rows = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in TABLES}
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return {"counts": {table: len(items) for table, items in rows.items()},
            "business_sha256": hashlib.sha256(encoded).hexdigest()}


def run(output):
    fingerprints = source_hashes()
    with tempfile.TemporaryDirectory(prefix="epic4-restart-") as directory:
        temporary = Path(directory)
        database = temporary / "test.sqlite3"
        users = [dict(username=name, display_name=display, role=role,
                      password=secrets.token_urlsafe(24),
                      supervisor_username=DEMO_SUPERVISORS.get(name))
                 for name, display, role in DEMO_IDENTITIES]
        seed_users(database, users)
        server = LiveServer(database, temporary)
        try:
            server.start()
            clients = {}
            for user in users:
                client = Client(server.origin)
                client.login(user)
                clients[user["username"]] = client

            def call(who, path, body=None, expected=200):
                status, response, _ = clients[who].request(path, body)
                assert status == expected and response["ok"], (who, path, status, expected)
                return response["data"]

            student, teacher, admin = "demo_member_a", "demo_teacher_a", "demo_admin"
            room = call(admin, "/api/admin/rooms",
                        {"name": "重启核验室", "location": "合成楼", "capacity": 12}, 201)
            day = (datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=1)).date()
            application_payload = {
                "room_id": room["id"], "title": "连续组会", "purpose": "合成核验",
                "attendees": 3, "start": f"{day}T10:00", "end": f"{day}T11:00",
                "weeks": 8, "intent_key": secrets.token_hex(16),
            }
            application = call(student, "/api/applications", application_payload, 201)["application"]
            assert len(application["occurrences"]) == 8
            approved = call(teacher, f"/api/applications/{application['id']}/approve", {})
            assert len(approved["occurrences"]) == 8
            first_id = approved["occurrences"][0]["reservation_id"]
            later_id = approved["occurrences"][1]["reservation_id"]
            untouched_id = approved["occurrences"][2]["reservation_id"]
            window = {"room_id": room["id"], "start": f"{day}T10:00",
                      "end": f"{day}T11:00", "reason": "维修核验"}
            preview = call(admin, "/api/admin/blocks/preview", window, 201)
            assert [item["id"] for item in preview["affected"]] == [first_id]
            before = snapshot(database)
            pid1 = server.process.pid
            server.stop()
            server.start()
            assert server.process.pid != pid1 and snapshot(database) == before

            replay = call(student, "/api/applications", application_payload)["application"]
            assert replay["id"] == application["id"] and len(replay["occurrences"]) == 8
            assert call(teacher, f"/api/applications/{application['id']}/approve", {})["id"] == application["id"]
            assert snapshot(database) == before

            confirm_body = {"preview_token": preview["preview_token"], "confirmed": True}
            block = call(admin, "/api/admin/blocks/confirm", confirm_body, 201)["block"]
            after_confirm = snapshot(database)
            pid2 = server.process.pid
            server.stop()
            server.start()
            assert server.process.pid != pid2 and snapshot(database) == after_confirm
            repeated = call(admin, "/api/admin/blocks/confirm", confirm_body)
            assert repeated["replayed"] is True and repeated["block"]["id"] == block["id"]
            assert snapshot(database) == after_confirm
            first = call(student, f"/api/bookings/{first_id}")
            later = call(student, f"/api/bookings/{later_id}")
            assert first["status"] == "cancelled" and later["status"] != "cancelled"

            cancellation = call(student, f"/api/bookings/{later_id}/cancellation-requests", {}, 201)["cancellation_request"]
            before_decision = snapshot(database)
            pid3 = server.process.pid
            server.stop()
            server.start()
            assert server.process.pid != pid3 and snapshot(database) == before_decision
            assert call(student, f"/api/bookings/{later_id}")["status"] != "cancelled"
            call(teacher, f"/api/cancellation-requests/{cancellation['id']}/approve", {})
            after_decision = snapshot(database)
            pid4 = server.process.pid
            server.stop()
            server.start()
            assert server.process.pid != pid4 and snapshot(database) == after_decision
            call(teacher, f"/api/cancellation-requests/{cancellation['id']}/approve", {})
            assert snapshot(database) == after_decision
            assert call(student, f"/api/bookings/{later_id}")["status"] == "cancelled"

            call(admin, f"/api/admin/blocks/{block['id']}/revoke", {"reason": "维修结束"})
            final = snapshot(database)
            pid5 = server.process.pid
            server.stop()
            server.start()
            assert server.process.pid != pid5 and snapshot(database) == final
            assert call(student, f"/api/bookings/{first_id}")["status"] == "cancelled"
            assert call(student, f"/api/bookings/{later_id}")["status"] == "cancelled"
            assert call(student, f"/api/bookings/{untouched_id}")["status"] != "cancelled"
            assert len(set(server.pids)) == 6
            report = {"result": "PASS", "schema_version": 6, "clock": "production SystemClock",
                      "distinct_processes": True,
                      "checks": ["eight-week approval", "preview survives restart",
                                 "application and approval replay", "batch confirm survives restart",
                                 "batch confirm replay", "cancellation request survives restart",
                                 "supervisor decision survives restart and replays",
                                 "revoke does not restore bookings"],
                      "before_confirm": before, "after_confirm": after_confirm,
                      "before_cancellation_decision": before_decision,
                      "after_cancellation_decision": after_decision, "after_revoke": final}
        finally:
            server.stop()
    assert source_hashes() == fingerprints
    write_json(output / "result.json", report | {"source_sha256": fingerprints})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()

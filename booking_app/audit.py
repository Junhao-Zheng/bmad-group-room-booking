"""One INSERT on the command's connection; no clock, connection or transaction ownership."""

import json


def audit_writer(conn, event: dict) -> None:
    def encode(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    conn.execute(
        "INSERT INTO audit_events(actor_id,actor_display_name,action,target_type,target_id,"
        "occurred_at,before_json,after_json,reason) VALUES(?,?,?,?,?,?,?,?,?)",
        (event["actor_id"], event["actor_display_name"], event["action"], event["target_type"],
         event["target_id"], event["occurred_at"],
         None if event["before"] is None else encode(event["before"]), encode(event["after"]), event["reason"]),
    )

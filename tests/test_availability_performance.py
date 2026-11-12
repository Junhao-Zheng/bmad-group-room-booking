"""Targeted failure-path checks for the NFR-03 measurement script."""

from contextlib import redirect_stdout
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from booking_app import db
from scripts import verify_availability_performance as perf


class PerformanceHarnessTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)

    def samples(self):
        return [json.loads(line) for line in (self.output / "performance-samples.jsonl").read_text().splitlines()]

    def test_prior_pass_is_invalidated_before_work_and_failure_has_new_run_identity(self):
        perf.write_json(self.output / "performance-result.json", {"result": "PASS", "run_id": "old-run"})
        perf.write_json(self.output / "performance-environment.json", {"run_id": "old-run"})
        observed = {}

        def fail(output_dir, run):
            observed.update(json.loads((output_dir / "performance-result.json").read_text()))
            self.assertEqual(observed["result"], "INCOMPLETE")
            self.assertIs(observed["completed"], False)
            self.assertEqual(observed["run_id"], run["run_id"])
            raise RuntimeError("sensitive diagnostic must not be written")

        stdout = io.StringIO()
        with patch.object(perf, "run_measurement", side_effect=fail), patch("sys.argv", ["verify", "--output-dir", str(self.output)]), redirect_stdout(stdout):
            self.assertEqual(perf.main(), 1)
        result = json.loads((self.output / "performance-result.json").read_text())
        environment = json.loads((self.output / "performance-environment.json").read_text())
        self.assertEqual(result["result"], "INCOMPLETE")
        self.assertIs(result["completed"], False)
        self.assertNotEqual(result["run_id"], "old-run")
        self.assertEqual(result["run_id"], environment["run_id"])
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertRegex(result["started_at_utc"], r"\+00:00$")
        self.assertGreaterEqual(result["finished_at_utc"], result["started_at_utc"])
        self.assertEqual(len(environment["app_source_sha256"]), 64)
        digest = environment["app_source_files_sha256"]["booking_app/services.py"]
        self.assertEqual(digest, hashlib.sha256((perf.ROOT / "booking_app/services.py").read_bytes()).hexdigest())
        self.assertNotIn("sensitive", stdout.getvalue() + json.dumps(result))

    def test_json_parse_failure_retains_status_and_safe_body_fingerprint_in_every_sample(self):
        raw = b'{invalid-json: "private response text"}'

        class Response:
            status = 503
            headers = Message()
            headers["Content-Type"] = "application/json"

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return raw

        clients = [perf.Client("http://127.0.0.1:1") for _ in range(10)]
        for client in clients:
            client.opener = Mock()
            client.opener.open.return_value = Response()
        report = perf.measure(clients, {"rooms": [], "bookings": []}, self.output, "parse-failure")
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual((report["errors"], report["wrong_results"]), (220, 220))
        samples = self.samples()
        self.assertEqual(len(samples), 220)
        for sample in samples:
            self.assertEqual(sample["http_status"], 503)
            self.assertEqual(sample["error"], "JSONDecodeError")
            self.assertEqual(sample["body_bytes"], len(raw))
            self.assertEqual(sample["body_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertIsNone(sample["response"])
            self.assertEqual(sample["run_id"], "parse-failure")
        self.assertNotIn("private response text", (self.output / "performance-samples.jsonl").read_text())

    def test_broken_barrier_returns_and_persists_all_submitted_error_samples(self):
        barrier = Mock()
        barrier.wait.side_effect = threading.BrokenBarrierError
        clients = [Mock() for _ in range(10)]
        with patch.object(perf.threading, "Barrier", return_value=barrier):
            report = perf.measure(clients, {"rooms": [], "bookings": []}, self.output, "barrier-failure")
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["errors"], 220)
        self.assertEqual(len(self.samples()), 220)
        self.assertEqual([row["index"] for row in self.samples()], list(range(220)))
        for row in self.samples():
            self.assertIsNone(row["http_status"])
            self.assertEqual(row["error"], "BrokenBarrierError")
            self.assertIs(row["correct"], False)
        for client in clients:
            client.request.assert_not_called()

    def test_json_contract_comparison_rejects_bool_int_and_float_substitutions(self):
        expected = {"ok": True, "data": {"items": [{"id": 1, "name": "房间", "location": "位置", "capacity": 10}], "total": 1}}
        self.assertTrue(perf.strict_json_equal(expected, json.loads(json.dumps(expected))))
        for field, bad in (("ok", 1), ("id", True), ("id", 1.0), ("capacity", 10.0), ("total", True), ("total", 1.0)):
            actual = json.loads(json.dumps(expected))
            if field == "ok":
                actual[field] = bad
            elif field == "total":
                actual["data"][field] = bad
            else:
                actual["data"]["items"][0][field] = bad
            with self.subTest(field=field, bad=bad):
                self.assertEqual(actual, expected, "This case must expose Python's loose equality.")
                self.assertFalse(perf.strict_json_equal(actual, expected))
        client = Mock()
        client.request.return_value = (200, {"ok": 1, "data": {"items": [], "total": 0.0}}, 1.0)
        report = perf.measure([client] * 10, {"rooms": [], "bookings": []}, self.output, "wrong-json-types")
        self.assertEqual((report["result"], report["errors"], report["wrong_results"]), ("FAIL", 0, 220))
        self.assertEqual(report["by_query_path"]["sql_availability"]["measured_requests"], 160)
        self.assertEqual(report["by_query_path"]["over_capacity_fast_path"]["measured_requests"], 40)
        self.assertEqual(report["by_query_path"]["sql_availability"]["p95_ms"], 1.0)

    def test_fixture_created_and_cancelled_times_precede_now_and_each_other(self):
        database = self.output / "fixture.sqlite3"
        db.initialize_database(database)
        with db.write_transaction(database) as conn:
            conn.execute("INSERT INTO users(id,username,display_name,password_hash,role,created_at) VALUES(1,'synthetic','合成','unused-test-hash','member',?)", (perf.BASE - 86400 * 60,))
        fixture = perf.seed_fixture(database, [1])
        integrity = perf.verify_fixture(database, fixture)
        self.assertIs(integrity["all_created_and_cancelled_before_fixed_now_in_order"], True)
        for record in fixture["bookings"]:
            self.assertLess(record["created_at"], min(record["start"], perf.BASE))
            if record["cancelled"]:
                self.assertLess(record["created_at"], record["cancelled_at"])
                self.assertLess(record["cancelled_at"], min(record["start"], perf.BASE))
        record = next(row for row in fixture["bookings"] if row["cancelled"] and row["start"] > perf.BASE)
        with db.write_transaction(database) as conn:
            conn.execute("UPDATE reservations SET cancelled_at=? WHERE id=?", (perf.BASE + 1, record["id"]))
        record["cancelled_at"] = perf.BASE + 1
        with self.assertRaises(AssertionError):
            perf.verify_fixture(database, fixture)
        with db.write_transaction(database) as conn:
            conn.execute("UPDATE reservations SET cancelled_at=created_at WHERE id=?", (record["id"],))
        record["cancelled_at"] = record["created_at"]
        with self.assertRaises(AssertionError):
            perf.verify_fixture(database, fixture)


if __name__ == "__main__":
    unittest.main()

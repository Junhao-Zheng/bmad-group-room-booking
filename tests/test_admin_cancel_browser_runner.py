"""Fail-closed browser evidence, using the real temporary SQLite DB and Waitress."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from booking_app import ROOT
from scripts import verify_admin_cancel_browser as runner
from scripts.verify_availability_performance import Client


class AdminCancelBrowserFailureTests(unittest.TestCase):
    def check_failure(self, mode, expected_phase):
        parent = ROOT / 'work/quality-review-fixes'
        parent.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=f'browser-{mode}-', dir=parent))
        target = output / 'browser-results.json'
        target.write_text(json.dumps({'result': 'PASS', 'completed': True, 'old_run': True}))
        missing_playwright_root = output / 'deliberately-absent-playwright-root'
        self.assertFalse(missing_playwright_root.exists())
        controlled_environment = {'verification_mode': 'stubbed-driver-real-waitress-sqlite',
                                  'browser': 'not-started', 'playwright': 'not-required'}
        def environment_metadata(args):
            self.assertEqual(args.playwright_root, missing_playwright_root)
            self.assertFalse(args.playwright_root.exists())
            self.assertEqual(args.browser_executable, Path(sys.executable))
            return controlled_environment
        private_marker = 'DO-NOT-OUTPUT-SYNTHETIC-CREDENTIAL-OR-DRIVER-LOG'
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        def driver(command, env, registry):
            self.assertEqual(Path(env['NODE_PATH']), missing_playwright_root)
            self.assertFalse(Path(env['NODE_PATH']).exists())
            # Seeded evidence must already be on disk before the driver executes.
            run_dir = Path(command[4])
            seeded = json.loads((run_dir / 'storage.json').read_text())
            self.assertIsNone(seeded['after'])
            self.assertFalse(seeded['cancellation_invariants_verified'])
            client = Client(command[2])
            users = json.loads(Path(command[3]).read_text())['users']
            client.login(users[2])
            status, _, _ = client.request('/api/admin/bookings/103/cancel', {'reason': '故障留证合成原因'})
            self.assertEqual(status, 200)
            if mode == 'timeout':
                raise subprocess.TimeoutExpired(command, 1, output=private_marker, stderr=private_marker)
            if mode == 'driver':
                return subprocess.CompletedProcess(command, 1, private_marker, private_marker)
            # A driver claiming PASS after incomplete mutations must fail the real storage oracle.
            return subprocess.CompletedProcess(command, 0, json.dumps({'result': 'PASS'}), private_marker)
        args = ['verify_admin_cancel_browser', '--output-dir', str(output), '--port', str(port),
                '--playwright-root', str(missing_playwright_root), '--browser-executable', sys.executable]
        stdout = io.StringIO()
        with (patch('sys.argv', args), patch.object(runner, 'run_driver', driver),
              patch.object(runner, 'environment_metadata', side_effect=environment_metadata) as metadata,
              redirect_stdout(stdout)):
            self.assertEqual(runner.main(), 1)
        metadata.assert_called_once()
        (output / 'runner-stdout.json').write_text(stdout.getvalue())
        report = json.loads(target.read_text())
        self.assertEqual(report['environment'], controlled_environment)
        self.assertFalse(missing_playwright_root.exists())
        self.assertEqual(report['result'], 'INCOMPLETE'); self.assertFalse(report['completed'])
        self.assertNotIn('old_run', report)
        run_dir = output / report['artifact_directory']
        storage = json.loads((run_dir / 'storage.json').read_text())
        diagnostics = json.loads((run_dir / 'browser-diagnostics.json').read_text())
        self.assertFalse(storage['cancellation_invariants_verified'])
        self.assertEqual(storage['phase'], expected_phase)
        self.assertEqual(diagnostics['phase'], expected_phase)
        self.assertLessEqual(set(diagnostics), {'phase', 'error_type', 'driver_returncode', 'storage_error_type'})
        self.assertEqual(set(storage['before']), {'reservations', 'occupancy_slots', 'audit_events'})
        self.assertEqual(set(storage['after']), {'reservations', 'occupancy_slots', 'audit_events'})
        self.assertIsNone(next(row for row in storage['before']['reservations'] if row['id'] == 103)['cancelled_at'])
        self.assertIsNotNone(next(row for row in storage['after']['reservations'] if row['id'] == 103)['cancelled_at'])
        for path in output.rglob('*.json'):
            text = path.read_text()
            self.assertNotIn(private_marker, text)
            self.assertNotIn('password', text)
            self.assertNotIn('csrf_token', text)
            self.assertNotIn('token_hash', text)
        print(f'{mode} safe failure evidence: {output.relative_to(ROOT)}')

    def test_driver_nonzero_preserves_mutated_storage_without_private_output(self):
        self.check_failure('driver', 'driver')

    def test_driver_exception_preserves_mutated_storage_without_private_output(self):
        self.check_failure('timeout', 'driver')

    def test_storage_assertion_failure_preserves_before_after_and_invalidates_old_pass(self):
        self.check_failure('storage', 'storage_assertions')


if __name__ == '__main__': unittest.main()

"""Real launcher failure must invalidate a prior result and keep artifact runs separate."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

from booking_app import ROOT


class BrowserVerificationTests(unittest.TestCase):
    def test_existing_pass_is_invalidated_before_real_startup_failure(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            output = Path(directory)
            target = output / 'browser-results.json'
            target.write_text(json.dumps(dict(result='PASS',completed=True,run_id='previous-run')))
            old = output / 'runs' / 'previous-run' / 'replay-network-1280.jsonl'
            old.parent.mkdir(parents=True)
            old.write_text('{"prior":"artifact"}\n')
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            before = datetime.now(timezone.utc)
            result = subprocess.run([sys.executable, '-m', 'scripts.verify_auth_browser', '--replay',
                '--port', str(occupied.getsockname()[1]), '--output-dir', str(output)],
                cwd=ROOT, capture_output=True, text=True, timeout=15)
            after = datetime.now(timezone.utc)
            self.assertEqual(result.returncode, 1)
            report = json.loads(target.read_text())
            self.assertEqual(report, json.loads(result.stdout))
            self.assertEqual(result.stderr, '')
            self.assertEqual(report['result'], 'INCOMPLETE')
            self.assertIs(report['completed'], False)
            self.assertEqual(report['error_type'], 'OSError')
            self.assertNotEqual(report['run_id'], 'previous-run')
            self.assertTrue(before <= datetime.fromisoformat(report['started_at_utc']) <= after)
            self.assertTrue(before <= datetime.fromisoformat(report['finished_at_utc']) <= after)
            self.assertEqual(set(report), {'result','completed','error_type','run_id','started_at_utc',
                                          'finished_at_utc','artifact_directory'})
            self.assertEqual(report['artifact_directory'], f"runs/{report['run_id']}")
            self.assertEqual(list((output / report['artifact_directory']).iterdir()), [])
            self.assertEqual(old.read_text(), '{"prior":"artifact"}\n')

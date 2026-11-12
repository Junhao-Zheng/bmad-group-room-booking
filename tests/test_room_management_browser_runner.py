"""Only safe failure coordinates survive a failed room browser driver."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_room_management_browser as runner


class RoomManagementBrowserRunnerTests(unittest.TestCase):
    def test_failed_driver_preserves_stage_and_location_in_incomplete_but_omits_secrets(self):
        secret = 'SYNTHETIC_PRIVATE_password_cookie_csrf_SQL'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            def fail(args):
                (args.output_dir/'failure-diagnostics.json').write_text(json.dumps({
                    'stage':'capacity','error_type':'AssertionError','actual':secret,'message':secret,
                    'source':{'file':'scripts/verify_room_management_browser.cjs','line':73,'column':9,'expected':secret}}))
                return runner.check_driver_result(subprocess.CompletedProcess(['synthetic'],1,secret,secret), args.output_dir)
            stdout = io.StringIO()
            with patch('sys.argv',['runner','--output-dir',str(output)]), \
                    patch.object(runner,'environment_metadata',return_value={}), \
                    patch.object(runner,'source_fingerprints',return_value={}), \
                    patch.object(runner,'run',side_effect=fail), redirect_stdout(stdout):
                self.assertEqual(runner.main(),1)
            report = json.loads((output/'browser-results.json').read_text())
            self.assertEqual(report['result'],'INCOMPLETE');self.assertFalse(report['completed'])
            expected = dict(stage='capacity',error_type='AssertionError',source=dict(
                file='scripts/verify_room_management_browser.cjs',line=73,column=9))
            self.assertEqual(report['diagnostics'],expected)
            self.assertEqual(json.loads((output/report['artifact_directory']/'failure-diagnostics.json').read_text()),expected)
            for text in [stdout.getvalue(),*(path.read_text() for path in output.rglob('*.json'))]:
                self.assertNotIn(secret,text);self.assertNotIn('expected',text);self.assertNotIn('actual',text)

    def test_timeout_retains_controlled_stage_and_rejects_untrusted_type_or_location(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            (output/'progress.json').write_text(json.dumps({'stage':'multiline'}))
            self.assertEqual(runner.failure_diagnostics(output,timeout=True),dict(stage='multiline',error_type='TimeoutError',source=None))
            (output/'failure-diagnostics.json').write_text(json.dumps({'stage':['private'],'error_type':'private',
                'source':{'file':'/private/credentials.json','line':True,'column':'secret'}}))
            self.assertEqual(runner.failure_diagnostics(output),dict(stage='startup',error_type='Error',source=None))


if __name__ == '__main__': unittest.main()

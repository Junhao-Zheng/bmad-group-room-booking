"""Real launcher failure must invalidate a prior result and keep artifact runs separate."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

from scripts import verify_auth_browser as runner

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
            package = output / 'modules/playwright/package.json'
            package.parent.mkdir(parents=True)
            package.write_text('{"version":"1.58.2"}')
            before = datetime.now(timezone.utc)
            result = subprocess.run([sys.executable, '-m', 'scripts.verify_auth_browser', '--replay',
                '--port', str(occupied.getsockname()[1]), '--output-dir', str(output), '--playwright-root', str(output / 'modules')],
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
                                          'finished_at_utc','artifact_directory','configuration','environment','app_source_files_sha256','verification_source_files_sha256'})
            self.assertEqual(report['artifact_directory'], f"runs/{report['run_id']}")
            self.assertEqual(list((output / report['artifact_directory']).iterdir()), [])
            self.assertEqual(old.read_text(), '{"prior":"artifact"}\n')

    def test_missing_metadata_invalidates_previous_pass_before_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'browser-results.json'
            target.write_text(json.dumps({'result':'PASS','completed':True,'run_id':'old'}))
            with patch.object(sys, 'argv', ['verify_auth_browser', '--output-dir', str(root),
                      '--playwright-root', str(root / 'missing')]), patch.object(runner, 'run_browser') as run, redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 1)
                run.assert_not_called()
            report = json.loads(target.read_text())
            self.assertEqual(report['result'], 'INCOMPLETE')
            self.assertFalse(report['completed'])
            self.assertNotEqual(report['run_id'], 'old')
            self.assertEqual(report['error_type'], 'FileNotFoundError')

    def test_changed_sources_invalidate_browser_success(self):
        import base64
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII=')
        def browser(args):
            (args.output_dir/'fixture.png').write_bytes(png)
            return {'result':'PASS'}
        for changed in [False,True]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                fingerprints=[{'app_source_files_sha256':{'a':'before'}},{'app_source_files_sha256':{'a':'after' if changed else 'before'}}]
                with patch.object(sys,'argv',['verify_auth_browser','--output-dir',str(root)]), \
                     patch.object(runner,'environment_metadata',return_value={}), \
                     patch.object(runner,'source_fingerprints',side_effect=fingerprints), \
                     patch.object(runner,'run_browser',side_effect=browser), redirect_stdout(io.StringIO()):
                    self.assertEqual(runner.main(),1 if changed else 0)
                report=json.loads((root/'browser-results.json').read_text())
                self.assertEqual(report['result'],'INCOMPLETE' if changed else 'PASS')
                self.assertIs(report['completed'],not changed)
                if changed:self.assertEqual(report['error_type'],'RuntimeError')
                else:self.assertEqual(len(report['screenshots_sha256']),1)

    def test_real_fingerprints_detect_edit_add_remove_and_bind_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'booking_app').mkdir()
            app=root/'booking_app/a.py';app.write_text('original')
            helpers=('scripts/verify_auth_browser.py','scripts/verify_auth_browser.cjs',
                     'scripts/init_demo.py','tests/schedule_fixtures.py')
            for name in helpers:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(name)
            with patch.object(runner,'ROOT',root):
                before=runner.source_fingerprints()
                self.assertEqual(set(before['app_source_files_sha256']),{'booking_app/a.py'})
                self.assertEqual(set(before['verification_source_files_sha256']),set(helpers))
                app.write_text('edited');edited=runner.source_fingerprints()
                self.assertNotEqual(before['app_source_files_sha256']['booking_app/a.py'],edited['app_source_files_sha256']['booking_app/a.py'])
                added=root/'booking_app/added.js';added.write_text('new')
                self.assertIn('booking_app/added.js',runner.source_fingerprints()['app_source_files_sha256'])
                app.unlink();self.assertNotIn('booking_app/a.py',runner.source_fingerprints()['app_source_files_sha256'])
                for name in helpers:
                    (root/name).write_text('changed helper')
                    self.assertNotEqual(before['verification_source_files_sha256'][name],runner.source_fingerprints()['verification_source_files_sha256'][name])

    def test_real_http_isolates_opposite_parent_https_configuration(self):
        import os
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        result=subprocess.run([sys.executable,'-m','scripts.verify_auth_http','--port',str(port)],
            cwd=ROOT,env=dict(os.environ,COOKIE_SECURE='true',TRUSTED_HOSTS='invalid.invalid'),
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,'isolated HTTP verification failed')
        report=json.loads(result.stdout)
        self.assertEqual(report['result'],'PASS')
        self.assertEqual(report['http_isolation']['parent'],{'COOKIE_SECURE':'true','TRUSTED_HOSTS':'invalid.invalid'})
        self.assertEqual(report['http_isolation']['child'],{'COOKIE_SECURE':'false','TRUSTED_HOSTS':'127.0.0.1','APP_ORIGIN':f'http://127.0.0.1:{port}'})

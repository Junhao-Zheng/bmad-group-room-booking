"""Portable browser resolution without requiring an installed browser in unit tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from booking_app import ROOT
from scripts import verify_audit_browser as runner

class AuditBrowserRunnerTests(unittest.TestCase):
    def test_explicit_browser_wins_without_playwright_lookup(self):
        args=SimpleNamespace(browser_executable=Path('chosen/chrome'))
        with patch.object(runner.subprocess,'run') as command:
            self.assertEqual(runner.resolve_browser_executable(args,{}),Path('chosen/chrome').resolve())
            command.assert_not_called()

    def test_default_browser_uses_playwright_executable_path(self):
        args=SimpleNamespace(browser_executable=None);env={'NODE_PATH':'synthetic/modules'}
        with patch.object(runner.subprocess,'run',return_value=SimpleNamespace(stdout='/synthetic/not-installed/chromium')) as command:
            self.assertEqual(runner.resolve_browser_executable(args,env),Path('/synthetic/not-installed/chromium'))
            command.assert_called_once_with(['node','-e','process.stdout.write(require("playwright").chromium.executablePath())'],
                env=env,cwd=ROOT,capture_output=True,text=True,check=True,timeout=10,start_new_session=True)

    def test_cli_omission_passes_none_to_runner(self):
        with TemporaryDirectory() as directory,patch.object(runner,'source_hashes',return_value={}),patch.object(runner,'run',return_value={'result':'PASS','completed':True}) as run,patch('builtins.print'):
            self.assertEqual(runner.main(['--output-dir',directory]),0)
            self.assertIsNone(run.call_args.args[0].browser_executable)

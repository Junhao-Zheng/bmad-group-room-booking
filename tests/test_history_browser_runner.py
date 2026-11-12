"""Real process lifecycle checks for the isolated history browser runner (POSIX)."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import verify_history_browser as runner


def live_group_pids(group_id):
    rows = subprocess.check_output(['ps', '-axo', 'pid=,pgid=,state='], text=True).splitlines()
    return [int(pid) for line in rows for pid, group, state in [line.split()]
            if int(group) == group_id and not state.startswith('Z')]


def wait_for_file(path):
    deadline = time.monotonic() + 3
    while not path.exists() and time.monotonic() < deadline: time.sleep(.01)
    if not path.exists(): raise AssertionError('Child failed to start')


class HistoryBrowserRunnerTests(unittest.TestCase):
    def test_permission_denied_with_successful_zombie_only_snapshot_is_recovered(self):
        group_id=max(os.getpgrp()+1, 999999)
        with patch.object(runner.os, 'killpg', side_effect=PermissionError('injected zombie-only group')) as kill, \
                patch.object(runner.subprocess, 'check_output', return_value=f'{group_id} Z\n{group_id} Z+\n1 S\n') as table:
            runner.stop_process_group(group_id, grace=.03)
        kill.assert_called_once_with(group_id, signal.SIGTERM)
        table.assert_called_once_with(['ps', '-axo', 'pgid=,state='], text=True)

    def test_fast_exit_groups_are_reaped_without_treating_zombies_as_live(self):
        for _ in range(20):
            process = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'], start_new_session=True)
            try:
                runner.stop_process_group(process.pid, process, grace=.03)
                self.assertIsNotNone(process.returncode)
                self.assertEqual(live_group_pids(process.pid), [])
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=2)

    def test_permission_denied_with_live_group_is_not_reported_as_cleaned(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'], start_new_session=True)
        try:
            with patch.object(runner.os, 'killpg', side_effect=PermissionError('injected denied signal')):
                with self.assertRaises(PermissionError): runner.stop_process_group(process.pid, process, grace=.03)
            self.assertIsNone(process.poll())
            self.assertIn(process.pid, live_group_pids(process.pid))
        finally: runner.stop_process_group(process.pid, process, grace=.03)

    def test_permission_denied_and_unreadable_process_table_fails_closed(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'], start_new_session=True)
        try:
            with patch.object(runner.os, 'killpg', side_effect=PermissionError('injected denied signal')), \
                    patch.object(runner.subprocess, 'check_output', side_effect=subprocess.CalledProcessError(1, ['ps'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    runner.stop_process_group(process.pid, process, grace=.03)
            self.assertIsNone(process.poll())
            self.assertIn(process.pid, live_group_pids(process.pid))
        finally: runner.stop_process_group(process.pid, process, grace=.03)

    def test_driver_failure_and_timeout_reap_detached_browser_group_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
            try:
                for timeout in [False, True]:
                    with self.subTest(timeout=timeout):
                        work = root / str(timeout); work.mkdir()
                        ready = work / 'ready'
                        child = work / 'fake-browser'
                        child.write_text(f'#!{sys.executable}\nimport signal, time\nfrom pathlib import Path\n'
                            f'signal.signal(signal.SIGTERM, signal.SIG_IGN)\nPath({str(ready)!r}).touch()\ntime.sleep(30)\n')
                        child.chmod(0o700)
                        wrapper, registry = runner.browser_wrapper(work, child)
                        driver = ('import subprocess, time\nfrom pathlib import Path\n'
                            f'subprocess.Popen([{str(wrapper)!r}], start_new_session=True, '
                            'stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n'
                            f'while not Path({str(ready)!r}).exists(): time.sleep(.01)\n' +
                            ('time.sleep(30)\n' if timeout else 'raise SystemExit(17)\n'))
                        if timeout:
                            with self.assertRaises(subprocess.TimeoutExpired):
                                # Include startup of the driver, wrapper and synthetic browser before the timeout probe.
                                runner.run_driver([sys.executable, '-c', driver], dict(os.environ), registry, timeout=5)
                        else:
                            result = runner.run_driver([sys.executable, '-c', driver], dict(os.environ), registry, timeout=3)
                            self.assertEqual(result.returncode, 17)
                        self.assertTrue(ready.exists(), 'Detached browser must actually start before failure injection')
                        groups = [int(value) for value in registry.read_text().splitlines()]
                        self.assertEqual(len(groups), 1)
                        self.assertEqual(live_group_pids(groups[0]), [])
                        self.assertIsNone(sentinel.poll(), 'Unrelated process must remain running')
            finally: runner.stop_process_group(sentinel.pid, sentinel, grace=.05)

    def test_server_ignoring_term_is_force_killed_and_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / 'ready'
            process = subprocess.Popen([sys.executable, '-c',
                'import signal,time\nfrom pathlib import Path\n'
                f'signal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath({str(ready)!r}).touch()\ntime.sleep(30)'],
                start_new_session=True)
            try:
                wait_for_file(ready)
                runner.stop_process_group(process.pid, process, grace=.05)
                self.assertEqual(process.returncode, -signal.SIGKILL)
                self.assertEqual(live_group_pids(process.pid), [])
            finally:
                if process.poll() is None: runner.stop_process_group(process.pid, process, grace=.05)

    def test_missing_playwright_metadata_replaces_prior_pass_with_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'browser-results.json'
            target.write_text(json.dumps({'result':'PASS','completed':True,'run_id':'old-pass'}))
            with patch.object(sys, 'argv', ['verify_history_browser', '--output-dir', str(root),
                                           '--playwright-root', str(root / 'missing')]), redirect_stdout(io.StringIO()):
                self.assertEqual(runner.main(), 1)
            result = json.loads(target.read_text())
            self.assertEqual(result['result'], 'INCOMPLETE')
            self.assertFalse(result['completed'])
            self.assertNotEqual(result['run_id'], 'old-pass')
            self.assertEqual(result['error_type'], 'FileNotFoundError')

if __name__ == '__main__': unittest.main()

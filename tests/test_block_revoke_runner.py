"""Targeted revocation evidence, cleanup publication and storage-oracle regressions."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_block_revoke_browser as runner
from scripts import verify_block_revoke_http as http
from tests.schedule_fixtures import NOW


def example_facts():
    before=dict(rooms=[dict(id=1,name='原会议室',location='楼',capacity=20,created_at=NOW,updated_at=NOW)],
                reservations=[],occupancy_slots=[],audit_events=[dict(id=1,action='room.created',target_id=1)],
                integrity_check='ok',foreign_key_check=[])
    for index,key in enumerate(runner.TARGET_REASONS):
        start=NOW+index*7200
        row=dict(id=key,kind='block',room_id=1,user_id=3,title=None,purpose=None,attendees=None,reason=f'原原因 {key}',
                 start_at=start,end_at=start+3600,intent_key=None,request_payload=None,created_at=NOW-86400,
                 cancelled_at=None,cancelled_by=None,cancel_reason=None)
        before['reservations'].append(row)
        before['occupancy_slots'] += [dict(room_id=1,slot_start=slot,reservation_id=key) for slot in range(start,start+3600,1800)]
    before['reservations'].append(dict(id=999,kind='booking',room_id=1,user_id=1,cancelled_at=NOW-1,start_at=NOW,end_at=NOW+3600))
    after=deepcopy(before);after['occupancy_slots']=[]
    for index,row in enumerate(after['reservations'][:4]):
        key=row['id'];reason=runner.TARGET_REASONS[key]
        initial=dict(id=key,room_id=1,creator_id=3,reason=f'原原因 {key}',start_at=row['start_at'],end_at=row['end_at'],
                     created_at=NOW-86400,revoked_at=None,revoked_by_id=None,revoke_reason=None)
        row.update(cancelled_at=NOW,cancelled_by=3,cancel_reason=reason)
        after['audit_events'].append(dict(id=index+2,actor_id=3,actor_display_name='演示管理员',action='block.revoked',
            target_type='block',target_id=key,occurred_at=NOW,reason=reason,before_json=json.dumps(initial),
            after_json=json.dumps(initial|dict(revoked_at=NOW,revoked_by_id=3,revoke_reason=reason))))
    return before,after


class RevokeStorageOracleTests(unittest.TestCase):
    def test_exact_four_transitions_and_existing_facts_pass(self):
        self.assertTrue(runner.verify_storage(*example_facts())['full_target_rows_and_ids_verified'])

    def test_deleted_target_is_rejected_even_if_its_slots_and_audit_are_deleted(self):
        before,after=example_facts();after['reservations']=after['reservations'][1:];after['audit_events'].pop(1)
        with self.assertRaises(AssertionError): runner.verify_storage(before,after)

    def test_original_target_fields_must_not_change(self):
        for field,value in [('room_id',2),('reason','changed'),('start_at',NOW+1800),('end_at',NOW+7200),('created_at',0),('user_id',2),('kind','booking')]:
            with self.subTest(field=field):
                before,after=example_facts();after['reservations'][0][field]=value
                with self.assertRaises(AssertionError): runner.verify_storage(before,after)

    def test_rooms_other_records_old_audits_and_slots_cannot_change(self):
        for change in ('room','other-record','old-audit','retained-slot','target-id','extra-record'):
            with self.subTest(change=change):
                before,after=example_facts()
                if change=='room': after['rooms'][0]['name']='changed'
                elif change=='other-record': after['reservations'][-1]['user_id']=2
                elif change=='old-audit': after['audit_events'][0]['target_id']=5
                elif change=='retained-slot': after['occupancy_slots']=[before['occupancy_slots'][0]]
                elif change=='target-id': after['reservations'][0]['id']=10000
                else: after['reservations'].append(dict(after['reservations'][0],id=10001))
                with self.assertRaises(AssertionError): runner.verify_storage(before,after)

    def test_complete_audit_snapshots_actor_time_reason_and_target_are_verified(self):
        for field,value in [('before_json','{}'),('after_json','{}'),('actor_id',2),('occurred_at',NOW+1),('reason','wrong'),('target_id',999),('target_type','booking')]:
            with self.subTest(field=field):
                before,after=example_facts();after['audit_events'][1][field]=value
                with self.assertRaises(AssertionError): runner.verify_storage(before,after)


class RevokeRunnerTests(unittest.TestCase):
    def test_safe_diagnostics_strip_sentinel_and_untrusted_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'failure-diagnostics.json').write_text(json.dumps(dict(stage=['SECRET'],error_type={'SECRET':1},
                source=dict(file='SECRET',line=1,column=1),message='SECRET',stack='SECRET')))
            result=runner.failure_diagnostics(root)
            self.assertEqual(result,dict(stage='startup',error_type='Error',source=None))
            self.assertNotIn('SECRET',(root/'failure-diagnostics.json').read_text())

    def test_publication_failure_replaces_prior_pass_and_has_unique_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);target=output/'browser-result.json'
            target.write_text(json.dumps(dict(result='PASS',completed=True,run_id='old')))
            seen=[]
            def fail(args):
                seen.append(json.loads(target.read_text()))
                (args.output_dir/'database-facts.json').write_text(json.dumps(dict(before={'synthetic':True},after={})))
                raise RuntimeError('SENTINEL_PRIVATE_DRIVER_LOG')
            with patch.object(runner,'environment_metadata',return_value={'controlled':True}), patch.object(runner,'run',side_effect=fail), redirect_stdout(io.StringIO()) as stdout:
                status=runner.main(['--output-dir',directory,'--playwright-root',str(output/'not-installed')])
            self.assertEqual(status,1);report=json.loads(target.read_text())
            self.assertEqual(seen[0]['result'],'INCOMPLETE');self.assertFalse(report['completed']);self.assertNotEqual(report['run_id'],'old')
            self.assertNotIn('SENTINEL',stdout.getvalue()+target.read_text())
            self.assertTrue((output/report['artifact_directory']/'database-facts.json').exists())

    def test_source_change_or_cleanup_exception_cannot_publish_pass(self):
        for mode in ('hash-change','cleanup-failure'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                def work(args):
                    if mode=='cleanup-failure': raise PermissionError('SECRET cleanup failure')
                    return dict(result='PASS')
                with patch.object(runner,'environment_metadata',return_value={'controlled':True}), patch.object(runner,'run',side_effect=work), \
                     patch.object(runner,'source_hashes',side_effect=[{'source':'before'},{'source':'after'}]),redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(runner.main(['--output-dir',directory,'--playwright-root',str(Path(directory)/'not-installed')]),1)
                result=json.loads((Path(directory)/'browser-result.json').read_text())
                self.assertEqual(result['result'],'INCOMPLETE');self.assertFalse(result['completed']);self.assertNotIn('SECRET',stdout.getvalue())

    def test_available_before_after_facts_are_saved_before_oracle_rejection(self):
        # Driver and metadata are controlled: this Python test needs neither Node nor Playwright/Chrome.
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);fake_metadata={'controlled':True}
            args=argparse.Namespace(output_dir=output,playwright_root=output/'not-installed',browser_executable=Path(sys.executable),driver_fault=None,driver_timeout=2)
            completed=runner.subprocess.CompletedProcess([],0,json.dumps(dict(result='PASS',viewports=[dict(width=1280,height=800),dict(width=390,height=844)])),'PRIVATE_STDERR')
            original=runner.subprocess.check_output
            def metadata(command,*a,**kw):
                return 'controlled-node' if command==['node','--version'] else original(command,*a,**kw)
            with patch.object(runner,'environment_metadata',return_value=fake_metadata),patch.object(runner,'run_driver',return_value=completed), \
                 patch.object(runner.subprocess,'check_output',side_effect=metadata):
                with self.assertRaises(AssertionError): runner.run(args)
            saved=json.loads((output/'database-facts.json').read_text())
            self.assertTrue(saved['before']['reservations']);self.assertEqual(saved['before'],saved['after'])
            self.assertTrue(json.loads((output/'process-cleanup.json').read_text())['completed'])
            self.assertNotIn('PRIVATE_STDERR',''.join(path.read_text() for path in output.glob('*.json')))

    def test_system_temporary_database_does_not_require_root_work(self):
        for module in (runner,http):
            with self.subTest(module=module.__name__),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);output=root/'external';output.mkdir()
                args=argparse.Namespace(output_dir=output)
                with patch.object(module,'ROOT',root),patch.object(module,'seed_users',side_effect=RuntimeError('reached seeding')) as seed:
                    with self.assertRaisesRegex(RuntimeError,'reached seeding'):
                        module.run(args if module is runner else output)
                self.assertEqual(seed.call_count,1);self.assertFalse((root/'work').exists())

    def test_source_hashes_cover_driver_runner_transitive_helpers_and_fixtures(self):
        originals=http.source_hashes()
        required={'scripts/verify_block_revoke_browser.py','scripts/verify_block_revoke_browser.cjs','scripts/verify_history_browser.py',
                  'scripts/verify_auth_browser.py','tests/history_fixtures.py','tests/schedule_fixtures.py','tests/maintenance_contract.py','uv.lock'}
        self.assertTrue(required <= originals.keys())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in originals:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((http.ROOT/name).read_bytes())
            with patch.object(http,'ROOT',root):
                first=http.source_hashes()
                for name in required:
                    path=root/name;path.write_text(path.read_text()+'\n# fingerprint probe\n')
                    self.assertNotEqual(http.source_hashes()[name],first[name])


if __name__=='__main__': unittest.main()

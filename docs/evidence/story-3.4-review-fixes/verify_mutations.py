"""Reproduce review mutations in memory; application files are never overwritten."""
from pathlib import Path
import io
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from booking_app import dto
from tests.test_audit import AuditTests

original=dto.audit_event

def drop_reason(row):
    return original(row)|{'reason':None}

output=Path(__file__).resolve().parent
stream=io.StringIO()
case=unittest.defaultTestLoader.loadTestsFromName('test_all_seven_actions_exact_snapshots_and_repeats',AuditTests)
with patch.object(dto,'audit_event',drop_reason):
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(case)
(output/'null-reason-mutation.log').write_text(stream.getvalue())
assert result.testsRun==1 and len(result.failures)==1 and not result.errors
assert "None != 'finished'" in result.failures[0][1]
report={'mutation':'every AuditEvent.reason returned as null','application_source_changed':False,
        'targeted_test':'AuditTests.test_all_seven_actions_exact_snapshots_and_repeats',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'mutation_rejected':True,'independent_expected_reason':'finished'}
(output/'null-reason-mutation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report))

# Run only the full display-binding test against private mutated copies. The
# production source, initial evidence and working-tree tests stay untouched.
import shutil
import subprocess
import tempfile

source=(ROOT/'booking_app/static/audit.js').read_text()
mutations=[('before-cell-reads-after','JSON.stringify(item.before,null,2)','JSON.stringify(item.after,null,2)'),
           ('reason-cell-null','cell(row,item.reason === null ? "无" : item.reason,item.reason !== null && item.reason.length > 80);','cell(row,"无");')]
reports=[]
for name,old,new in mutations:
    assert source.count(old)==1
    with tempfile.TemporaryDirectory(prefix='audit-review-mutation-') as directory:
        temporary=Path(directory)
        (temporary/'booking_app/static').mkdir(parents=True);(temporary/'tests').mkdir()
        (temporary/'booking_app/static/audit.js').write_text(source.replace(old,new))
        shutil.copyfile(ROOT/'tests/test_audit_js.cjs',temporary/'tests/test_audit_js.cjs')
        command=['node','--test','--test-reporter=tap','--test-name-pattern=^audit distinct update cancellation revocation bind every full field to its own cell$',str(temporary/'tests/test_audit_js.cjs')]
        run=subprocess.run(command,capture_output=True,text=True,timeout=30)
        log=run.stdout+run.stderr
        (output/(name+'-mutation.log')).write_text(log)
        assert run.returncode!=0 and '# fail 1' in log and 'not ok' in log
        reports.append(dict(mutation=name,application_source_changed=False,mutation_rejected=True,
                            exit_code=run.returncode,expected_failed_test='audit distinct update cancellation revocation bind every full field to its own cell'))
(output/'js-mutations.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(reports))

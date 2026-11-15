"""Real browser student → supervisor → schedule flow, using production Clock."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from booking_app import ROOT,db
from booking_app.domain import SystemClock
from scripts.init_demo import seed_users
from scripts.verify_supervised_booking_http import users,counts
from scripts.verify_audit_http import LiveServer,source_hashes
from scripts.verify_history_browser import browser_wrapper,run_driver
from scripts.verify_availability_performance import Client,write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'docs/evidence/story-4.2/browser')
    parser.add_argument('--playwright-root',type=Path,default=ROOT/'work/browser-tools/node_modules')
    parser.add_argument('--browser-executable',type=Path)
    args=parser.parse_args();output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    write_json(output/'result.json',dict(result='INCOMPLETE'));fingerprints=source_hashes()
    with tempfile.TemporaryDirectory(prefix='supervised-browser-') as directory:
        temporary=Path(directory);database=temporary/'test.db';identities=users();seed_users(database,identities,SystemClock())
        credentials=temporary/'credentials.json';credentials.touch(mode=0o600);credentials.write_text(json.dumps(dict(users=identities)))
        env=dict(os.environ,NODE_PATH=str(args.playwright_root.resolve()))
        executable=args.browser_executable or Path(subprocess.check_output(['node','-e','process.stdout.write(require("playwright").chromium.executablePath())'],env=env,text=True))
        wrapper,registry=browser_wrapper(temporary,executable.resolve());server=LiveServer(database,temporary)
        try:
            server.start();admin=Client(server.origin);admin.login(next(u for u in identities if u['role']=='admin'))
            assert admin.request('/api/admin/rooms',dict(name='浏览器审批室',location='合成测试地点',capacity=20))[0]==201
            result=run_driver(['node',str(ROOT/'scripts/verify_supervised_booking_browser.cjs'),server.origin,str(credentials),str(output),str(wrapper)],env,registry,timeout=180)
            if result.returncode:
                write_json(output/'failure.json',dict(result='FAIL',stderr=result.stderr[-3000:]))
                raise RuntimeError('Browser approval verification failed; see failure.json')
            report=json.loads(result.stdout);assert report['result']=='PASS'
            report.update(clock='production SystemClock',schema_version=db.SCHEMA_VERSION,database_counts=counts(database))
        finally:
            server.stop();write_json(output/'process-cleanup.json',dict(server_pids=server.pids,browser_groups=registry.read_text().splitlines(),completed=True))
    assert fingerprints==source_hashes();report['source_sha256']=fingerprints;write_json(output/'result.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},ensure_ascii=False))

if __name__=='__main__':main()

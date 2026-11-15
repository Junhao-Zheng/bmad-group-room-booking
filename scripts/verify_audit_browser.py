"""Run real audit UI checks at desktop/mobile sizes using private temporary data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from booking_app import ROOT
from booking_app.domain import SystemClock
from tests.legacy_fixture import DEMO_IDENTITIES,seed_users
from scripts.verify_audit_http import LiveServer,populate,facts,evidence_facts,source_hashes
from scripts.verify_availability_performance import environment,write_json
from scripts.verify_history_browser import browser_wrapper,run_driver,environment_metadata


def resolve_browser_executable(args, env):
    if args.browser_executable is not None:
        return args.browser_executable.resolve()
    resolved = subprocess.run(['node', '-e', 'process.stdout.write(require("playwright").chromium.executablePath())'],
        env=env, cwd=ROOT, capture_output=True, text=True, check=True, timeout=10, start_new_session=True)
    return Path(resolved.stdout).resolve()


def run(args,output,meta):
    with tempfile.TemporaryDirectory(prefix='audit-browser-') as directory:
        temporary=Path(directory);database=temporary/'test.sqlite3'
        users=[dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24)) for u,d,r in DEMO_IDENTITIES]
        credentials=temporary/'credentials.json';credentials.touch(mode=0o600);credentials.write_text(json.dumps(dict(users=users)))
        seed_users(database,users,SystemClock());server=LiveServer(database,temporary)
        env=dict(os.environ,NODE_PATH=str(args.playwright_root.resolve()))
        wrapper,registry=browser_wrapper(temporary,resolve_browser_executable(args,env))
        try:
            server.start();populate(server,users,output);before=facts(database)
            write_json(output/'environment.json',environment(server,meta)|dict(server_start=server.command,browser=environment_metadata(args),
                clock='production SystemClock',fixed_clock_injection=False,database_path=str(database),schema_version=2,
                invocation=[sys.executable,'-m','scripts.verify_audit_browser',*sys.argv[1:]]))
            result=run_driver(['node',str(ROOT/'scripts/verify_audit_browser.cjs'),server.origin,str(credentials),str(output),str(wrapper)],env,registry,timeout=120)
            if result.returncode:raise RuntimeError('Browser verification failed; see safe failure.json')
            report=json.loads(result.stdout);assert report['result']=='PASS'
            after=facts(database);write_json(output/'database-facts.json',dict(before=evidence_facts(before),after=evidence_facts(after)));assert before==after
        finally:
            server.stop();write_json(output/'process-cleanup.json',dict(server_pids=server.pids,browser_groups=[int(x) for x in registry.read_text().splitlines()],completed=True))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'docs/evidence/story-3.4/browser')
    parser.add_argument('--browser-executable',type=Path,help='Optional existing Chrome/Chromium; defaults to Playwright Chromium')
    parser.add_argument('--playwright-root',type=Path,default=ROOT/'work/browser-tools/node_modules')
    args=parser.parse_args(argv);args.output_dir.mkdir(parents=True,exist_ok=True)
    meta=dict(run_id=secrets.token_hex(16),started_at_utc=datetime.now(timezone.utc).isoformat());output=args.output_dir/'runs'/meta['run_id'];output.mkdir(parents=True)
    meta['artifact_directory']='runs/'+meta['run_id'];target=args.output_dir/'result.json';write_json(target,meta|dict(result='INCOMPLETE',completed=False))
    try:
        meta['source_sha256']=source_hashes();report=run(args,output,meta);meta['source_sha256_after']=source_hashes();assert meta['source_sha256']==meta['source_sha256_after']
        report=meta|report|dict(finished_at_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        report=meta|dict(result='INCOMPLETE',completed=False,error_type=type(error).__name__)
        write_json(output/'result.json',report);write_json(target,report);raise
    write_json(output/'result.json',report);write_json(target,report);print(json.dumps({k:v for k,v in report.items() if not k.startswith('source_')}));return 0

if __name__=='__main__':raise SystemExit(main())

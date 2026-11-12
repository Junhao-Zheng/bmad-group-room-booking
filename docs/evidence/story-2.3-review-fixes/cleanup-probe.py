"""Reproduce real Chrome cleanup after killed/timed-out Node; no application data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.verify_history_browser import browser_wrapper, run_driver, stop_process_group


def processes():
    return {int(pid): dict(group=int(group), state=state)
            for line in subprocess.check_output(['ps','-axo','pid=,pgid=,state='],text=True).splitlines()
            for pid,group,state in [line.split()]}


def main():
    executable = Path(sys.argv[1]).resolve()
    reports = []
    sentinel = subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    try:
        for mode in ['node_killed','node_timeout']:
            with tempfile.TemporaryDirectory(prefix='grb-real-cleanup-') as directory:
                work = Path(directory)
                wrapper, registry = browser_wrapper(work, executable)
                observed = work / 'observed.json'
                driver = work / 'probe.cjs'
                driver.write_text('''const {chromium}=require('playwright');
const fs=require('node:fs'),{execFileSync}=require('node:child_process');
(async()=>{
  process.on('SIGTERM',()=>{});
  const browser=await chromium.launch({headless:true,executablePath:process.argv[2],handleSIGTERM:false,handleSIGINT:false,handleSIGHUP:false});
  await browser.newPage();
  const groups=fs.readFileSync(process.argv[3],'utf8').trim().split('\\n').map(Number);
  const rows=execFileSync('ps',['-axo','pid=,ppid=,pgid=,state='],{encoding:'utf8'}).trim().split('\\n').map(line=>line.trim().split(/\\s+/));
  const owned=new Set([process.pid,...groups]);
  let changed=true;
  while(changed){changed=false;for(const [pid,ppid,pgid] of rows){if((owned.has(Number(ppid))||groups.includes(Number(pgid)))&&!owned.has(Number(pid))){owned.add(Number(pid));changed=true;}}}
  fs.writeFileSync(process.argv[4],JSON.stringify({node_pid:process.pid,groups,observed_pids:[...owned],browser_version:browser.version()}));
  if(process.argv[5]==='node_killed')process.kill(process.pid,'SIGKILL');
  else await new Promise(()=>{});
})().catch(()=>process.exit(18));
''')
                env = dict(os.environ,NODE_PATH=str(ROOT/'work/browser-tools/node_modules'))
                try:
                    result = run_driver(['node',str(driver),str(wrapper),str(registry),str(observed),mode],env,registry,timeout=4)
                    assert mode == 'node_killed' and result.returncode == -9
                except subprocess.TimeoutExpired:
                    assert mode == 'node_timeout'
                facts = json.loads(observed.read_text())
                current = processes()
                remaining = [pid for pid in facts['observed_pids'] if pid in current and not current[pid]['state'].startswith('Z')]
                assert remaining == [], remaining
                assert sentinel.poll() is None
                reports.append(dict(mode=mode,**facts,remaining_live_pids=remaining,unrelated_process_survived=True,result='PASS'))
    finally: stop_process_group(sentinel.pid,sentinel,grace=.05)
    output = {'result':'PASS','supported_environment':'macOS/Linux POSIX; actual macOS Chrome exercised', 'scenarios':reports}
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

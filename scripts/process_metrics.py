"""Summarize measured implementation calls; shared rework is counted once globally."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent.parent
if not (ROOT/'docs/evidence').is_dir():ROOT=ROOT/'outputs/group-room-booking'
S1={'1-1-account-access','1-2-room-schedule','1-3-availability','2-1-create-booking','2-2-replay-intent','2-3-personal-history','2-4-member-cancel'}

def report(rows,rework_events):
 assert len({r['story'] for r in rows})==len(rows),'one initial measurement per story required'
 completed=[r for r in rows if r['result']=='PASS'];ids={r['story'] for r in completed};n=len(completed)
 latest={event['work_id']:event for event in rework_events}
 related=[event for event in latest.values() if ids.intersection(event['stories'])]
 finished=[event for event in related if event.get('event')=='completed' and event.get('result')=='PASS']
 integration={}
 for r in completed:
  for item in r.get('shared_pre_done_integration',[]):
   if item['work_id'] in integration:assert integration[item['work_id']]==item,'shared integration metadata must agree'
   integration[item['work_id']]=item
 integration_passes=sum(x['root_implementation_passes'] for x in integration.values())
 integration_participations=sum(x['root_implementation_passes']*len(ids.intersection(x['stories'])) for x in integration.values())
 initial_calls=sum(r['implementation_rounds'] for r in completed)
 extra_unique_calls=sum(event['implementation_calls'] for event in finished)
 extra_participations=sum(event['implementation_calls']*len(ids.intersection(event['stories'])) for event in finished)
 reworked={s for event in related for s in event['stories']} & ids
 return {'initially_accepted_stories':n,'initial_implementation_calls':initial_calls,
  'post_done_unique_implementation_calls_completed':extra_unique_calls,
  'post_done_root_implementation_passes':sum(e.get('root_implementation_passes',0) for e in finished),
  'pre_done_shared_root_integration_passes':integration_passes,
  'initial_calls_plus_rework_calls_and_root_passes':initial_calls+extra_unique_calls+sum(e.get('root_implementation_passes',0) for e in finished)+integration_passes,
  'total_unique_implementation_calls_completed':initial_calls+extra_unique_calls,
  'story_implementation_participations_completed':initial_calls+extra_participations,
  'story_root_pass_participations':sum(e.get('root_implementation_passes',0)*len(ids.intersection(e['stories'])) for e in finished)+integration_participations,
  'implementation_participations_per_story':(initial_calls+extra_participations)/n if n else None,
  'first_review_pass_stories':sum(r['initial_review_pass'] for r in completed),
  'first_review_pass_rate':sum(r['initial_review_pass'] for r in completed)/n if n else None,
  'initial_context_story_rule_pairs':sum(len(set(r['initial_context_rules_violated'])) for r in completed),
  'initial_distinct_context_rule_ids':sorted(set(x for r in completed for x in r['initial_context_rules_violated'])),
  'initial_adr_story_conflict_pairs':sum(len(set(r['initial_adr_conflicts'])) for r in completed),
  'initial_distinct_adr_ids':sorted(set(x for r in completed for x in r['initial_adr_conflicts'])),
  'post_done_rework_stories':sorted(reworked | {r['story'] for r in completed if r['post_done_rework']}),
  'post_done_rework_count':len(reworked | {r['story'] for r in completed if r['post_done_rework']}),
  'unfinished_rework_ids':[e['work_id'] for e in related if e not in finished],
  'initial_review_contexts':sum(r['review_contexts'] for r in completed),
  'review_transport_failures':sum(r.get('review_transport_failures',0) for r in completed)+sum(e.get('review_transport_failures',0) for e in finished),
  'implementation_transport_failures':sum(r.get('implementation_transport_failures',0) for r in completed)+sum(e.get('implementation_transport_failures',0) for e in finished)}

if __name__=='__main__':
 rows=[json.loads(x) for x in (ROOT/'docs/evidence/build-metrics.jsonl').read_text().splitlines() if x.strip()]
 p=ROOT/'docs/evidence/post-done-rework.jsonl';rew=[json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
 status=(ROOT/'_bmad-output/implementation-artifacts/sprint-status.yaml').read_text()
 current=dict(re.findall(r'^  (\d-\d-[\w-]+): (\S+)$',status,re.M))
 print(json.dumps({'all':report(rows,rew),'sprint_1':report([r for r in rows if r['story'] in S1],rew),
 'sprint_2':report([r for r in rows if r['story'] not in S1],rew),'current_story_status':current,
 'note':'初始验收与当前状态分开。共享返工调用全局只计一次，逐故事参与次数按涉及故事分别计；两者不可混用。进行中的返工次数尚未并入已完成调用。测试计数是各次全量规模，不能跨故事相加。'},ensure_ascii=False,indent=2))

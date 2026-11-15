"""Production-clock HTTP approval verification against a private temporary database."""
import argparse
from datetime import datetime,timedelta
import json
from pathlib import Path
import secrets
import tempfile
from zoneinfo import ZoneInfo
from booking_app import ROOT,db
from booking_app.domain import SystemClock
from scripts.init_demo import DEMO_IDENTITIES,DEMO_SUPERVISORS,seed_users
from scripts.verify_audit_http import LiveServer,source_hashes
from scripts.verify_availability_performance import Client,write_json


def users():
    return [dict(username=u,display_name=d,role=r,password=secrets.token_urlsafe(24),supervisor_username=DEMO_SUPERVISORS.get(u)) for u,d,r in DEMO_IDENTITIES]


def counts(database):
    with db.read_transaction(database) as conn:
        assert [r[0] for r in conn.execute('PRAGMA integrity_check')]==['ok']
        assert not list(conn.execute('PRAGMA foreign_key_check'))
        return {table:conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('applications','application_occurrences','reservations','occupancy_slots','booking_supervisors','audit_events')}


def run(output):
    fingerprints=source_hashes();steps=[]
    with tempfile.TemporaryDirectory(prefix='supervised-http-') as directory:
        temporary=Path(directory);database=temporary/'test.db';identities=users();seed_users(database,identities,SystemClock())
        server=LiveServer(database,temporary)
        try:
            server.start();clients={}
            for user in identities:
                client=Client(server.origin);client.login(user);clients[user['username']]=client
            def call(who,path,payload=None,status=200):
                code,body,_=clients[who].request(path,payload)
                steps.append(dict(path=path,actor=who,status=code,expected=status,response=body));write_json(output/'operations.json',steps)
                assert code==status,(path,code,status)
                return body.get('data')
            student='demo_member_a';teacher='demo_teacher_a';other='demo_teacher_b';admin='demo_admin'
            room=call(admin,'/api/admin/rooms',dict(name='审批测试室',location='合成地点',capacity=12),201)
            day=(datetime.now(ZoneInfo('Asia/Shanghai'))+timedelta(days=1)).date()
            payload=dict(room_id=room['id'],title='审批端到端测试',purpose='私有研究讨论',attendees=3,start=f'{day}T10:00',end=f'{day}T11:00',intent_key=secrets.token_hex(16))
            item=call(student,'/api/applications',payload,201)['application'];before=counts(database)
            assert before['reservations']==before['occupancy_slots']==0
            call(other,f"/api/applications/{item['id']}",status=404)
            call(other,f"/api/applications/{item['id']}/approve",{},404)
            call(admin,f"/api/applications/{item['id']}/approve",{},403)
            call(student,'/api/bookings',payload,403)
            approved=call(teacher,f"/api/applications/{item['id']}/approve",{})
            after=counts(database);assert after['reservations']==1 and after['occupancy_slots']==2
            call(student,f"/api/bookings/{approved['reservation_id']}/cancel",{},403)
            schedule=call(other,f'/api/schedule?room_id={room["id"]}&date={day}')
            record=schedule['items'][0]['record'];assert record['supervisor_display_name']==item['supervisor_display_name'];assert 'purpose' not in record and 'supervisor_id' not in record
            call(other,f"/api/bookings/{approved['reservation_id']}",status=404)
            server.stop();server.start()
            replay=call(student,'/api/applications',payload)['application'];assert replay==approved
            assert call(teacher,f"/api/applications/{item['id']}/approve",{})==approved
            assert counts(database)==after
            report=dict(result='PASS',clock='production SystemClock',schema_version=db.SCHEMA_VERSION,steps=len(steps),before_approval=before,after_approval=after,restart_replay_preserved=True)
        finally:server.stop()
    assert fingerprints==source_hashes()
    report['source_sha256']=fingerprints;write_json(output/'result.json',report);return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,default=ROOT/'docs/evidence/story-4.2/http');args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    write_json(args.output_dir/'result.json',dict(result='INCOMPLETE'))
    report=run(args.output_dir);print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},ensure_ascii=False))

if __name__=='__main__':main()

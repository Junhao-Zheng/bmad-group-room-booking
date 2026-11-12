"""Story 2.5: twenty independent HTTP member/admin races, storage and fault oracles."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading

from booking_app import ROOT, create_app, db
from booking_app.audit import audit_writer
from scripts.init_demo import seed_users
from scripts.verify_availability_performance import Client, Server, environment, write_json
from scripts.verify_create_booking_http import FixedClock
from scripts.verify_history_browser import facts
from tests.history_fixtures import FULL_KEYS
from tests.schedule_fixtures import NOW


def server_main(database, port, fault):
    from waitress import serve
    def writer(conn, event):
        if fault == 'before': raise RuntimeError('synthetic private audit fault')
        audit_writer(conn, event)
        if fault == 'after': raise RuntimeError('synthetic private audit fault')
        if fault == 'commit':
            conn.set_authorizer(lambda action, first, *_: sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_TRANSACTION and first == 'COMMIT' else sqlite3.SQLITE_OK)
    config = {'TESTING': True, 'DATABASE': database, 'CLOCK': FixedClock(),
              'APP_ORIGIN': f'http://127.0.0.1:{port}', 'TRUSTED_HOSTS': ['127.0.0.1']}
    if fault: config['AUDIT_WRITER'] = writer
    serve(create_app(config), host='127.0.0.1', port=port, threads=8)


class CancelServer(Server):
    def __init__(self, database, fault=None):
        super().__init__(database)
        self.process = multiprocessing.get_context('spawn').Process(target=server_main, args=(str(database), self.port, fault))


def checked_storage(database):
    value = facts(database)
    with db.read_transaction(database) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    for record in value['reservations']:
        slots = sorted(s['slot_start'] for s in value['occupancy_slots'] if s['reservation_id'] == record['id'])
        assert slots == ([] if record['cancelled_at'] is not None else list(range(record['start_at'], record['end_at'], 1800)))
        events = [a for a in value['audit_events'] if a['target_type'] == 'booking' and a['target_id'] == record['id']]
        assert sum(a['action'] == 'booking.created' for a in events) == 1
        cancelled = [a for a in events if a['action'] in ('booking.cancelled_by_member', 'booking.cancelled_by_admin')]
        assert len(cancelled) == int(record['cancelled_at'] is not None)
        if cancelled:
            event = cancelled[0]
            assert event['actor_id'] == record['cancelled_by'] and event['occurred_at'] == record['cancelled_at'] == NOW
            before = dict(id=record['id'], room_id=record['room_id'], owner_id=record['user_id'], title=record['title'],
                purpose=record['purpose'], attendees=record['attendees'], start_at=record['start_at'], end_at=record['end_at'],
                created_at=record['created_at'], cancelled_at=None, cancelled_by_id=None, cancel_reason=None)
            assert json.loads(event['before_json']) == before
            assert json.loads(event['after_json']) == before | dict(cancelled_at=NOW, cancelled_by_id=record['cancelled_by'], cancel_reason=record['cancel_reason'])
            assert event['reason'] == record['cancel_reason']
            if event['action'] == 'booking.cancelled_by_member': assert record['cancelled_by'] == record['user_id'] and record['cancel_reason'] is None
            else:
                assert record['cancel_reason'] in {2: {'HTTP 合成管理原因', '管理员甲的独立原因'},
                                                    4: {'管理员乙的不同原因'}}[record['cancelled_by']]
    return value


def fingerprints():
    helpers = ('scripts/init_demo.py', 'scripts/verify_availability_performance.py',
               'scripts/verify_create_booking_http.py', 'scripts/verify_history_browser.py',
               'scripts/verify_auth_browser.py', 'tests/__init__.py',
               'tests/history_fixtures.py', 'tests/schedule_fixtures.py')
    files = list((ROOT / 'booking_app').rglob('*')) + [Path(__file__), *(ROOT / name for name in helpers)]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)
            if p.is_file() and p.suffix in {'.py', '.sql', '.js', '.html', '.css'}}


def run(output, meta):
    steps = []; rounds = []
    def capture(client, phase, path, payload):
        status, body, elapsed = client.request(path, payload)
        steps.append(dict(phase=phase, path=path, http_status=status, response=body, duration_ms=elapsed))
        write_json(output / 'http-steps.json', steps)
        return status, body
    with tempfile.TemporaryDirectory(prefix='grb-admin-cancel-http-') as directory:
        database = Path(directory) / 'test.sqlite3'
        users = [dict(username='race_member', display_name='合成成员', role='member', password=secrets.token_urlsafe(24)),
                 dict(username='race_admin', display_name='合成管理员', role='admin', password=secrets.token_urlsafe(24))]
        rival = dict(username='rival_admin', display_name='合成管理员乙', role='admin', password=secrets.token_urlsafe(24))
        seed_users(database, users + [dict(username='other_member', display_name='合成成员乙', role='member',
                                         password=secrets.token_urlsafe(24)), rival], FixedClock())
        with db.write_transaction(database) as conn:
            conn.execute("INSERT INTO rooms VALUES(1,'合成会议室','合成测试楼',20,?,?)", (NOW, NOW))
        payload = dict(room_id=1, title='合成竞争预约', purpose='合成用途', attendees=5,
                       start='2026-11-12T12:00', end='2026-11-12T14:00')
        server = CancelServer(database)
        try:
            server.start()
            write_json(output / 'environment.json', environment(server, meta) | dict(fixed_now=NOW, threads=8,
                server_start='spawn scripts.verify_admin_cancel_http.server_main; Waitress 8 threads',
                invocation=['.venv/bin/python', '-m', 'scripts.verify_admin_cancel_http', '--output-dir', str(output)]))
            for index in range(20):
                clients = [Client(server.origin), Client(server.origin)]
                for client, user in zip(clients, users): client.login(user)
                status, body = capture(clients[0], f'create-{index}', '/api/bookings', payload | dict(intent_key=f'admin-cancel-race-{index:03}'))
                assert status == 201
                booking_id = body['data']['booking']['id']; before = checked_storage(database)
                write_json(output / f'round-{index:02}-before.json', before)
                barrier = threading.Barrier(2)
                def cancel(which):
                    path = f'/api/{"admin/" if which else ""}bookings/{booking_id}/cancel'
                    try:
                        barrier.wait(timeout=30)
                        status, body, elapsed = clients[which].request(path, {'reason': ' HTTP 合成管理原因 '} if which else {})
                        return dict(actor='admin' if which else 'member', http_status=status, response=body, duration_ms=elapsed)
                    except Exception as error:
                        return dict(actor='admin' if which else 'member', http_status=None, error_type=type(error).__name__)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(cancel, [0, 1]))
                after = facts(database)
                row = dict(round=index, booking_id=booking_id, responses=responses, storage=after)
                rounds.append(row); write_json(output / 'race-rounds.json', rounds)
                assert [r['http_status'] for r in responses] == [200, 200]
                winner = responses[0]['response']['data']
                assert responses[1]['response']['data'] == winner and set(winner) == FULL_KEYS
                assert winner['status'] == 'cancelled'
                assert (winner['cancelled_by_id'], winner['cancel_reason']) in [(1, None), (2, 'HTTP 合成管理原因')]
                checked_storage(database)
                record = next(r for r in after['reservations'] if r['id'] == booking_id)
                original = next(r for r in before['reservations'] if r['id'] == booking_id)
                assert record == original | dict(cancelled_at=NOW, cancelled_by=winner['cancelled_by_id'], cancel_reason=winner['cancel_reason'])
                assert after['occupancy_slots'] == [s for s in before['occupancy_slots'] if s['reservation_id'] != booking_id]
            # Keep unrelated live occupancy while two different administrators race.
            status, _ = capture(clients[0], 'unrelated-booking', '/api/bookings', payload | dict(
                start='2026-11-12T14:00', end='2026-11-12T15:00', intent_key='admin-admin-unrelated'))
            assert status == 201
            status, body = capture(clients[0], 'admin-race-target', '/api/bookings', payload | dict(intent_key='admin-admin-race-target'))
            assert status == 201
            admin_target = body['data']['booking']['id']; before = checked_storage(database)
            write_json(output / 'admin-race-before.json', before)
            admins = [Client(server.origin), Client(server.origin)]
            for client, user in zip(admins, [users[1], rival]): client.login(user)
            barrier = threading.Barrier(2)
            reasons = ['管理员甲的独立原因', '管理员乙的不同原因']
            def admin_cancel(index):
                try:
                    barrier.wait(timeout=30)
                    status, body, elapsed = admins[index].request(f'/api/admin/bookings/{admin_target}/cancel', {'reason': reasons[index]})
                    return dict(actor_id=[2, 4][index], submitted_reason=reasons[index], http_status=status, response=body, duration_ms=elapsed)
                except Exception as error:
                    return dict(actor_id=[2, 4][index], http_status=None, error_type=type(error).__name__)
            with ThreadPoolExecutor(max_workers=2) as pool:
                admin_responses = list(pool.map(admin_cancel, [0, 1]))
            after = facts(database)
            write_json(output / 'admin-race-result.json', dict(booking_id=admin_target, responses=admin_responses, storage=after))
            assert [r['http_status'] for r in admin_responses] == [200, 200]
            winner = admin_responses[0]['response']['data']
            assert winner == admin_responses[1]['response']['data'] and set(winner) == FULL_KEYS
            assert (winner['cancelled_by_id'], winner['cancel_reason']) in [(2, reasons[0]), (4, reasons[1])]
            assert winner['cancelled_at'] == NOW
            assert after['reservations'] == [row | dict(cancelled_at=NOW, cancelled_by=winner['cancelled_by_id'], cancel_reason=winner['cancel_reason'])
                if row['id'] == admin_target else row for row in before['reservations']]
            assert after['occupancy_slots'] == [slot for slot in before['occupancy_slots'] if slot['reservation_id'] != admin_target]
            assert after['occupancy_slots']  # Unrelated active occupancy really was preserved.
            assert after['audit_events'][:-1] == before['audit_events'] and len(after['audit_events']) == len(before['audit_events']) + 1
            event = after['audit_events'][-1]
            assert (event['action'], event['target_id'], event['actor_id'], event['occurred_at'], event['reason']) == (
                'booking.cancelled_by_admin', admin_target, winner['cancelled_by_id'], NOW, winner['cancel_reason'])
            checked_storage(database)
            status, body = capture(clients[0], 'fault-target', '/api/bookings', payload | dict(intent_key='admin-cancel-fault-target'))
            assert status == 201
            fault_id = body['data']['booking']['id']; saved = checked_storage(database)
            write_json(output / 'before-fault.json', saved)
        finally: server.stop()
        for phase in ['before', 'after', 'commit']:
            server = CancelServer(database, phase)
            try:
                server.start(); client = Client(server.origin); client.login(users[1])
                assert checked_storage(database) == saved
                status, body = capture(client, f'fault-{phase}', f'/api/admin/bookings/{fault_id}/cancel', {'reason': 'HTTP 合成管理原因'})
                assert status == 500 and body['error']['code'] == 'INTERNAL_ERROR'
                observed = facts(database); write_json(output / f'after-fault-{phase}.json', observed)
                assert observed == saved; checked_storage(database)
                status, repeated = capture(client, f'repeat-with-{phase}-writer', f'/api/admin/bookings/{rounds[0]["booking_id"]}/cancel', {'reason': '重复合法原因'})
                assert status == 200 and repeated['data'] == rounds[0]['responses'][0]['response']['data']
            finally: server.stop()
        server = CancelServer(database)
        try:
            server.start(); client = Client(server.origin); client.login(users[1])
            assert checked_storage(database) == saved
            status, result = capture(client, 'cancel-after-restart', f'/api/admin/bookings/{fault_id}/cancel', {'reason': 'HTTP 合成管理原因'})
            assert status == 200
            member = Client(server.origin); member.login(users[0])
            status, result = capture(member, 'replay-old-cancelled-intent', '/api/bookings', payload | dict(intent_key='admin-cancel-fault-target'))
            assert status == 200 and result['data']['replayed'] and result['data']['booking']['status'] == 'cancelled'
            final = checked_storage(database); write_json(output / 'final-storage.json', final)
            assert len(final['reservations']) == 23 and len(final['occupancy_slots']) == 2 and len(final['audit_events']) == 45
        finally: server.stop()
    return dict(result='PASS', completed=True, rounds=20, independent_race_sessions=40, http_200=40,
                transitions_per_round=1, response_facts_agree=True, full_storage_oracle=True,
                writer_before_after_and_commit_rollback=True, restart_persistence=True, repeat_writer_calls=0,
                admin_admin_races=1, admin_admin_http_200=2, admin_admin_first_facts_agree=True,
                admin_admin_unrelated_storage_unchanged=True,
                race_winners={role: sum(r['responses'][0]['response']['data']['cancelled_by_id'] == actor for r in rounds)
                              for role, actor in [('member', 1), ('admin', 2)]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/admin-cancel-http')
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)
    meta = dict(run_id=secrets.token_hex(16), started_at_utc=datetime.now(timezone.utc).isoformat())
    target = args.output_dir / 'http-result.json'; output = args.output_dir / 'runs' / meta['run_id']; output.mkdir(parents=True)
    meta['artifact_directory'] = 'runs/' + meta['run_id']; meta['source_sha256'] = fingerprints()
    write_json(target, meta | dict(result='INCOMPLETE', completed=False))
    try:
        report = run(output, meta)
        assert fingerprints() == meta['source_sha256'], 'Sources changed during run'
        write_json(target, meta | report | dict(finished_at_utc=datetime.now(timezone.utc).isoformat()))
    except BaseException as error:
        write_json(target, meta | dict(result='INCOMPLETE', completed=False, error_type=type(error).__name__)); raise
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

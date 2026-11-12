"""Story 2.2 acceptance: current facts, authentication, normalization and no mutation."""
from contextlib import contextmanager
from dataclasses import replace
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, services
from booking_app.domain import DomainError
from tests import test_create_booking as creation
from tests.schedule_fixtures import NOW, epoch


# Reuse only fixture/helpers. Do not inherit the existing test class or its tests.
class ReplayIntentTests(unittest.TestCase):
    setUpClass = classmethod(creation.CreateBookingTests.setUpClass.__func__)
    tearDownClass = classmethod(creation.CreateBookingTests.tearDownClass.__func__)
    setUp = creation.CreateBookingTests.setUp
    login = creation.CreateBookingTests.login
    payload = creation.CreateBookingTests.payload
    post = creation.CreateBookingTests.post
    error = creation.CreateBookingTests.error
    counts = creation.CreateBookingTests.counts
    actor = creation.CreateBookingTests.actor

    def facts(self):
        with db.read_transaction(self.database) as conn:
            return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
                    for table in ('reservations', 'occupancy_slots', 'audit_events')}

    def replay(self, expected, **changes):
        before = self.facts()
        with patch.dict(self.app.config, AUDIT_WRITER=lambda *_: self.fail('Replay must not call writer')):
            response = self.post(**changes)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json), {'ok', 'data'})
        self.assertEqual(set(response.json['data']), {'booking', 'replayed'})
        self.assertIs(response.json['data']['replayed'], True)
        booking = response.json['data']['booking']
        self.assertEqual(set(booking), creation.FULL_KEYS)
        for name, value in expected.items(): self.assertEqual(booking[name], value)
        self.assertEqual(self.facts(), before)
        return booking

    def test_equivalent_python_whitespace_and_persistent_six_fields(self):
        original = self.post().json['data']['booking']
        whitespace = ''.join(chr(n) for n in range(0x3100) if chr(n).isspace())
        self.replay(original, title=whitespace + original['title'] + whitespace,
                    purpose=whitespace + original['purpose'] + whitespace)
        self.assertEqual(self.counts(), (1, 4, 1))
        # FEFF is material in Python, as are interior whitespace and Unicode normalization.
        for name, value in [('title', '\ufeff' + original['title']), ('purpose', original['purpose'] + ' x'),
                            ('title', original['title'].replace(' ', '  '))]:
            self.error(self.post(**{name: value}), 409, 'IDEMPOTENCY_MISMATCH')

    def test_all_six_material_changes_mismatch_before_new_business_rules(self):
        self.post()
        before = self.facts()
        for changes in [dict(room_id=999), dict(title='different'), dict(purpose='different'),
                        dict(attendees=100000), dict(start='2026-11-12T09:00'),
                        dict(end='2026-12-31T14:00')]:
            self.error(self.post(**changes), 409, 'IDEMPOTENCY_MISMATCH')
        self.assertEqual(self.facts(), before)

    def test_current_started_ended_and_cancelled_facts_with_lower_capacity(self):
        original = self.post().json['data']['booking']
        for now, status in [(epoch('2026-11-12T12:00'), 'in_progress'),
                            (epoch('2026-11-12T14:00'), 'ended')]:
            self.clock.now = now
            self.replay(dict(id=original['id'], status=status))
        # Legal historical fixture: only ended bookings permit lowering capacity.
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE rooms SET capacity=1,name='更名房间',location='新位置',updated_at=? WHERE id=1", (self.clock.now,))
            conn.execute("UPDATE users SET display_name='当前显示名' WHERE id=?", (original['owner_id'],))
        self.replay(dict(id=original['id'], status='ended', owner_display_name='当前显示名',
                         room=dict(id=1, name='更名房间', location='新位置', capacity=1)))
        # Direct fixture models a cancellation that occurred before start; no future API is exposed.
        with db.write_transaction(self.database) as conn:
            conn.execute('UPDATE reservations SET cancelled_at=?,cancelled_by=?,cancel_reason=? WHERE id=?',
                         (NOW + 30, 3, '合成历史取消原因', original['id']))
            conn.execute('DELETE FROM occupancy_slots WHERE reservation_id=?', (original['id'],))
        self.replay(dict(id=original['id'], status='cancelled', cancelled_at=NOW+30,
                         cancelled_by_id=3, cancelled_by_display_name='演示管理员', cancel_reason='合成历史取消原因'))
        self.assertEqual(self.counts(), (1, 0, 1))

    def test_cancelled_record_replays_after_new_booking_reuses_slots(self):
        original = self.post().json['data']['booking']
        with db.write_transaction(self.database) as conn:
            conn.execute('UPDATE reservations SET cancelled_at=?,cancelled_by=user_id WHERE id=?', (NOW+1, original['id']))
            conn.execute('DELETE FROM occupancy_slots WHERE reservation_id=?', (original['id'],))
        self.clock.now = NOW + 1
        self.assertEqual(self.post(intent_key='replacement-intent-01').status_code, 201)
        self.replay(dict(id=original['id'], status='cancelled', cancel_reason=None))
        self.assertEqual(self.counts(), (2, 4, 2))

    def test_same_key_other_user_cannot_replay_or_leak_private_facts(self):
        original = self.post().json['data']['booking']
        self.client = self.app.test_client()
        self.identity = self.login(self.client, 'demo_member_b')
        conflict = self.post()
        self.error(conflict, 409, 'OCCUPANCY_CONFLICT')
        self.assertEqual(set(conflict.json['error']['conflicts'][0]), creation.SHARED_CONFLICT_KEYS)
        self.assertNotIn(original['purpose'], conflict.text)
        new = self.post(room_id=2)
        self.assertEqual(new.status_code, 201)
        self.assertNotEqual(new.json['data']['booking']['id'], original['id'])
        self.assertEqual(new.json['data']['booking']['owner_id'], self.identity['id'])

    def test_failed_validation_and_conflict_do_not_claim_key(self):
        for changes, status, code in [(dict(title=''),400,'INVALID_INPUT'),
                                      (dict(attendees=11),409,'CAPACITY_CONFLICT'),
                                      (dict(room_id=999),404,'NOT_FOUND')]:
            self.error(self.post(**changes),status,code)
            self.assertEqual(self.counts(), (0,0,0))
        self.assertEqual(self.post().status_code,201)
        self.error(self.post(intent_key='failed-conflict-key'),409,'OCCUPANCY_CONFLICT')
        self.assertEqual(self.post(intent_key='failed-conflict-key',room_id=2).status_code,201)

    def test_static_format_rejection_still_precedes_replay(self):
        self.post()
        for changes in [dict(attendees=True),dict(room_id='1'),dict(start='2026-11-12T12:00:00'),
                        dict(title='\x00'),dict(purpose='\ud800')]:
            self.error(self.post(**changes),400,'INVALID_INPUT')
        self.assertEqual(self.counts(),(1,4,1))

    def test_replay_authentication_is_rechecked_after_lock_and_one_clock(self):
        self.post()
        with self.app.app_context():
            actor = self.actor()
            self.clock.calls = 0
            self.assertTrue(services.create_booking(actor,self.payload())['replayed'])
            self.assertEqual(self.clock.calls,1)
            for fake in (replace(actor,id=2),replace(actor,session_token_hash='0'*64)):
                with self.assertRaises(DomainError) as caught: services.create_booking(fake,self.payload())
                self.assertEqual(caught.exception.code,'AUTH_REQUIRED')
        original = db.write_transaction
        @contextmanager
        def expire_after_lock(database=None):
            with original(database) as conn:
                self.clock.now = NOW + auth.SESSION_SECONDS
                yield conn
        with patch.object(db,'write_transaction',expire_after_lock):
            self.error(self.post(),401,'AUTH_REQUIRED')
        self.assertEqual(self.counts(),(1,4,1))

    def test_reconstructed_application_retains_original_intent(self):
        original = self.post().json['data']['booking']
        before = self.facts()
        self.app = create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        self.client = self.app.test_client()
        self.identity = self.login(self.client)
        self.replay(original)
        self.assertEqual(self.facts(),before)

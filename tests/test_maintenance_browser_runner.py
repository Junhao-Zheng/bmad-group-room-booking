"""Focused negative oracles for maintenance browser evidence preservation."""
from copy import deepcopy
import unittest
from scripts.verify_maintenance_block_browser import assert_originals_preserved


class MaintenanceStorageOracleTests(unittest.TestCase):
    def setUp(self):
        self.before = {'rooms': [{'id': 1, 'name': 'original'}],
                       'reservations': [{'id': 10, 'room_id': 1}, {'id': 11, 'room_id': 1}],
                       'occupancy_slots': [{'room_id': 1, 'slot_start': 1800, 'reservation_id': 10},
                                           {'room_id': 1, 'slot_start': 3600, 'reservation_id': 11}],
                       'audit_events': [{'id': 1, 'target_id': 10}]}

    def test_unchanged_originals_with_new_rows_are_allowed(self):
        after = deepcopy(self.before)
        after['reservations'].append({'id': 12, 'room_id': 1})
        after['occupancy_slots'].append({'room_id': 1, 'slot_start': 5400, 'reservation_id': 12})
        assert_originals_preserved(self.before, after)

    def test_deleted_original_record_and_its_slots_cannot_pass(self):
        after = deepcopy(self.before)
        after['reservations'] = after['reservations'][1:]
        after['occupancy_slots'] = after['occupancy_slots'][1:]
        with self.assertRaises(AssertionError):
            assert_originals_preserved(self.before, after)

    def test_original_field_or_slot_changes_cannot_pass(self):
        for table, field, value in [('rooms','name','changed'), ('reservations','room_id',2),
                                    ('audit_events','target_id',11), ('occupancy_slots','slot_start',7200)]:
            with self.subTest(table=table):
                after = deepcopy(self.before); after[table][0][field] = value
                with self.assertRaises(AssertionError):
                    assert_originals_preserved(self.before, after)


if __name__ == '__main__': unittest.main()

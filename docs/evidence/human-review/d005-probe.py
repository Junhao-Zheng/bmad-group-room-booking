"""Synthetic two-representative scope probe; run from repo with PYTHONPATH=."""
import json
from tests.test_create_booking import CreateBookingTests

CreateBookingTests.setUpClass()
case = CreateBookingTests()
try:
    case.setUp()
    first = case.post()
    case.assertEqual(first.status_code, 201)
    before = case.counts()
    case.client = case.app.test_client()
    case.identity = case.login(case.client, 'demo_member_b')
    overlap = case.post(intent_key='second-representative-overlap')
    case.assertEqual(overlap.status_code, 409)
    case.assertEqual(case.counts(), before)
    adjacent = case.post(start='2026-11-12T14:00', end='2026-11-12T15:00', intent_key='second-representative-adjacent')
    case.assertEqual(adjacent.status_code, 201)
    print(json.dumps({'result':'PASS','scope':'synthetic different representative accounts, same room, Flask test client; no real users or rollout', 'first_booking_status':first.status_code, 'other_account_overlap_status':overlap.status_code, 'rejection_preserves_database':True, 'adjacent_booking_status':adjacent.status_code}, ensure_ascii=False, indent=2))
finally:
    case.doCleanups()
    CreateBookingTests.tearDownClass()

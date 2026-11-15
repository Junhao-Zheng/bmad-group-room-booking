# Supervised Cancellation Verification

Implemented and locally verified on 2026-11-15.

- Student cancellation requests persist as `awaiting_approval` and retain occupancy.
- The bound supervisor can approve once; the booking is released once and records the supervisor as the cancellation actor.
- Rejection preserves occupancy and reason; a later request creates a new history record.
- Start-time equality blocks supervisor approval.
- Admin cancellation supersedes an outstanding request in the same transaction.
- Audit writer failures roll back the request, booking, slots, and audit rows together.
- Twenty concurrent approval/admin attempts produce one booking cancellation event and no duplicate release.

Automated command: `.venv/bin/python -m unittest tests.test_supervised_cancellation tests.test_member_cancel tests.test_admin_cancel -q`.

- `location`: `booking_app/static/rooms.js:171`
  `trigger_condition`: A room update commits but its response is lost or malformed; the unknown-result branch clears only the room confirmation.
  `guard_snippet`: Mark the dependent room options stale on an uncertain write outcome, and require a successful refresh before allowing another block submission.
  `potential_consequence`: An already confirmed block remains enabled and can be submitted using outdated room information. A handler probe confirmed that `/api/admin/blocks` is sent without renewed block confirmation after the room request fails.

- `location`: `booking_app/static/rooms.js:145`; `booking_app/static/blocks.js:232`
  `trigger_condition`: The administrator starts a room update, then submits an already confirmed block before the room response arrives.
  `guard_snippet`: Broadcast a room-write-pending state before sending the update and prevent new block submissions until its outcome is resolved; preserve block requests already in flight.
  `potential_consequence`: The new invalidation runs too late when the room update commits before its response arrives. A probe confirmed that both POST requests can be outstanding while the old block confirmation remains valid.

- `location`: `booking_app/static/rooms.js:145`
  `trigger_condition`: “刷新目录” obtains changed room information, but the current page did not perform the update.
  `guard_snippet`: Detect directory changes during `loadRooms()` and propagate invalidation when the newly fetched room information differs from the previous directory.
  `potential_consequence`: The room directory displays the new name while the block form retains its old options and checked confirmation. A probe reproduced this after a successful manual directory refresh.

- `location`: `booking_app/static/blocks.js:116`
  `trigger_condition`: A booking cancellation or block revocation is selected and confirmed before its room is renamed or relocated in the room editor.
  `guard_snippet`: Invalidate cancellation and revocation confirmations and require refreshed target details when their room changes.
  `potential_consequence`: The new listener invalidates only block creation. Destructive actions retain their old room summaries and checked confirmations. A probe confirmed that revocation remained enabled and confirmed after a room save.

- `location`: `booking_app/static/blocks.js:279`
  `trigger_condition`: The directory contains a safe room and another room whose identifier exceeds JavaScript’s safe integer range; saving the safe room sets `roomsStale`.
  `guard_snippet`: Preserve safe room options while explicitly disabling unsupported entries, or provide another recovery path that can clear stale state for validated safe selections.
  `potential_consequence`: Every refresh rejects the complete directory, so block creation for the safe room stays permanently disabled in that page. A probe reproduced the lock after saving and refreshing; the displayed instruction to retry cannot resolve it.

- `location`: `booking_app/static/rooms.js:145`
  `trigger_condition`: An existing room is saved with completely unchanged values.
  `guard_snippet`: Dispatch the change event only when the saved room differs from the editing baseline, while still dispatching it for newly created rooms.
  `potential_consequence`: A successful no-op save incorrectly announces that room information changed, discards a valid block confirmation, and forces another directory request. A probe reproduced this with identical room values.


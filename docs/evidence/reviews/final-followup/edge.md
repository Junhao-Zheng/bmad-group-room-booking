[
  {
    "location": "booking_app/static/rooms.js:171-173",
    "trigger_condition": "Room update commits, but its response is lost while a block remains confirmed.",
    "guard_snippet": "if (!failure.serverError) invalidateBlockRoomOptionsUntilRefresh({reason:\"unknown-room-save\"});",
    "potential_consequence": "Previously confirmed block can submit using room details that may already have changed."
  }
]

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (length(trim(username)) > 0),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('member', 'admin')),
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY NOT NULL CHECK (length(token_hash) = 64),
    user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    csrf_token TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL CHECK (expires_at > created_at)
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80),
    location TEXT NOT NULL CHECK (length(trim(location)) BETWEEN 1 AND 120),
    capacity INTEGER NOT NULL CHECK (typeof(capacity) = 'integer' AND capacity BETWEEN 1 AND 1000),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE (name, location)
);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('booking', 'block')),
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title TEXT,
    purpose TEXT,
    attendees INTEGER,
    reason TEXT,
    start_at INTEGER NOT NULL CHECK (typeof(start_at) = 'integer' AND start_at % 1800 = 0),
    end_at INTEGER NOT NULL CHECK (typeof(end_at) = 'integer' AND end_at % 1800 = 0 AND start_at < end_at),
    intent_key TEXT,
    request_payload TEXT,
    created_at INTEGER NOT NULL,
    cancelled_at INTEGER,
    cancelled_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    cancel_reason TEXT,
    UNIQUE (id, room_id),
    CHECK (
        (kind = 'booking' AND title IS NOT NULL AND length(trim(title)) BETWEEN 1 AND 80
            AND purpose IS NOT NULL AND length(trim(purpose)) BETWEEN 1 AND 500
            AND attendees IS NOT NULL AND typeof(attendees) = 'integer' AND attendees > 0
            AND intent_key IS NOT NULL AND length(intent_key) BETWEEN 16 AND 80
            AND intent_key NOT GLOB '*[^A-Za-z0-9_-]*'
            AND request_payload IS NOT NULL AND reason IS NULL)
        OR
        (kind = 'block' AND title IS NULL AND purpose IS NULL AND attendees IS NULL
            AND intent_key IS NULL AND request_payload IS NULL
            AND reason IS NOT NULL AND length(trim(reason)) BETWEEN 1 AND 500)
    ),
    CHECK (
        (cancelled_at IS NULL AND cancelled_by IS NULL AND cancel_reason IS NULL)
        OR
        (cancelled_at IS NOT NULL AND typeof(cancelled_at) = 'integer' AND cancelled_by IS NOT NULL
            AND (cancel_reason IS NULL OR length(trim(cancel_reason)) BETWEEN 1 AND 500)
            AND (kind = 'booking' OR cancel_reason IS NOT NULL))
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS reservations_user_intent ON reservations(user_id, intent_key) WHERE kind = 'booking';
CREATE INDEX IF NOT EXISTS reservations_user_start ON reservations(user_id, start_at, id);
CREATE INDEX IF NOT EXISTS reservations_room_interval ON reservations(room_id, start_at, end_at);
CREATE INDEX IF NOT EXISTS reservations_kind_cancel_end ON reservations(kind, cancelled_at, end_at);

CREATE TABLE IF NOT EXISTS occupancy_slots (
    room_id INTEGER NOT NULL,
    slot_start INTEGER NOT NULL CHECK (typeof(slot_start) = 'integer' AND slot_start % 1800 = 0),
    reservation_id INTEGER NOT NULL,
    PRIMARY KEY (room_id, slot_start),
    FOREIGN KEY (reservation_id, room_id) REFERENCES reservations(id, room_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS occupancy_slots_reservation ON occupancy_slots(reservation_id);

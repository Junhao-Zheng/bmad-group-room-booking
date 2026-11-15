CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE CHECK (length(trim(username)) > 0),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('member', 'teacher', 'admin')),
    created_at INTEGER NOT NULL,
    supervisor_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    CHECK (supervisor_id IS NULL OR (role = 'member' AND supervisor_id != id))
);

CREATE TRIGGER IF NOT EXISTS users_supervisor_insert BEFORE INSERT ON users
WHEN NEW.supervisor_id IS NOT NULL AND NOT EXISTS
    (SELECT 1 FROM users WHERE id=NEW.supervisor_id AND role='teacher')
BEGIN SELECT RAISE(ABORT, 'Supervisor must be a teacher'); END;

CREATE TRIGGER IF NOT EXISTS users_supervisor_update BEFORE UPDATE OF supervisor_id, role ON users
WHEN NEW.supervisor_id IS NOT NULL AND NOT EXISTS
    (SELECT 1 FROM users WHERE id=NEW.supervisor_id AND role='teacher')
BEGIN SELECT RAISE(ABORT, 'Supervisor must be a teacher'); END;

CREATE TRIGGER IF NOT EXISTS users_teacher_role_update BEFORE UPDATE OF role ON users
WHEN NEW.role != 'teacher' AND EXISTS (SELECT 1 FROM users WHERE supervisor_id=OLD.id)
BEGIN SELECT RAISE(ABORT, 'Referenced teacher role cannot change'); END;

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

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    actor_display_name TEXT NOT NULL CHECK (length(trim(actor_display_name)) > 0),
    action TEXT NOT NULL CHECK (action IN ('room.created','room.updated','booking.created',
        'booking.cancelled_by_member','booking.cancelled_by_supervisor','booking.cancelled_by_admin','block.created','block.revoked',
        'application.created','application.approved','application.rejected','application.withdrawn',
        'cancellation_request.created','cancellation_request.approved',
        'cancellation_request.rejected','cancellation_request.superseded')),
    target_type TEXT NOT NULL CHECK (target_type IN ('room','booking','block','application','cancellation_request')),
    target_id INTEGER NOT NULL CHECK (typeof(target_id) = 'integer' AND target_id > 0),
    occurred_at INTEGER NOT NULL CHECK (typeof(occurred_at) = 'integer'),
    before_json TEXT CHECK (before_json IS NULL OR (json_valid(before_json) AND json_type(before_json) = 'object')),
    after_json TEXT NOT NULL CHECK (json_valid(after_json) AND json_type(after_json) = 'object' AND after_json != '{}'),
    reason TEXT CHECK (reason IS NULL OR length(trim(reason)) BETWEEN 1 AND 500)
);
CREATE INDEX IF NOT EXISTS audit_events_target_time ON audit_events(target_type, occurred_at, id);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    owner_display_name TEXT NOT NULL,
    supervisor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    supervisor_display_name TEXT NOT NULL,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 80),
    purpose TEXT NOT NULL CHECK(length(trim(purpose)) BETWEEN 1 AND 500),
    attendees INTEGER NOT NULL CHECK(typeof(attendees)='integer' AND attendees>0),
    start_at INTEGER NOT NULL CHECK(start_at%1800=0),
    end_at INTEGER NOT NULL CHECK(end_at%1800=0 AND end_at>start_at),
    weeks INTEGER NOT NULL DEFAULT 1 CHECK(weeks=1),
    intent_key TEXT NOT NULL CHECK(length(intent_key) BETWEEN 16 AND 80),
    request_payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('awaiting_approval','approved','rejected','withdrawn')),
    created_at INTEGER NOT NULL,
    decided_at INTEGER,
    decided_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    decision_reason TEXT,
    UNIQUE(owner_id,intent_key),
    CHECK((status='awaiting_approval' AND decided_at IS NULL AND decided_by IS NULL AND decision_reason IS NULL)
       OR (status!='awaiting_approval' AND decided_at IS NOT NULL AND decided_by IS NOT NULL)),
    CHECK(status!='rejected' OR (decision_reason IS NOT NULL AND length(trim(decision_reason)) BETWEEN 1 AND 500))
);
CREATE TABLE IF NOT EXISTS application_occurrences (
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE RESTRICT,
    occurrence INTEGER NOT NULL CHECK(occurrence=1),
    reservation_id INTEGER NOT NULL UNIQUE REFERENCES reservations(id) ON DELETE RESTRICT,
    PRIMARY KEY(application_id,occurrence)
);
CREATE TABLE IF NOT EXISTS booking_supervisors (
    reservation_id INTEGER PRIMARY KEY REFERENCES reservations(id) ON DELETE RESTRICT,
    supervisor_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    supervisor_display_name TEXT,
    source TEXT NOT NULL CHECK(source IN ('teacher','application','admin')),
    CHECK((source='admin' AND supervisor_id IS NULL AND supervisor_display_name IS NULL)
       OR (source!='admin' AND supervisor_id IS NOT NULL AND supervisor_display_name IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS applications_supervisor ON applications(supervisor_id,created_at,id);

CREATE TABLE IF NOT EXISTS cancellation_requests (
    id INTEGER PRIMARY KEY,
    booking_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE RESTRICT,
    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    supervisor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('awaiting_approval','approved','rejected','superseded')),
    decided_at INTEGER,
    decided_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    reason TEXT,
    CHECK((status='awaiting_approval' AND decided_at IS NULL AND decided_by IS NULL AND reason IS NULL)
       OR (status!='awaiting_approval' AND decided_at IS NOT NULL AND decided_by IS NOT NULL)),
    CHECK(status!='rejected' OR (reason IS NOT NULL AND length(trim(reason)) BETWEEN 1 AND 500))
);
CREATE UNIQUE INDEX IF NOT EXISTS cancellation_requests_pending ON cancellation_requests(booking_id) WHERE status='awaiting_approval';
CREATE INDEX IF NOT EXISTS cancellation_requests_supervisor ON cancellation_requests(supervisor_id,created_at,id);

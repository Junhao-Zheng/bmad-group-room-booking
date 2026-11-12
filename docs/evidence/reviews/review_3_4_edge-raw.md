[
  {
    "location": "scripts/backup_db.py:35-38",
    "trigger_condition": "Destination sidecars already exist, including when a sidecar path is the source database.",
    "guard_snippet": "if any(os.path.lexists(str(destination) + suffix) for suffix in ('-wal', '-shm', '-journal')): raise FileExistsError('Destination sidecar exists')",
    "potential_consequence": "Failure cleanup deletes pre-existing files and can delete the source database itself."
  },
  {
    "location": "booking_app/dto.py:20-22",
    "trigger_condition": "An update, cancellation, or revocation audit event has a null before snapshot.",
    "guard_snippet": "if (before is None) != row['action'].endswith('.created'): raise ValueError('Invalid before snapshot')",
    "potential_consequence": "Corrupted history returns success and displays missing prior evidence as a creation."
  }
]

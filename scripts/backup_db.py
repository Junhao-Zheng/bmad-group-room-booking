"""Create a private, checked SQLite backup, including committed WAL content."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from booking_app import default_database


def validate_backup_paths(source, destination):
    """Reserve disjoint SQLite namespaces before either database is opened."""
    source, destination = Path(source).resolve(strict=True), Path(destination).absolute()
    suffixes = ("", "-wal", "-shm", "-journal")
    source_namespace = {Path(str(source) + suffix).resolve() for suffix in suffixes}
    destination_namespace = {Path(str(destination) + suffix).resolve() for suffix in suffixes}
    if not source.is_file() or destination.resolve() in source_namespace:
        raise ValueError("Backup requires a source file and a distinct new destination")
    # SQLite may open/remove these names itself. Reject the whole namespace before
    # creating anything, including dangling symlinks and a source at a sidecar path.
    for suffix in suffixes:
        if os.path.lexists(str(destination) + suffix):
            raise FileExistsError("Backup destination namespace already exists")
    if source_namespace & destination_namespace:
        raise ValueError("Backup source and destination namespaces overlap")
    return source, destination


def backup_database(source, destination):
    source, destination = validate_backup_paths(source, destination)
    # O_EXCL also rejects symlinks and existing files; never truncate a source or backup.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
            with closing(sqlite3.connect(destination)) as target:
                origin.backup(target)
                integrity = [row[0] for row in target.execute("PRAGMA integrity_check")]
                foreign_keys = list(target.execute("PRAGMA foreign_key_check"))
                if integrity != ["ok"] or foreign_keys:
                    raise ValueError("Backup integrity or foreign key check failed")
                version = target.execute("PRAGMA user_version").fetchone()[0]
                # Keep the completed backup self-contained, with no WAL dependency.
                target.execute("PRAGMA journal_mode=DELETE")
        os.chmod(destination, 0o600)
        return dict(source=str(source), destination=str(destination),
                    completed_at_utc=datetime.now(timezone.utc).isoformat(), schema_version=version,
                    integrity_check=integrity, foreign_key_check=foreign_keys, permissions="0600")
    except BaseException:
        destination.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(destination) + suffix).unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", type=Path, default=Path(default_database()))
    args = parser.parse_args(argv)
    try:
        result = backup_database(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Backup failed ({type(error).__name__}); no source data was changed.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

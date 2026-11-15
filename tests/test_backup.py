"""Backup reads committed WAL state and never overwrites source/previous outputs."""
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts.backup_db import backup_database

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.source=Path(self.directory.name)/'source.sqlite3';self.target=Path(self.directory.name)/'backup.sqlite3'
        self.conn=sqlite3.connect(self.source);self.addCleanup(self.conn.close)
        self.conn.executescript('PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0; PRAGMA user_version=1; CREATE TABLE records(id INTEGER PRIMARY KEY, value TEXT); INSERT INTO records VALUES(1,"committed WAL");')
    def test_consistent_wal_backup_private_and_independent(self):
        self.assertTrue(Path(str(self.source)+'-wal').is_file())
        self.conn.execute('INSERT INTO records VALUES(2,"uncommitted")')
        result=backup_database(self.source,self.target)
        self.assertEqual(result['integrity_check'],['ok']);self.assertEqual(result['foreign_key_check'],[]);self.assertEqual(result['schema_version'],1)
        self.assertEqual(self.target.stat().st_mode&0o777,0o600)
        with closing(sqlite3.connect(self.target)) as backup:self.assertEqual(backup.execute('SELECT * FROM records').fetchall(),[(1,'committed WAL')])
        self.assertFalse(Path(str(self.target)+'-wal').exists())
        self.conn.rollback();self.conn.execute('DELETE FROM records');self.conn.commit()
        with closing(sqlite3.connect(self.target)) as backup:self.assertEqual(backup.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_same_existing_symlink_hardlink_and_missing_source_rejected(self):
        before=self.source.read_bytes()
        with self.assertRaises(ValueError):backup_database(self.source,self.source)
        self.target.write_text('preserve')
        with self.assertRaises(FileExistsError):backup_database(self.source,self.target)
        self.assertEqual(self.target.read_text(),'preserve');self.target.unlink()
        self.target.symlink_to(self.source)
        with self.assertRaises(ValueError):backup_database(self.source,self.target)
        self.target.unlink();os.link(self.source,self.target)
        with self.assertRaises(FileExistsError):backup_database(self.source,self.target)
        self.assertEqual(self.source.read_bytes(),before)
        with self.assertRaises(FileNotFoundError):backup_database(self.source.with_name('missing'),self.target.with_name('new'))
        self.assertFalse(self.target.with_name('new').exists())
    def test_foreign_key_failure_removes_partial_output(self):
        self.conn.executescript('CREATE TABLE child(parent REFERENCES records(id)); INSERT INTO child VALUES(99);')
        with self.assertRaises(ValueError):backup_database(self.source,self.target)
        self.assertFalse(self.target.exists());self.assertEqual(self.conn.execute('SELECT * FROM child').fetchall(),[(99,)])

    def test_sidecar_files_and_dangling_symlinks_rejected_before_any_sqlite_open(self):
        for suffix in ('-wal','-shm','-journal'):
            for dangling in (False,True):
                with self.subTest(suffix=suffix,dangling=dangling):
                    collision=Path(str(self.target)+suffix)
                    if dangling:collision.symlink_to('missing-target')
                    else:collision.write_bytes(b'existing sidecar must survive')
                    source_before=self.source.read_bytes()
                    # Both a valid copy and an otherwise failing copy must stop before
                    # SQLite/cleanup can interpret or delete the pre-existing name.
                    for source in (self.source,Path(self.directory.name)/'invalid.sqlite3'):
                        if source!=self.source:source.write_bytes(b'invalid SQLite source')
                        before=source.read_bytes()
                        with patch('scripts.backup_db.sqlite3.connect') as connect:
                            with self.assertRaises(FileExistsError):backup_database(source,self.target)
                            connect.assert_not_called()
                        self.assertEqual(source.read_bytes(),before);self.assertFalse(self.target.exists())
                        self.assertTrue(os.path.lexists(collision))
                        if dangling:self.assertEqual(os.readlink(collision),'missing-target')
                        else:self.assertEqual(collision.read_bytes(),b'existing sidecar must survive')
                    self.assertEqual(self.source.read_bytes(),source_before);collision.unlink()

    def test_source_at_each_destination_sidecar_is_never_deleted(self):
        for suffix in ('-wal','-shm','-journal'):
            for valid in (False,True):
                with self.subTest(suffix=suffix,valid=valid):
                    source=Path(str(self.target)+suffix)
                    source.write_bytes(self.source.read_bytes() if valid else b'invalid SQLite source')
                    before=source.read_bytes()
                    with patch('scripts.backup_db.sqlite3.connect') as connect:
                        with self.assertRaises(FileExistsError):backup_database(source,self.target)
                        connect.assert_not_called()
                    self.assertEqual(source.read_bytes(),before);self.assertFalse(self.target.exists());source.unlink()
    def test_cli_reports_checks_and_failure_nonzero(self):
        run=subprocess.run([sys.executable,'-m','scripts.backup_db','--source',str(self.source),str(self.target)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr);self.assertIn('"schema_version": 1',run.stdout)
        failed=subprocess.run([sys.executable,'-m','scripts.backup_db','--source',str(self.source),str(self.target)],capture_output=True,text=True)
        self.assertEqual(failed.returncode,1);self.assertIn('FileExistsError',failed.stderr)

    def test_source_sidecar_destinations_and_directory_aliases_rejected_before_open(self):
        alias=Path(self.directory.name)/'alias'
        alias.symlink_to(Path(self.directory.name),target_is_directory=True)
        namespace=lambda: {suffix: Path(str(self.source)+suffix).read_bytes()
                           for suffix in ('','-wal','-shm','-journal') if Path(str(self.source)+suffix).exists()}
        before=namespace()
        for folder in (self.source.parent,alias):
            for suffix in ('-wal','-shm','-journal'):
                with self.subTest(folder=folder,suffix=suffix), patch('scripts.backup_db.sqlite3.connect') as connect:
                    with self.assertRaises(ValueError):backup_database(self.source,folder/(self.source.name+suffix))
                    connect.assert_not_called()
                self.assertEqual(namespace(),before)
        backup_database(self.source,self.target)
        with closing(sqlite3.connect(self.target)) as backup:
            self.assertEqual(backup.execute('SELECT * FROM records').fetchall(),[(1,'committed WAL')])

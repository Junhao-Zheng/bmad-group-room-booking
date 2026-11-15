"""Schema 2 identity acceptance, using real temporary schema 1 histories."""
from contextlib import closing
from pathlib import Path
import re
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from booking_app import auth, create_app, db, dto
from scripts.init_demo import seed_users
from scripts import migrate_db
from tests.test_auth import accounts, FixedClock, ORIGIN, PASSWORD


class SupervisorIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'identity.sqlite3'
        self.backup = Path(self.temp.name) / 'schema1.sqlite3'
        self.clock = FixedClock()

    def snapshot(self, path=None):
        with closing(db.connect(path or self.database)) as conn:
            return {name: [tuple(r) for r in conn.execute(f'SELECT * FROM {name} ORDER BY 1')]
                    for name in ('users','sessions','rooms','reservations','occupancy_slots','audit_events')}

    def legacy_history(self, schema=None):
        with closing(db.connect(self.database)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(schema or Path(__file__).with_name('fixtures').joinpath('schema_v1.sql').read_text())
            conn.executemany('INSERT INTO users VALUES(?,?,?,?,?,?)', [
                (11,'legacy_student','旧学生','preserved-hash','member',100),
                (23,'legacy_admin','旧管理员','preserved-admin-hash','admin',100)])
            conn.execute("INSERT INTO rooms VALUES(37,'历史房间','旧位置',20,100,100)")
            conn.execute("INSERT INTO reservations(id,kind,room_id,user_id,title,purpose,attendees,start_at,end_at,intent_key,request_payload,created_at) "
                         "VALUES(41,'booking',37,11,'历史预约','旧用途',3,1800001800,1800005400,'historical-intent-41','{}',100)")
            conn.executemany('INSERT INTO occupancy_slots VALUES(37,?,41)', [(1800001800,), (1800003600,)])
            conn.execute("INSERT INTO audit_events VALUES(53,11,'旧时显示名','booking.created','booking',41,1800000000,NULL,?,NULL)",
                         (json.dumps(dto.booking_snapshot(conn.execute('SELECT * FROM reservations WHERE id=41').fetchone()),ensure_ascii=False),))
            conn.execute('INSERT INTO sessions VALUES(?,11,?,1800000000,1800028800)', (auth.token_digest('legacy-token'),'legacy-csrf'))
            conn.execute('INSERT INTO sessions VALUES(?,23,?,1800000000,1800028800)', (auth.token_digest('admin-token'),'admin-csrf'))
            conn.execute('PRAGMA user_version=1')

    def login(self, app, name, extra=None):
        client = app.test_client()
        page = client.get('/login', base_url=ORIGIN)
        csrf = re.search('name="csrf_token" value="([^"]+)"', page.text).group(1)
        result = client.post('/api/login', base_url=ORIGIN, headers={'Origin':ORIGIN,'X-CSRF-Token':csrf},
                             json=dict(username=name,password=PASSWORD,**(extra or {})))
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn('Max-Age=28800',result.headers['Set-Cookie'])
        return client, result.json['data']

    def test_three_roles_bindings_login_and_teacher_denied_admin(self):
        self.assertEqual(seed_users(self.database, accounts(), self.clock),5)
        with closing(db.connect(self.database)) as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT s.username,t.username FROM users s JOIN users t ON t.id=s.supervisor_id ORDER BY s.username')],
                             [('demo_member_a','demo_teacher_a'),('demo_member_b','demo_teacher_b')])
        app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        for username,label in [('demo_member_a','学生'),('demo_teacher_a','导师'),('demo_admin','管理员')]:
            client,user=self.login(app,username)
            self.assertEqual(set(user),{'id','display_name','role','csrf_token'})
            self.assertIn(f'<span class="role">{label}</span>',client.get('/',base_url=ORIGIN).text)
            if label!='管理员':
                self.assertEqual(client.get('/admin',base_url=ORIGIN).status_code,403)
                self.assertEqual(client.get('/api/admin/audit',base_url=ORIGIN).status_code,403)
                self.assertEqual(client.post('/api/admin/rooms',base_url=ORIGIN,
                    headers={'Origin':ORIGIN,'X-CSRF-Token':user['csrf_token']},json={}).status_code,403)

    def test_repeat_is_add_only_and_never_repairs_old_binding(self):
        seed_users(self.database, accounts(), self.clock)
        before=self.snapshot()
        changed=accounts('New-password-never-installed')
        changed[0]['supervisor_username']='demo_teacher_b'
        changed[0]['display_name']='unapplied'
        self.assertEqual(seed_users(self.database,changed,self.clock),0)
        self.assertEqual(self.snapshot(),before)
        self.legacy_history_after_reset()
        migrate_db.migrate_database(self.database,self.backup)
        seed_users(self.database,[dict(username='new_teacher',display_name='新导师',role='teacher',password=PASSWORD)],self.clock)
        seed_users(self.database,[dict(username='legacy_student',display_name='not-applied',role='member',password=PASSWORD,supervisor_username='new_teacher')],self.clock)
        with closing(db.connect(self.database)) as conn:
            self.assertEqual(tuple(conn.execute("SELECT display_name,password_hash,supervisor_id FROM users WHERE id=11").fetchone()),('旧学生','preserved-hash',None))

    def legacy_history_after_reset(self):
        self.database.unlink()
        self.legacy_history()

    def test_invalid_mappings_reject_entire_batch_and_single_account_add_supported(self):
        seed_users(self.database,accounts(),self.clock)
        before=self.snapshot()
        student=dict(username='new_student',display_name='新学生',role='member',password=PASSWORD,supervisor_username='demo_teacher_a')
        for overrides in ({'supervisor_username':None},{'supervisor_username':'missing'},
                          {'supervisor_username':'demo_admin'},{'supervisor_username':'demo_member_a'},
                          {'role':'teacher'},{'role':'admin'}):
            invalid=student|overrides
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                seed_users(self.database,[dict(username='new_teacher',display_name='新导师',role='teacher',password=PASSWORD),invalid],self.clock)
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(seed_users(self.database,[student],self.clock),1)
        # Existing authoritative role takes precedence over a supplied teacher role.
        with self.assertRaises(ValueError):
            seed_users(self.database,[dict(username='demo_admin',display_name='伪导师',role='teacher',password=PASSWORD),student|{'username':'bad','supervisor_username':'demo_admin'}],self.clock)

    def test_hashing_outside_writer_and_transaction_failure_rolls_back_all_users(self):
        db.initialize_database(self.database)
        from scripts import init_demo
        original=init_demo.generate_password_hash
        def hash_unlocked(*args,**kwargs):
            with db.write_transaction(self.database):
                pass
            return original(*args,**kwargs)
        with db.write_transaction(self.database) as conn:
            conn.execute("CREATE TRIGGER reject_student BEFORE INSERT ON users WHEN NEW.role='member' BEGIN SELECT RAISE(ABORT,'failure'); END")
        with patch.object(init_demo,'generate_password_hash',side_effect=hash_unlocked),self.assertRaises(sqlite3.IntegrityError):
            seed_users(self.database,accounts(),self.clock)
        self.assertEqual(self.snapshot()['users'],[])

    def test_database_rejects_non_teacher_dangling_and_nonstudent_bindings(self):
        seed_users(self.database,accounts(),self.clock)
        with closing(db.connect(self.database)) as conn:
            ids={r['username']:r['id'] for r in conn.execute('SELECT id,username FROM users')}
            for sql,values in [
                ('UPDATE users SET supervisor_id=? WHERE username=?',(9999,'demo_member_a')),
                ('UPDATE users SET supervisor_id=? WHERE username=?',(ids['demo_admin'],'demo_member_a')),
                ('UPDATE users SET supervisor_id=? WHERE username=?',(ids['demo_teacher_a'],'demo_admin')),
                ('UPDATE users SET supervisor_id=? WHERE username=?',(ids['demo_teacher_a'],'demo_teacher_b')),
                ("UPDATE users SET role='admin' WHERE username=?",('demo_teacher_a',)),
                ('DELETE FROM users WHERE username=?',('demo_teacher_a',))]:
                with self.subTest(sql=sql,values=values),self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql,values)

    def test_client_cannot_set_role_or_supervisor_and_session_reads_database(self):
        seed_users(self.database,accounts(),self.clock)
        before=self.snapshot()['users']
        app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        client,user=self.login(app,'demo_member_a',{'role':'admin','supervisor_id':999,'supervisor_username':'demo_teacher_b'})
        self.assertEqual(user['role'],'member')
        self.assertEqual(self.snapshot()['users'],before)
        for path in ('/api/users','/api/me','/api/supervisor'):
            response=client.post(path,base_url=ORIGIN,headers={'Origin':ORIGIN,'X-CSRF-Token':user['csrf_token']},json={'supervisor_id':999})
            self.assertEqual(response.status_code,400 if path=='/api/me' else 404)
            self.assertEqual(response.json['error']['code'],'INVALID_INPUT' if path=='/api/me' else 'NOT_FOUND')
            self.assertEqual(self.snapshot()['users'],before)
        with db.write_transaction(self.database) as conn:
            conn.execute("UPDATE users SET role='teacher',supervisor_id=NULL WHERE username='demo_member_a'")
        self.assertEqual(client.get('/api/me',base_url=ORIGIN).json['data']['role'],'teacher')

    def test_real_schema1_migration_preserves_all_facts_and_history_readability(self):
        self.legacy_history()
        before=self.snapshot()
        with self.assertRaises(RuntimeError):db.check_database(self.database)
        with self.assertRaises(RuntimeError):db.initialize_database(self.database)
        self.assertEqual(self.snapshot(),before)
        result=migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(result['schema_version'],db.SCHEMA_VERSION)
        self.assertEqual(stat.S_IMODE(self.backup.stat().st_mode),0o600)
        self.assertEqual(self.snapshot(self.backup),before)
        after=self.snapshot()
        with closing(db.connect(self.database)) as conn:
            for table in ('applications','application_occurrences','booking_supervisors'):
                self.assertEqual(conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
        self.assertEqual([r[:-1] for r in after.pop('users')],before.pop('users'))
        self.assertEqual(after,before)
        with closing(db.connect(self.database)) as conn:
            self.assertEqual([r[0] for r in conn.execute('SELECT supervisor_id FROM users')],[None,None])
            self.assertEqual(list(conn.execute('PRAGMA foreign_key_check')),[])
        app=create_app({'TESTING':True,'DATABASE':str(self.database),'CLOCK':self.clock})
        client=app.test_client();client.set_cookie(auth.COOKIE_NAME,'legacy-token',domain='127.0.0.1')
        self.assertEqual(client.get('/api/bookings/41',base_url=ORIGIN).status_code,200)
        client.set_cookie(auth.COOKIE_NAME,'admin-token',domain='127.0.0.1')
        response=client.get('/api/admin/audit',base_url=ORIGIN)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json['data']['items'][0]['actor_display_name'],'旧时显示名')

    def test_migration_failure_after_rebuild_rolls_back_and_backup_is_restorable(self):
        self.legacy_history();before=self.snapshot()
        check=migrate_db._check_integrity
        calls=0
        def fail_after_rebuild(conn):
            nonlocal calls
            calls+=1
            if calls==2:raise RuntimeError('injected-private-value')
            check(conn)
        with patch.object(migrate_db,'_check_integrity',side_effect=fail_after_rebuild),self.assertRaises(RuntimeError):
            migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.snapshot(self.backup),before)
        with closing(db.connect(self.database)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertNotIn('supervisor_id',{r[1] for r in conn.execute('PRAGMA table_info(users)')})
            self.assertEqual(list(conn.execute('PRAGMA foreign_key_check')),[])
        migrate_db.migrate_database(self.backup,Path(self.temp.name)/'backup-of-backup.sqlite3')
        db.check_database(self.backup)

    def test_migration_rejects_bad_version_mapping_foreign_keys_and_backup_collision(self):
        self.legacy_history();before=self.snapshot()
        self.backup.write_bytes(b'never overwrite')
        with self.assertRaises(FileExistsError):migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.backup.read_bytes(),b'never overwrite');self.assertEqual(self.snapshot(),before)
        self.backup.unlink()
        with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.database)
        with closing(db.connect(self.database)) as conn:conn.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.backup)
        self.assertFalse(self.backup.exists())
        with closing(db.connect(self.database)) as conn:
            conn.execute('PRAGMA user_version=1');conn.execute('ALTER TABLE users ADD COLUMN unexpected TEXT')
        with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.snapshot()['reservations'],before['reservations'])
        self.legacy_history_after_reset()
        with closing(db.connect(self.database)) as conn:
            conn.execute('PRAGMA foreign_keys=OFF');conn.execute('UPDATE reservations SET user_id=999')
        bad=self.snapshot()
        with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.snapshot(),bad);self.assertFalse(self.backup.exists())

    def test_migration_cli_success_and_sanitized_nonzero_failure(self):
        self.legacy_history()
        cmd=[sys.executable,'-m','scripts.migrate_db','--source',str(self.database),'--backup',str(self.backup)]
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn(f'"schema_version": {db.SCHEMA_VERSION}',run.stdout)
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,1)
        for secret in ('preserved-hash','Traceback','legacy-csrf'):
            self.assertNotIn(secret,run.stderr+run.stdout)

    def test_init_cli_empty_demo_requires_complete_roles_then_accepts_one_account(self):
        config=Path(self.temp.name)/'private.json'
        config.touch(mode=0o600)
        cmd=[sys.executable,'-m','scripts.init_demo','--credentials-file',str(config)]
        env=dict(os.environ,BOOKING_DB_PATH=str(self.database))
        config.write_text(json.dumps({'users':[accounts()[3]]}))
        run=subprocess.run(cmd,env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,1)
        self.assertNotIn(PASSWORD,run.stderr+run.stdout)
        self.assertFalse(self.database.exists())
        self.database.touch(mode=0o600)
        config.write_text(json.dumps({'users':accounts()}))
        run=subprocess.run(cmd,env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('新增 5 个账号',run.stdout)
        student=dict(accounts()[0],username='extra_student')
        config.write_text(json.dumps({'users':[student]}))
        run=subprocess.run(cmd,env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('新增 1 个账号',run.stdout)

    def schema_facts(self):
        with closing(db.connect(self.database)) as conn:
            return (conn.execute('PRAGMA user_version').fetchone()[0],
                    [tuple(r) for r in conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')])

    def test_migration_source_sidecar_backups_rejected_before_sqlite_open(self):
        self.legacy_history();before=self.snapshot();schema=self.schema_facts()
        alias=Path(self.temp.name)/'alias';alias.symlink_to(Path(self.temp.name),target_is_directory=True)
        raw=self.database.read_bytes()
        for folder in (self.database.parent,alias):
            for suffix in ('-journal','-wal','-shm'):
                with self.subTest(folder=folder,suffix=suffix),patch.object(db,'connect') as connect:
                    with self.assertRaises(ValueError):
                        migrate_db.migrate_database(self.database,folder/(self.database.name+suffix))
                    connect.assert_not_called()
                self.assertEqual(self.database.read_bytes(),raw)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.schema_facts(),schema)
        migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.snapshot(self.backup),before)
        db.check_database(self.database)

    def test_wrong_table_trigger_collision_rolls_back_and_keeps_backup(self):
        self.legacy_history()
        with closing(db.connect(self.database)) as conn:
            conn.execute('CREATE TRIGGER users_supervisor_update BEFORE UPDATE ON rooms BEGIN SELECT 1; END')
        before=self.snapshot();schema=self.schema_facts()
        with self.assertRaisesRegex(RuntimeError,'身份约束'):
            migrate_db.migrate_database(self.database,self.backup)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.schema_facts(),schema)
        self.assertEqual(self.snapshot(self.backup),before)
        with closing(db.connect(self.backup)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT tbl_name FROM sqlite_master WHERE name='users_supervisor_update'").fetchone()[0],'rooms')

    def test_schema2_rejects_missing_altered_or_misattached_identity_guards_and_bad_binding(self):
        seed_users(self.database,accounts(),self.clock)
        db.check_database(self.database)
        with closing(db.connect(self.database)) as conn:
            definitions={r[0]:r[1] for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='users'")}
            for name,sql in definitions.items():
                for variant in ('absent','altered','wrong_table'):
                    with self.subTest(name=name,variant=variant):
                        conn.execute(f'DROP TRIGGER {name}')
                        if variant!='absent':
                            conn.execute(f'CREATE TRIGGER {name} BEFORE UPDATE ON '+('rooms' if variant=='wrong_table' else 'users')+' BEGIN SELECT 1; END')
                        with self.assertRaisesRegex(RuntimeError,'身份约束'):db.check_database(self.database)
                        if variant!='absent':conn.execute(f'DROP TRIGGER {name}')
                        conn.execute(sql)
                        db.check_database(self.database)
            conn.execute('DROP TRIGGER users_supervisor_update')
            conn.execute("UPDATE users SET supervisor_id=(SELECT id FROM users WHERE role='admin') WHERE username='demo_member_a'")
            conn.execute(definitions['users_supervisor_update'])
        with self.assertRaisesRegex(RuntimeError,'无效导师归属'):db.check_database(self.database)

    def test_custom_v1_user_index_trigger_and_constraint_rejected_without_schema_changes(self):
        original=Path(__file__).with_name('fixtures').joinpath('schema_v1.sql').read_text()
        for variant in ('index','trigger','constraint'):
            self.database=Path(self.temp.name)/(variant+'.sqlite3')
            with self.subTest(variant=variant):
                self.legacy_history(original.replace('created_at INTEGER NOT NULL','created_at INTEGER NOT NULL CHECK (created_at > 0)',1) if variant=='constraint' else original)
                with closing(db.connect(self.database)) as conn:
                    if variant=='index':conn.execute('CREATE INDEX custom_user_name ON users(display_name)')
                    if variant=='trigger':conn.execute('CREATE TRIGGER custom_user_guard AFTER UPDATE ON users BEGIN SELECT 1; END')
                before=self.snapshot();schema=self.schema_facts()
                with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.backup)
                self.assertEqual(self.snapshot(),before);self.assertEqual(self.schema_facts(),schema)
                self.assertFalse(self.backup.exists())

    def test_rejected_delete_mode_migration_keeps_wal_setup_but_preserves_facts(self):
        self.legacy_history()
        with closing(db.connect(self.database)) as conn:
            conn.execute('CREATE INDEX custom_user_name ON users(display_name)')
            self.assertEqual(conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0],'delete')
        before=self.snapshot();schema=self.schema_facts()
        with self.assertRaises(ValueError):migrate_db.migrate_database(self.database,self.backup)
        with closing(db.connect(self.database)) as conn:
            self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0],'wal')
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.schema_facts(),schema)
        self.assertFalse(self.backup.exists())


if __name__=='__main__':unittest.main()

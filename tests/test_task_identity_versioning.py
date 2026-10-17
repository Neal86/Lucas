"""Versioned grouping with real SQLite; historical rows are never decoded."""
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from gpt_windows_connector.task_runs import TaskRunStore


def record(store, context, title=None, *, start=1000, **kwargs):
    return store.record_operation(owner_id='owner', node_id='computer', action='fixture',
        target='fixture', started_at=start, ended_at=start + 1, status='success',
        context_key=context, task_title=title, **kwargs)


def legacy_database(path, context='a::task::b::task::c'):
    with sqlite3.connect(path) as db:
        db.executescript('''
        CREATE TABLE task_runs(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
          node_id TEXT NOT NULL, context_key TEXT NOT NULL, title TEXT NOT NULL,
          started_at REAL NOT NULL,last_activity_at REAL NOT NULL,ended_at REAL,
          success_count INTEGER NOT NULL DEFAULT 0,error_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE task_steps(id TEXT PRIMARY KEY,task_run_id TEXT NOT NULL,
          owner_id TEXT NOT NULL,node_id TEXT NOT NULL,action TEXT NOT NULL,target TEXT,
          status TEXT NOT NULL,started_at REAL NOT NULL,ended_at REAL NOT NULL,
          duration_ms INTEGER NOT NULL,operation_count INTEGER NOT NULL DEFAULT 1,
          details TEXT NOT NULL DEFAULT '{}');
        ''')
        db.execute('INSERT INTO task_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('legacy', 'owner', 'computer', context, 'Historical title', 999, 1000, 1000, 1, 0))
        db.execute('INSERT INTO task_steps VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('legacy-operation', 'legacy', 'owner', 'computer', 'fixture', 'old', 'success', 999, 1000, 1000, 3, '{}'))


def snapshot(path):
    with sqlite3.connect(path) as db:
        return {name: db.execute('SELECT * FROM ' + name + ' ORDER BY id').fetchall()
                for name in ('task_runs', 'task_steps')}


@pytest.mark.parametrize('left,right', [
    (('a', 'b::task::c'), ('a::task::b', 'c')),
    (('a', 'b'), ('a::task::b', None)),
    (('a::task::b', None), ('a', 'b')),
    (('a::task::b', 'c'), ('a', None)),
])
def test_distinct_structured_identities_never_merge(tmp_path, left, right):
    store = TaskRunStore(tmp_path / 'identity.db')
    first = record(store, *left)
    second = record(store, *right, start=1002)
    assert first != second
    assert record(store, *left, start=1004) == first
    assert record(store, *right, start=1006) == second
    assert sorted(len(run['steps']) for run in store.list_runs('owner')) == [2, 2]


@pytest.mark.parametrize('context', ['a::task::b::task::c', '[1,"a","b"]', 'v1:a:b', 'a\0::task::b'])
def test_legacy_rows_are_visible_unchanged_and_not_new_candidates(tmp_path, context):
    path = tmp_path / 'legacy.db'; legacy_database(path, context)
    old = snapshot(path)
    store = TaskRunStore(path)
    migrated = snapshot(path)
    assert migrated['task_runs'][0][:-3] == old['task_runs'][0]
    assert migrated['task_runs'][0][-3:] == (0, None, None)
    assert migrated['task_steps'] == old['task_steps']
    TaskRunStore(path)
    assert snapshot(path) == migrated
    history = store.list_runs('owner')
    assert history[0]['context_key'] == context
    assert history[0]['steps'][0]['operation_count'] == 3
    assert not {'identity_version','identity_context','identity_title'} & history[0].keys()
    assert record(store, 'unrelated', 'ignored', operation_id='legacy-operation') == 'legacy'
    assert snapshot(path) == migrated
    assert record(store, context, start=1002) != 'legacy'
    assert record(store, 'a', 'b::task::c', start=1004) != 'legacy'
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM task_runs WHERE id='legacy'").fetchone() == migrated['task_runs'][0]
        assert db.execute("SELECT * FROM task_steps WHERE id='legacy-operation'").fetchone() == old['task_steps'][0]


def test_concurrent_additive_migration_is_idempotent(tmp_path):
    path = tmp_path / 'startup.db'; legacy_database(path)
    barrier = threading.Barrier(8)
    def initialize(_):
        barrier.wait(timeout=10)
        return TaskRunStore(path).list_runs('owner')[0]['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(initialize, range(8))) == ['legacy'] * 8
    before = snapshot(path)
    TaskRunStore(path)
    assert snapshot(path) == before
    with sqlite3.connect(path) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(task_runs)')]
        assert columns.count('identity_version') == 1
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='idx_task_runs_identity'").fetchone()[0] == 1


def test_new_identity_promotion_replay_and_caller_rollback(tmp_path):
    path = tmp_path / 'transaction.db'; store = TaskRunStore(path)
    first = record(store, 'literal::task::context')
    before = snapshot(path)
    db = sqlite3.connect(path); db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        assert record(store, 'literal::task::context', '  New   title ', start=1002,
                      connection=db, operation_id='stable') == first
        assert record(store, 'other', 'Other', start=1004,
                      connection=db, operation_id='stable') == first
        assert db.in_transaction
        db.rollback()
    finally:
        db.close()
    assert snapshot(path) == before
    assert record(store, 'literal::task::context', '  New   title ', start=1002) == first
    assert record(store, 'literal::task::context', start=1004) == first
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT identity_version,identity_context,identity_title FROM task_runs').fetchone() == (1, 'literal::task::context', 'New title')


def test_versioned_collisions_and_legacy_history_through_settlement_and_http(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from gpt_windows_connector import gateway, webapp
    from gpt_windows_connector.auth import AuthStore
    from gpt_windows_connector.entitlements import snapshot as quota
    from gpt_windows_connector.operation_admission import OperationAdmissionStore
    path=tmp_path/'http.db';legacy_database(path)
    auth=AuthStore(path,'synthetic-versioned-history-key'*2)
    user=auth.register('identity@example.invalid','Synthetic-password-only')
    foreign=auth.register('other@example.invalid','Synthetic-password-only')
    with sqlite3.connect(path) as db:
        db.execute('UPDATE task_runs SET owner_id=?',(user.id,))
        db.execute('UPDATE task_steps SET owner_id=?',(user.id,))
    tasks=TaskRunStore(path);admission=OperationAdmissionStore(path,auth_store=auth,task_store=tasks)
    monkeypatch.setenv('LUCAS_BETA_FREE','1')
    for name,value in {'db_path':path,'auth':auth,'task_runs':tasks}.items():monkeypatch.setattr(gateway,name,value)
    runs=[]
    for context,title,units in [('a','b::task::c',2),('a::task::b','c',3)]:
        item=admission.reserve(owner_id=user.id,node_id='computer',action='fixture',target='synthetic-only',context_key=context,task_title=title)
        runs.append(admission.settle(item['id'],operation_count=units))
        before=snapshot(path)
        assert admission.settle(item['id'],operation_count=99,status='failed')==runs[-1]
        assert snapshot(path)==before
    assert len(set(runs))==2 and 'legacy' not in runs
    before=snapshot(path)
    with TestClient(webapp.app) as client:
        response=client.get('/api/task-runs?node_id=computer',headers={'Authorization':'Bearer '+auth.issue_token(user)})
        assert response.status_code==200
        data=response.json()
        assert {run['id'] for run in data['runs']}=={'legacy',*runs}
        assert data['summary']['task_runs']==3 and data['summary']['operations']==8
        assert all(not {'identity_version','identity_context','identity_title'} & run.keys() for run in data['runs'])
        other=client.get('/api/task-runs',headers={'Authorization':'Bearer '+auth.issue_token(foreign)})
        assert other.status_code==200 and other.json()['runs']==[]
    assert snapshot(path)==before
    assert quota(path,user.id).requests_used==5

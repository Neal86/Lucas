import sqlite3
import time

from gpt_windows_connector.entitlements import active_node_ids, snapshot


def schema(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE subscriptions(user_id TEXT PRIMARY KEY,plan TEXT,status TEXT,expansion_quantity INTEGER DEFAULT 0,current_period_start REAL,current_period_end REAL,cancel_at_period_end INTEGER DEFAULT 0,bonus_requests INTEGER DEFAULT 0);
        CREATE TABLE task_steps(id INTEGER PRIMARY KEY,owner_id TEXT,started_at REAL);
        CREATE TABLE user_node_bindings(user_id TEXT,node_id TEXT,approved_at REAL);
        CREATE TABLE oauth_client_users(client_id TEXT,user_id TEXT,authorized_at REAL);
        CREATE TABLE users(id TEXT PRIMARY KEY,role TEXT);
        CREATE TABLE entitlement_overrides(user_id TEXT PRIMARY KEY,bonus_requests INTEGER DEFAULT 0,bonus_nodes INTEGER DEFAULT 0,bonus_ai_accounts INTEGER DEFAULT 0,expires_at REAL,updated_at REAL DEFAULT 0);
        """)

def test_unexpired_override_applies_and_expired_override_is_ignored(tmp_path):
    p=tmp_path/'db.sqlite'; schema(p); now=time.time()
    with sqlite3.connect(p) as db:
        db.execute("INSERT INTO users VALUES('u','user')")
        db.execute("INSERT INTO entitlement_overrides VALUES('u',5000,2,1,?,?)",(now+3600,now))
    e=snapshot(p,'u',now)
    assert (e.request_limit,e.node_limit,e.ai_account_limit)==(6000,3,2)
    e2=snapshot(p,'u',now+7200)
    assert (e2.request_limit,e2.node_limit,e2.ai_account_limit)==(1000,1,1)

def test_admin_pro_plus_and_extra_nodes_drive_active_selection(tmp_path):
    p=tmp_path/'db.sqlite'; schema(p); now=time.time()
    with sqlite3.connect(p) as db:
        db.execute("INSERT INTO users VALUES('a','admin')")
        db.execute("INSERT INTO entitlement_overrides VALUES('a',1000,2,1,NULL,?)",(now,))
        db.executemany("INSERT INTO user_node_bindings VALUES('a',?,?)",[(f'n{i}',now+i) for i in range(8)])
    e=snapshot(p,'a',now)
    assert e.admin_grant and e.plan=='pro_plus'
    assert (e.request_limit,e.node_limit,e.ai_account_limit)==(101000,8,4)
    assert len(active_node_ids(p,'a'))==8

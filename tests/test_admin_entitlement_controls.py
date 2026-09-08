import sqlite3

from gpt_windows_connector.entitlements import snapshot

def test_non_admin_keeps_normal_plan(tmp_path):
    p=tmp_path/"x.db"
    with sqlite3.connect(p) as db:
        db.execute("CREATE TABLE users(id TEXT PRIMARY KEY,role TEXT)")
        db.execute("INSERT INTO users VALUES('u','user')")
        db.execute("CREATE TABLE subscriptions(user_id TEXT PRIMARY KEY,plan TEXT,status TEXT,expansion_quantity INTEGER DEFAULT 0,current_period_start REAL,current_period_end REAL,cancel_at_period_end INTEGER DEFAULT 0,bonus_requests INTEGER DEFAULT 0)")
        db.execute("CREATE TABLE task_steps(id INTEGER PRIMARY KEY,owner_id TEXT,started_at REAL)")
        db.execute("CREATE TABLE user_node_bindings(user_id TEXT,node_id TEXT,approved_at REAL)")
        db.execute("CREATE TABLE oauth_client_users(client_id TEXT,user_id TEXT,authorized_at REAL)")
    e=snapshot(p,'u')
    assert e.plan=='free' and e.node_limit==1 and e.ai_account_limit==1

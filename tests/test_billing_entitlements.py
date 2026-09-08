import sqlite3
import time

import pytest

from gpt_windows_connector.entitlements import active_node_ids, ensure_ai_capacity, ensure_node_active, ensure_node_capacity, ensure_request_capacity, set_active_node, snapshot


def schema(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE subscriptions(user_id TEXT PRIMARY KEY,plan TEXT,status TEXT,expansion_quantity INTEGER DEFAULT 0,current_period_start REAL,current_period_end REAL,cancel_at_period_end INTEGER DEFAULT 0,bonus_requests INTEGER DEFAULT 0);
        CREATE TABLE task_steps(id INTEGER PRIMARY KEY,owner_id TEXT,started_at REAL);
        CREATE TABLE user_node_bindings(user_id TEXT,node_id TEXT,approved_at REAL);
        CREATE TABLE oauth_client_users(client_id TEXT,user_id TEXT,authorized_at REAL);
        """)


def paid(path, plan, expansion=0):
    now=time.time()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO subscriptions VALUES(?,?,?,?,?,?,?,?)",("u",plan,"active",expansion,now-100,now+10000,0,0))


def test_plan_limits_and_pro_plus_expansion(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro_plus",2)
    e=snapshot(p,"u")
    assert (e.request_limit,e.node_limit,e.ai_account_limit)==(300000,18,5)
    assert e.can_buy_expansion is True


def test_expansion_never_applies_to_pro(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro",9)
    e=snapshot(p,"u")
    assert (e.request_limit,e.node_limit,e.ai_account_limit)==(25000,3,1)
    assert e.expansion_quantity==0 and not e.can_buy_expansion


def test_requests_are_task_steps_not_http_requests(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro")
    now=time.time()
    with sqlite3.connect(p) as db:
        db.executemany("INSERT INTO task_steps(owner_id,started_at) VALUES(?,?)",[("u",now)]*7)
    assert snapshot(p,"u").requests_used==7


def test_node_and_ai_limits_are_hard(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro")
    now=time.time()
    with sqlite3.connect(p) as db:
        db.executemany("INSERT INTO user_node_bindings VALUES(?,?,?)",[("u",f"n{i}",now+i) for i in range(3)])
        db.execute("INSERT INTO oauth_client_users VALUES(?,?,?)",("c1","u",now))
    ensure_node_capacity(p,"u","n4")
    with pytest.raises(PermissionError): ensure_ai_capacity(p,"u","c2")
    assert len(active_node_ids(p,"u")) == 3
    ensure_node_active(p,"u",active_node_ids(p,"u")[0])


def test_over_limit_existing_node_is_preserved_but_blocked(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro")
    now=time.time()
    with sqlite3.connect(p) as db:
        db.executemany("INSERT INTO user_node_bindings VALUES(?,?,?)",[("u",f"n{i}",now+i) for i in range(4)])
    active=active_node_ids(p,"u")
    inactive=next(n for n in ["n0","n1","n2","n3"] if n not in active)
    with pytest.raises(PermissionError): ensure_node_active(p,"u",inactive)
    set_active_node(p,"u",inactive)
    ensure_node_active(p,"u",inactive)
    assert inactive in active_node_ids(p,"u")
    with sqlite3.connect(p) as db: assert db.execute("SELECT COUNT(*) FROM user_node_bindings").fetchone()[0]==4


def test_request_limit_blocks_before_next_operation(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p); paid(p,"pro")
    now=time.time()
    with sqlite3.connect(p) as db:
        db.executemany("INSERT INTO task_steps(owner_id,started_at) VALUES(?,?)",[("u",now)]*25000)
    with pytest.raises(PermissionError): ensure_request_capacity(p,"u")


def test_free_prefers_online_computer_and_allows_manual_switch(tmp_path):
    p=tmp_path/"db.sqlite"; schema(p)
    now=time.time()
    with sqlite3.connect(p) as db:
        db.executemany("INSERT INTO user_node_bindings VALUES(?,?,?)",[("u","old-offline",now-100),("u","online",now-50),("u","other",now-10)])
    assert active_node_ids(p,"u",["online"]) == ["online"]
    assert snapshot(p,"u").nodes_used == 1
    assert snapshot(p,"u").nodes_connected == 3
    set_active_node(p,"u","other")
    assert active_node_ids(p,"u",["online"]) == ["other"]
    with pytest.raises(PermissionError): ensure_node_active(p,"u","online")
    ensure_node_active(p,"u","other")

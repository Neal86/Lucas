import sqlite3

from gpt_windows_connector.webapp import _ensure_dashboard_metadata_schema


def test_dashboard_metadata_schema_is_user_scoped():
    db = sqlite3.connect(":memory:")
    _ensure_dashboard_metadata_schema(db)
    db.execute("INSERT INTO dashboard_node_metadata(user_id,node_id,display_name,updated_at) VALUES(?,?,?,?)", ("u1","n1","Office",1))
    db.execute("INSERT INTO dashboard_node_metadata(user_id,node_id,display_name,updated_at) VALUES(?,?,?,?)", ("u2","n1","Home",1))
    rows = db.execute("SELECT user_id,display_name FROM dashboard_node_metadata WHERE node_id=? ORDER BY user_id", ("n1",)).fetchall()
    assert rows == [("u1","Office"),("u2","Home")]


def test_ai_metadata_supports_name_and_note_per_user():
    db = sqlite3.connect(":memory:")
    _ensure_dashboard_metadata_schema(db)
    db.execute("INSERT INTO dashboard_ai_metadata(user_id,client_id,display_name,note,updated_at) VALUES(?,?,?,?,?)", ("u1","c1","Work ChatGPT","finance",1))
    row = db.execute("SELECT display_name,note FROM dashboard_ai_metadata WHERE user_id=? AND client_id=?", ("u1","c1")).fetchone()
    assert row == ("Work ChatGPT","finance")


def test_dashboard_user_node_relationship_survives_authorization_changes():
    db = sqlite3.connect(":memory:")
    _ensure_dashboard_metadata_schema(db)
    db.execute("INSERT INTO dashboard_user_nodes(user_id,node_id,node_name,access_state,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("u1","n1","Office PC","authorized",1,1))
    db.execute("UPDATE dashboard_user_nodes SET access_state='unauthorized',updated_at=2 WHERE user_id='u1' AND node_id='n1'")
    row = db.execute("SELECT node_id,node_name,access_state FROM dashboard_user_nodes WHERE user_id='u1'").fetchone()
    assert row == ("n1","Office PC","unauthorized")


def test_pending_node_is_backfilled_into_durable_dashboard_relationship():
    db = sqlite3.connect(":memory:")
    _ensure_dashboard_metadata_schema(db)
    db.execute("INSERT INTO dashboard_pending_node_access(user_id,node_id,node_name,requested_at,updated_at) VALUES(?,?,?,?,?)", ("u1","n2","Home PC",1,2))
    _ensure_dashboard_metadata_schema(db)
    row = db.execute("SELECT node_id,node_name,access_state FROM dashboard_user_nodes WHERE user_id='u1' AND node_id='n2'").fetchone()
    assert row == ("n2","Home PC","pending")

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

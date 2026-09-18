from pathlib import Path


def test_ai_disconnect_commits_before_audit_connection():
    source = Path("src/gpt_windows_connector/webapp.py").read_text(encoding="utf-8")
    start = source.index('if request.method == "DELETE":')
    end = source.index('body = await request.json()', start)
    branch = source[start:end]
    assert 'db.commit()' in branch
    assert 'gateway.auth.audit(user.id, "oauth.disconnect", client_id)' in branch
    assert branch.index('db.commit()') < branch.index('gateway.auth.audit(user.id, "oauth.disconnect", client_id)')

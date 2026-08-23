from starlette.testclient import TestClient

from gpt_windows_connector.auth import AuthStore
from gpt_windows_connector.oauth import OAuthProvider
from gpt_windows_connector import webapp


def _setup(tmp_path):
    db_path = tmp_path / "lucas.db"
    auth = AuthStore(db_path, "test-secret-" * 8)
    provider = OAuthProvider(db_path, auth, "https://lucasmcp.com")
    admin = auth.register("admin@example.com", "password-12345")
    user_a = auth.register("a@example.com", "password-12345")
    user_b = auth.register("b@example.com", "password-12345")
    webapp.gateway.db_path = db_path
    webapp.gateway.auth = auth
    return auth, provider, admin, user_a, user_b


def test_ai_connections_are_isolated_by_user(tmp_path):
    auth, provider, _, user_a, user_b = _setup(tmp_path)
    now = 1_700_000_000.0
    with provider.db() as db:
        db.execute("INSERT INTO oauth_clients(client_id,client_name,redirect_uris,created_at) VALUES(?,?,?,?)", ("client-a", "Client A", '[\"https://a.example/cb\"]', now))
        db.execute("INSERT INTO oauth_clients(client_id,client_name,redirect_uris,created_at) VALUES(?,?,?,?)", ("client-b", "Client B", '[\"https://b.example/cb\"]', now + 1))
    provider.refresh("client-a", user_a.id, "lucas offline_access")
    provider.refresh("client-b", user_b.id, "lucas offline_access")

    client = TestClient(webapp.app)
    client.cookies.set("gwc_access_token", auth.issue_token(user_a))
    response = client.get("/api/ai-connections")
    assert response.status_code == 200
    assert [item["client_id"] for item in response.json()["clients"]] == ["client-a"]


def test_admin_page_rejects_normal_user(tmp_path):
    auth, _, _, user_a, _ = _setup(tmp_path)
    client = TestClient(webapp.app, follow_redirects=False)
    client.cookies.set("gwc_access_token", auth.issue_token(user_a))
    response = client.get("/admin/users")
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_access_and_refresh_tokens_keep_same_user(tmp_path):
    auth, provider, _, user_a, _ = _setup(tmp_path)
    with provider.db() as db:
        db.execute("INSERT INTO oauth_clients(client_id,client_name,redirect_uris,created_at) VALUES(?,?,?,?)", ("client-a", "Client A", '[\"https://a.example/cb\"]', 1_700_000_000.0))

    tokens = provider.tokens(user_a, "client-a", "lucas offline_access", True)
    assert auth.verify_token(tokens["access_token"]).id == user_a.id
    with provider.db() as db:
        row = db.execute("SELECT user_id FROM oauth_refresh_tokens WHERE client_id=? ORDER BY expires_at DESC LIMIT 1", ("client-a",)).fetchone()
    assert row["user_id"] == user_a.id

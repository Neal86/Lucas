from __future__ import annotations

import base64, hashlib, html, json, secrets, sqlite3, time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from .auth import AuthStore, User


class OAuthProvider:
    SCOPES = ("lucas", "offline_access")

    def __init__(self, db_path: Path, auth: AuthStore, public_base_url: str) -> None:
        self.db_path, self.auth = db_path, auth
        self.base = public_base_url.rstrip("/")
        self.resource = f"{self.base}/mcp"
        self._init_db()

    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30); db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL"); return db

    @staticmethod
    def h(v: str) -> str: return hashlib.sha256(v.encode()).hexdigest()

    def _init_db(self):
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS oauth_clients(client_id TEXT PRIMARY KEY,client_name TEXT,redirect_uris TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_requests(request_id TEXT PRIMARY KEY,client_id TEXT NOT NULL,redirect_uri TEXT NOT NULL,state TEXT,scope TEXT NOT NULL,code_challenge TEXT NOT NULL,expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_codes(code_hash TEXT PRIMARY KEY,client_id TEXT NOT NULL,user_id TEXT NOT NULL,redirect_uri TEXT NOT NULL,scope TEXT NOT NULL,code_challenge TEXT NOT NULL,expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_refresh_tokens(token_hash TEXT PRIMARY KEY,client_id TEXT NOT NULL,user_id TEXT NOT NULL,scope TEXT NOT NULL,expires_at REAL NOT NULL,revoked_at REAL);
            CREATE TABLE IF NOT EXISTS oauth_client_users(client_id TEXT NOT NULL,user_id TEXT NOT NULL,authorized_at REAL NOT NULL,PRIMARY KEY(client_id,user_id));
            """)
            db.execute("INSERT OR IGNORE INTO oauth_client_users(client_id,user_id,authorized_at) SELECT client_id,user_id,MIN(expires_at-7776000) FROM oauth_refresh_tokens GROUP BY client_id,user_id")

    async def form(self, request: Request) -> dict[str, str]:
        raw = (await request.body()).decode("utf-8", "replace")
        return {k: v[-1] if v else "" for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def user(self, request: Request) -> User | None:
        try: return self.auth.verify_token(request.cookies.get("gwc_access_token", ""))
        except Exception: return None

    def client(self, cid: str):
        with self.db() as db: return db.execute("SELECT * FROM oauth_clients WHERE client_id=?", (cid,)).fetchone()

    def clean(self):
        now = time.time()
        with self.db() as db:
            db.execute("DELETE FROM oauth_requests WHERE expires_at<?", (now,)); db.execute("DELETE FROM oauth_codes WHERE expires_at<?", (now,))
            db.execute("DELETE FROM oauth_refresh_tokens WHERE expires_at<? OR (revoked_at IS NOT NULL AND revoked_at<?)", (now, now-30))

    async def as_meta(self, _):
        return JSONResponse({"issuer":self.base,"authorization_endpoint":f"{self.base}/oauth/authorize","token_endpoint":f"{self.base}/oauth/token","registration_endpoint":f"{self.base}/oauth/register","response_types_supported":["code"],"grant_types_supported":["authorization_code","refresh_token"],"code_challenge_methods_supported":["S256"],"token_endpoint_auth_methods_supported":["none"],"scopes_supported":list(self.SCOPES)})

    async def resource_meta(self, _):
        return JSONResponse({"resource":self.resource,"authorization_servers":[self.base],"bearer_methods_supported":["header"],"scopes_supported":list(self.SCOPES)})

    @staticmethod
    def redirect_ok(uri: str) -> bool:
        try: p = urlsplit(uri)
        except Exception: return False
        return bool(p.netloc and not p.fragment and p.scheme in {"https","http"} and not (p.scheme=="http" and p.hostname not in {"localhost","127.0.0.1","::1"}))

    async def register(self, request: Request):
        try: body = await request.json()
        except Exception: return JSONResponse({"error":"invalid_client_metadata"}, status_code=400)
        uris = body.get("redirect_uris") or []
        if not isinstance(uris,list) or not uris or len(uris)>20 or any(not self.redirect_ok(str(u)) for u in uris): return JSONResponse({"error":"invalid_redirect_uri"}, status_code=400)
        uris=[str(u) for u in uris]; cid="lucas_"+secrets.token_urlsafe(24); name=str(body.get("client_name") or "MCP Client")[:200]; now=time.time()
        with self.db() as db: db.execute("INSERT INTO oauth_clients VALUES(?,?,?,?)",(cid,name,json.dumps(uris),now))
        return JSONResponse({"client_id":cid,"client_id_issued_at":int(now),"client_name":name,"redirect_uris":uris,"grant_types":["authorization_code","refresh_token"],"response_types":["code"],"token_endpoint_auth_method":"none","scope":" ".join(self.SCOPES)},status_code=201)

    def err(self, uri: str, error: str, state: str=""):
        q={"error":error}; q.update({"state":state} if state else {})
        return RedirectResponse(uri+("&" if "?" in uri else "?")+urlencode(q),302)

    def consent(self, rid: str, user: User, client: str, scope: str):
        return HTMLResponse(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Authorize Lucas</title><style>body{{font:15px Segoe UI,Arial;background:#f6f7fb;padding:24px;color:#101828}}.c{{max-width:520px;margin:8vh auto;background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:28px}}.m{{color:#667085}}button{{padding:11px 16px;border-radius:9px;border:1px solid #d0d5dd;font-weight:650}}.a{{background:#155eef;color:#fff;border:0}}.x{{display:flex;justify-content:flex-end;gap:10px}}</style><div class=c><h1>Lucas</h1><h2>Connect {html.escape(client)}?</h2><p class=m>Signed in as {html.escape(user.email)}. ChatGPT/MCP will be able to use Lucas tools for your authorized projects and Windows nodes.</p><p><b>Scope:</b> {html.escape(scope)}</p><form method=post action=/oauth/authorize/decision><input type=hidden name=request_id value="{html.escape(rid,quote=True)}"><div class=x><button name=decision value=deny>Cancel</button><button class=a name=decision value=allow>Authorize</button></div></form></div>''')

    def login(self, rid: str):
        return HTMLResponse(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in to Lucas</title><style>body{{font:15px Segoe UI,Arial;background:#f6f7fb;padding:24px}}.c{{max-width:440px;margin:8vh auto;background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:28px}}input{{width:100%;box-sizing:border-box;padding:11px;margin:6px 0 14px;border:1px solid #d0d5dd;border-radius:9px}}button{{width:100%;padding:11px;border:0;border-radius:9px;background:#155eef;color:#fff;font-weight:650}}</style><div class=c><h2>Sign in to Lucas</h2><form method=post action=/oauth/authorize/login><input type=hidden name=request_id value="{html.escape(rid,quote=True)}"><label>Email</label><input name=email type=email required><label>Password</label><input name=password type=password required><button>Sign in and continue</button></form></div>''')

    async def authorize(self, request: Request):
        self.clean(); q=request.query_params; cid=q.get("client_id",""); uri=q.get("redirect_uri",""); state=q.get("state",""); scope=(q.get("scope","") or "lucas offline_access").strip(); challenge=q.get("code_challenge",""); c=self.client(cid)
        if not c: return JSONResponse({"error":"invalid_client"},400)
        if uri not in json.loads(c["redirect_uris"]): return JSONResponse({"error":"invalid_redirect_uri"},400)
        if q.get("response_type")!="code": return self.err(uri,"unsupported_response_type",state)
        if q.get("code_challenge_method")!="S256" or not challenge: return self.err(uri,"invalid_request",state)
        if not set(scope.split()).issubset(set(self.SCOPES)): return self.err(uri,"invalid_scope",state)
        if q.get("resource") and q.get("resource","").rstrip("/")!=self.resource.rstrip("/"): return self.err(uri,"invalid_target",state)
        rid=secrets.token_urlsafe(32)
        with self.db() as db: db.execute("INSERT INTO oauth_requests VALUES(?,?,?,?,?,?,?)",(rid,cid,uri,state,scope,challenge,time.time()+600))
        u=self.user(request); return self.consent(rid,u,str(c["client_name"] or "MCP Client"),scope) if u else self.login(rid)

    def req(self, rid: str):
        with self.db() as db: r=db.execute("SELECT * FROM oauth_requests WHERE request_id=?",(rid,)).fetchone()
        return r if r and float(r["expires_at"])>=time.time() else None

    async def authorize_login(self, request: Request):
        f=await self.form(request); r=self.req(f.get("request_id",""))
        if not r: return JSONResponse({"error":"authorization_request_expired"},400)
        try: u=self.auth.login(f.get("email",""),f.get("password",""))
        except Exception: return HTMLResponse("<h2>Invalid email or password</h2>",401)
        c=self.client(str(r["client_id"])); resp=self.consent(str(r["request_id"]),u,str(c["client_name"] if c else "MCP Client"),str(r["scope"])); resp.set_cookie("gwc_access_token",self.auth.issue_token(u),httponly=True,secure=True,samesite="lax",max_age=self.auth.jwt_ttl_seconds); return resp

    async def authorize_decision(self, request: Request):
        f=await self.form(request); rid=f.get("request_id",""); r=self.req(rid); u=self.user(request)
        if not r: return JSONResponse({"error":"authorization_request_expired"},400)
        if not u: return self.login(rid)
        uri=str(r["redirect_uri"]); state=str(r["state"] or "")
        if f.get("decision")!="allow":
            with self.db() as db: db.execute("DELETE FROM oauth_requests WHERE request_id=?",(rid,))
            return self.err(uri,"access_denied",state)
        code=secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO oauth_client_users(client_id,user_id,authorized_at) VALUES(?,?,?)",(r["client_id"],u.id,time.time()))
            db.execute("INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?)",(self.h(code),r["client_id"],u.id,uri,r["scope"],r["code_challenge"],time.time()+300)); db.execute("DELETE FROM oauth_requests WHERE request_id=?",(rid,))
        self.auth.audit(u.id,"oauth.authorize",str(r["client_id"]),{"scope":str(r["scope"])}); q={"code":code}; q.update({"state":state} if state else {}); return RedirectResponse(uri+("&" if "?" in uri else "?")+urlencode(q),302)

    @staticmethod
    def pkce(verifier: str, challenge: str) -> bool:
        actual=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="); return bool(verifier) and secrets.compare_digest(actual,challenge)

    def refresh(self,cid: str,uid: str,scope: str) -> str:
        t=secrets.token_urlsafe(48); now=time.time()
        with self.db() as db:
            # A refresh token proves a client is authorized for this user. Keep
            # the durable ownership index in sync here as well as in consent so
            # every token creation path preserves dashboard/user isolation.
            db.execute("INSERT OR IGNORE INTO oauth_client_users(client_id,user_id,authorized_at) VALUES(?,?,?)",(cid,uid,now))
            db.execute("INSERT INTO oauth_refresh_tokens VALUES(?,?,?,?,?,NULL)",(self.h(t),cid,uid,scope,now+7776000))
        return t

    def tokens(self,u: User,cid: str,scope: str,want_refresh: bool):
        out={"access_token":self.auth.issue_token(u,ttl_seconds=3600),"token_type":"Bearer","expires_in":3600,"scope":scope}
        if want_refresh: out["refresh_token"]=self.refresh(cid,u.id,scope)
        return out

    async def token(self, request: Request):
        self.clean(); f=await self.form(request); grant=f.get("grant_type",""); cid=f.get("client_id","")
        if not self.client(cid): return JSONResponse({"error":"invalid_client"},401)
        if grant=="authorization_code":
            ch=self.h(f.get("code",""))
            with self.db() as db: r=db.execute("SELECT * FROM oauth_codes WHERE code_hash=?",(ch,)).fetchone()
            if not r or float(r["expires_at"])<time.time() or str(r["client_id"])!=cid or f.get("redirect_uri","")!=str(r["redirect_uri"]) or not self.pkce(f.get("code_verifier",""),str(r["code_challenge"])): return JSONResponse({"error":"invalid_grant"},400)
            with self.db() as db: db.execute("DELETE FROM oauth_codes WHERE code_hash=?",(ch,))
            u=self.auth.get_user(str(r["user_id"])); scope=str(r["scope"]); self.auth.audit(u.id,"oauth.token",cid); return JSONResponse(self.tokens(u,cid,scope,True),headers={"Cache-Control":"no-store","Pragma":"no-cache"})
        if grant=="refresh_token":
            th=self.h(f.get("refresh_token",""))
            with self.db() as db: r=db.execute("SELECT * FROM oauth_refresh_tokens WHERE token_hash=?",(th,)).fetchone()
            now=time.time()
            if not r or float(r["expires_at"])<now or str(r["client_id"])!=cid or (r["revoked_at"] is not None and now-float(r["revoked_at"])>30): return JSONResponse({"error":"invalid_grant"},400)
            scope=str(r["scope"]); requested=f.get("scope","").strip()
            if requested and not set(requested.split()).issubset(set(scope.split())): return JSONResponse({"error":"invalid_scope"},400)
            if requested: scope=requested
            with self.db() as db: db.execute("UPDATE oauth_refresh_tokens SET revoked_at=? WHERE token_hash=?",(time.time(),th))
            u=self.auth.get_user(str(r["user_id"])); self.auth.audit(u.id,"oauth.refresh",cid); return JSONResponse(self.tokens(u,cid,scope,True),headers={"Cache-Control":"no-store","Pragma":"no-cache"})
        return JSONResponse({"error":"unsupported_grant_type"},400)
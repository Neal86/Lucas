from __future__ import annotations

import contextvars
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


_current_user: contextvars.ContextVar["User | None"] = contextvars.ContextVar("gwc_current_user", default=None)
_passwords = PasswordHasher()


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str | None
    picture: str | None
    provider: str
    created_at: float
    role: str = "user"
    status: str = "active"


class AuthStore:
    def __init__(self, db_path: Path, jwt_secret: str, jwt_ttl_seconds: int = 60 * 60 * 24 * 30) -> None:
        self.db_path = db_path
        self.jwt_secret = jwt_secret
        self.jwt_ttl_seconds = jwt_ttl_seconds
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT,
                    picture TEXT,
                    provider TEXT NOT NULL,
                    password_hash TEXT,
                    google_sub TEXT UNIQUE,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    created_at REAL NOT NULL
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "role" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            if "status" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "last_login_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN last_login_at REAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id TEXT PRIMARY KEY,
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'inactive',
                    billing_provider TEXT,
                    billing_customer_id TEXT,
                    started_at REAL,
                    ends_at REAL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_daily (
                    user_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    operation_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    execution_seconds REAL NOT NULL DEFAULT 0,
                    bytes_in INTEGER NOT NULL DEFAULT 0,
                    bytes_out INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, day)
                );
                CREATE TABLE IF NOT EXISTS login_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    provider TEXT,
                    created_at REAL NOT NULL
                );
                """
            )
            if not db.execute("SELECT 1 FROM users WHERE role IN ('admin','super_admin') LIMIT 1").fetchone():
                first = db.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1").fetchone()
                if first:
                    db.execute("UPDATE users SET role='super_admin' WHERE id=?", (first["id"],))

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"], email=row["email"], name=row["name"], picture=row["picture"],
            provider=row["provider"], created_at=float(row["created_at"]),
            role=(row["role"] if "role" in row.keys() else "user"),
            status=(row["status"] if "status" in row.keys() else "active"),
        )

    def register(self, email: str, password: str, name: str | None = None) -> User:
        email = email.strip().lower()
        if "@" not in email or len(email) > 320:
            raise ValueError("A valid email is required")
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters")
        now = time.time()
        user_id = uuid.uuid4().hex
        password_hash = _passwords.hash(password)
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO users(id,email,name,provider,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (user_id, email, name or None, "email", password_hash, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Email is already registered") from exc
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE role IN ('admin','super_admin') LIMIT 1").fetchone():
                db.execute("UPDATE users SET role='super_admin' WHERE id=?", (user_id,))
        return self.get_user(user_id)

    def login(self, email: str, password: str) -> User:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone()
        if not row or not row["password_hash"]:
            raise PermissionError("Invalid email or password")
        if (row["status"] if "status" in row.keys() else "active") != "active":
            raise PermissionError("Account is disabled")
        try:
            _passwords.verify(row["password_hash"], password)
        except VerifyMismatchError as exc:
            raise PermissionError("Invalid email or password") from exc
        now = time.time()
        with self._connect() as db:
            db.execute("UPDATE users SET last_login_at=?,updated_at=? WHERE id=?", (now, now, row["id"]))
            db.execute("INSERT INTO login_sessions(user_id,provider,created_at) VALUES(?,?,?)", (row["id"], "email", now))
        return self.get_user(str(row["id"]))

    def google_login(self, *, sub: str, email: str, name: str | None, picture: str | None) -> User:
        if not sub or not email:
            raise ValueError("Google account did not provide required identity fields")
        email = email.strip().lower()
        now = time.time()
        user_id: str
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE google_sub=?", (sub,)).fetchone()
            if row:
                user_id = str(row["id"])
                db.execute("UPDATE users SET name=?,picture=?,updated_at=? WHERE id=?", (name, picture, now, user_id))
            else:
                row = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
                if row:
                    user_id = str(row["id"])
                    db.execute(
                        "UPDATE users SET google_sub=?, provider='google', name=COALESCE(?,name), picture=COALESCE(?,picture), updated_at=? WHERE id=?",
                        (sub, name, picture, now, user_id),
                    )
                else:
                    user_id = uuid.uuid4().hex
                    db.execute(
                        "INSERT INTO users(id,email,name,picture,provider,google_sub,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (user_id, email, name, picture, "google", sub, now, now),
                    )
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE role IN ('admin','super_admin') LIMIT 1").fetchone():
                db.execute("UPDATE users SET role='super_admin' WHERE id=?", (user_id,))
        return self.get_user(user_id)

    def get_user(self, user_id: str) -> User:
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise KeyError("User not found")
        user = self._user(row)
        if user.status != "active":
            raise PermissionError("Account is disabled")
        return user

    def issue_token(self, user: User, ttl_seconds: int | None = None) -> str:
        now = int(time.time())
        ttl = self.jwt_ttl_seconds if ttl_seconds is None else max(60, min(int(ttl_seconds), self.jwt_ttl_seconds))
        payload = {"sub": user.id, "email": user.email, "iat": now, "exp": now + ttl, "iss": "gpt-windows-connector"}
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> User:
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"], issuer="gpt-windows-connector")
            return self.get_user(str(payload["sub"]))
        except Exception as exc:
            raise PermissionError("Invalid or expired access token") from exc

    def new_oauth_state(self, ttl_seconds: int = 600) -> str:
        state = secrets.token_urlsafe(32)
        digest = hashlib.sha256(state.encode()).hexdigest()
        with self._connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),))
            db.execute("INSERT INTO oauth_states(state_hash,expires_at) VALUES(?,?)", (digest, time.time() + ttl_seconds))
        return state

    def consume_oauth_state(self, state: str) -> None:
        digest = hashlib.sha256(state.encode()).hexdigest()
        with self._connect() as db:
            row = db.execute("SELECT expires_at FROM oauth_states WHERE state_hash=?", (digest,)).fetchone()
            db.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest,))
        if not row or float(row["expires_at"]) < time.time():
            raise PermissionError("Invalid or expired OAuth state")

    def record_request(self, user_id: str) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self._connect() as db:
            db.execute("INSERT INTO usage_daily(user_id,day,request_count) VALUES(?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET request_count=request_count+1", (user_id, day))

    def record_operation(self, user_id: str, success: bool, duration_seconds: float) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self._connect() as db:
            db.execute("INSERT INTO usage_daily(user_id,day,operation_count,success_count,error_count,execution_seconds) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET operation_count=operation_count+1,success_count=success_count+excluded.success_count,error_count=error_count+excluded.error_count,execution_seconds=execution_seconds+excluded.execution_seconds", (user_id, day, 1, 1 if success else 0, 0 if success else 1, max(0.0, duration_seconds)))

    def audit(self, user_id: str | None, action: str, target: str | None = None, details: dict[str, Any] | None = None) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO audit_logs(user_id,action,target,details,created_at) VALUES(?,?,?,?,?)",
                (user_id, action, target, json.dumps(details or {}, ensure_ascii=False), time.time()),
            )


def set_current_user(user: User | None):
    return _current_user.set(user)


def reset_current_user(token) -> None:
    _current_user.reset(token)


def current_user(required: bool = True) -> User | None:
    user = _current_user.get()
    if required and user is None:
        raise PermissionError("Authentication required")
    return user


def google_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def google_exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise PermissionError("Google did not return an access token")
        info_resp = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        info_resp.raise_for_status()
        info = info_resp.json()
        if info.get("email_verified") is False:
            raise PermissionError("Google email is not verified")
        return info

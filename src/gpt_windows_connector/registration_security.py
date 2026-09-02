from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
import sqlite3
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

from argon2 import PasswordHasher

_passwords = PasswordHasher()


class RegistrationSecurity:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._buckets: dict[str, list[float]] = {}
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS pending_registrations (
                    email TEXT PRIMARY KEY COLLATE NOCASE,
                    name TEXT,
                    password_hash TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_verifications (
                    challenge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE,
                    ip_address TEXT NOT NULL,
                    remember_device INTEGER NOT NULL DEFAULT 0,
                    code_hash TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trusted_login_devices (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    last_ip TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trusted_login_devices_user ON trusted_login_devices(user_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def _normalize_email(email: str) -> str:
        email = email.strip().lower()
        if "@" not in email or len(email) > 320:
            raise ValueError("A valid email is required")
        return email

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        bucket = [t for t in self._buckets.get(key, []) if t >= cutoff]
        if len(bucket) >= limit:
            self._buckets[key] = bucket
            return False
        bucket.append(now)
        self._buckets[key] = bucket
        return True

    def start(self, email: str, password: str, name: str | None = None) -> tuple[str, str]:
        email = self._normalize_email(email)
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
                raise ValueError("Email is already registered")
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        now = time.time()
        password_hash = _passwords.hash(password)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO pending_registrations(email,name,password_hash,code_hash,expires_at,attempts,created_at,updated_at)
                VALUES(?,?,?,?,?,0,?,?)
                ON CONFLICT(email) DO UPDATE SET
                    name=excluded.name,password_hash=excluded.password_hash,code_hash=excluded.code_hash,
                    expires_at=excluded.expires_at,attempts=0,updated_at=excluded.updated_at
                """,
                (email, name or None, password_hash, code_hash, now + 600, now, now),
            )
        return email, code

    def resend(self, email: str) -> tuple[str, str]:
        email = self._normalize_email(email)
        with self._connect() as db:
            row = db.execute("SELECT * FROM pending_registrations WHERE email=? COLLATE NOCASE", (email,)).fetchone()
            if not row:
                raise ValueError("No pending verification for this email")
            code = f"{secrets.randbelow(1_000_000):06d}"
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            now = time.time()
            db.execute("UPDATE pending_registrations SET code_hash=?,expires_at=?,attempts=0,updated_at=? WHERE email=? COLLATE NOCASE", (code_hash, now + 600, now, email))
        return email, code

    def verify(self, email: str, code: str) -> str:
        email = self._normalize_email(email)
        code = str(code or "").strip()
        if len(code) != 6 or not code.isdigit():
            raise ValueError("Invalid verification code")
        now = time.time()
        with self._connect() as db:
            row = db.execute("SELECT * FROM pending_registrations WHERE email=? COLLATE NOCASE", (email,)).fetchone()
            if not row:
                raise ValueError("No pending verification for this email")
            if float(row["expires_at"]) < now:
                raise ValueError("Verification code expired")
            if int(row["attempts"]) >= 5:
                raise ValueError("Too many verification attempts")
            expected = str(row["code_hash"])
            actual = hashlib.sha256(code.encode()).hexdigest()
            if not secrets.compare_digest(expected, actual):
                db.execute("UPDATE pending_registrations SET attempts=attempts+1,updated_at=? WHERE email=? COLLATE NOCASE", (now, email))
                db.commit()
                raise ValueError("Invalid verification code")
            existing = db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
            if existing:
                user_id = str(existing["id"])
            else:
                user_id = uuid.uuid4().hex
                db.execute(
                    "INSERT INTO users(id,email,name,provider,password_hash,created_at,updated_at,status) VALUES(?,?,?,?,?,?,?,'active')",
                    (user_id, email, row["name"], "email", row["password_hash"], now, now),
                )
            db.execute("DELETE FROM pending_registrations WHERE email=? COLLATE NOCASE", (email,))
        return user_id

    def start_login_verification(
        self,
        user_id: str,
        email: str,
        ip_address: str,
        remember_device: bool,
    ) -> tuple[str, str]:
        email = self._normalize_email(email)
        challenge_id = uuid.uuid4().hex
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        now = time.time()
        with self._connect() as db:
            db.execute("DELETE FROM login_verifications WHERE expires_at < ?", (now,))
            db.execute(
                """
                INSERT INTO login_verifications(
                    challenge_id,user_id,email,ip_address,remember_device,code_hash,
                    expires_at,attempts,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,0,?,?)
                """,
                (challenge_id, user_id, email, ip_address, 1 if remember_device else 0, code_hash, now + 600, now, now),
            )
        return challenge_id, code

    def verify_login(self, challenge_id: str, code: str, ip_address: str) -> tuple[str, bool, str | None]:
        challenge_id = str(challenge_id or "").strip()
        code = str(code or "").strip()
        if not challenge_id:
            raise ValueError("Login verification session is missing")
        if len(code) != 6 or not code.isdigit():
            raise ValueError("Invalid verification code")
        now = time.time()
        with self._connect() as db:
            row = db.execute("SELECT * FROM login_verifications WHERE challenge_id=?", (challenge_id,)).fetchone()
            if not row:
                raise ValueError("Login verification session expired")
            if float(row["expires_at"]) < now:
                db.execute("DELETE FROM login_verifications WHERE challenge_id=?", (challenge_id,))
                db.commit()
                raise ValueError("Verification code expired")
            if str(row["ip_address"]) != str(ip_address):
                db.execute("DELETE FROM login_verifications WHERE challenge_id=?", (challenge_id,))
                db.commit()
                raise ValueError("Login network changed. Please sign in again.")
            if int(row["attempts"]) >= 5:
                raise ValueError("Too many verification attempts")
            expected = str(row["code_hash"])
            actual = hashlib.sha256(code.encode()).hexdigest()
            if not secrets.compare_digest(expected, actual):
                db.execute("UPDATE login_verifications SET attempts=attempts+1,updated_at=? WHERE challenge_id=?", (now, challenge_id))
                db.commit()
                raise ValueError("Invalid verification code")
            user_id = str(row["user_id"])
            remember = bool(row["remember_device"])
            db.execute("DELETE FROM login_verifications WHERE challenge_id=?", (challenge_id,))
            trusted_token: str | None = None
            if remember:
                trusted_token = secrets.token_urlsafe(48)
                token_hash = hashlib.sha256(trusted_token.encode()).hexdigest()
                db.execute(
                    """
                    INSERT INTO trusted_login_devices(id,user_id,token_hash,last_ip,created_at,last_seen_at,expires_at)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (uuid.uuid4().hex, user_id, token_hash, str(ip_address), now, now, now + 60 * 60 * 24 * 30),
                )
        return user_id, remember, trusted_token

    def is_trusted_login(self, user_id: str, token: str | None, ip_address: str) -> bool:
        token = str(token or "").strip()
        if not token:
            return False
        now = time.time()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._connect() as db:
            db.execute("DELETE FROM trusted_login_devices WHERE expires_at < ?", (now,))
            row = db.execute(
                "SELECT id,last_ip FROM trusted_login_devices WHERE user_id=? AND token_hash=? AND expires_at>=?",
                (user_id, token_hash, now),
            ).fetchone()
            if not row:
                return False
            if str(row["last_ip"]) != str(ip_address):
                db.execute("DELETE FROM trusted_login_devices WHERE id=?", (row["id"],))
                return False
            db.execute("UPDATE trusted_login_devices SET last_seen_at=? WHERE id=?", (now, row["id"]))
        return True


def email_verification_enabled() -> bool:
    return bool(os.getenv("GWC_SMTP_HOST", "").strip() and os.getenv("GWC_SMTP_FROM", "").strip())


def send_verification_email(email: str, code: str) -> None:
    host = os.getenv("GWC_SMTP_HOST", "").strip()
    sender = os.getenv("GWC_SMTP_FROM", "").strip()
    if not host or not sender:
        raise RuntimeError("Email verification is not configured")
    port = int(os.getenv("GWC_SMTP_PORT", "587"))
    username = os.getenv("GWC_SMTP_USERNAME", "").strip()
    password = os.getenv("GWC_SMTP_PASSWORD", "")
    use_tls = os.getenv("GWC_SMTP_STARTTLS", "true").lower() not in {"0", "false", "no"}
    msg = EmailMessage()
    msg["Subject"] = "Your Lucas verification code"
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(f"Your Lucas verification code is {code}. It expires in 10 minutes. If you did not request this, you can ignore this email.")
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)

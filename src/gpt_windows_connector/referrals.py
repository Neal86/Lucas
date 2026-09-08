from __future__ import annotations

import secrets
import sqlite3
import string
import time
from pathlib import Path
from typing import Any


REFERRAL_SIGNUP_REWARD_REQUESTS = 1_000
REFERRAL_PAID_REWARD_REQUESTS = 10_000
# Backward-compatible alias used by older callers/tests.
REFERRAL_REWARD_REQUESTS = REFERRAL_PAID_REWARD_REQUESTS


class ReferralService:
    def __init__(self, db_path: Path, base_url: str) -> None:
        self.db_path = Path(db_path)
        self.base_url = base_url.rstrip("/")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS referral_codes(
                user_id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS referrals(
                referred_user_id TEXT PRIMARY KEY,
                referrer_user_id TEXT NOT NULL,
                referral_code TEXT NOT NULL,
                attributed_at REAL NOT NULL,
                qualified_at REAL,
                reward_requests INTEGER NOT NULL DEFAULT 0,
                reward_event_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
            CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);
            """)
            cols = {r[1] for r in db.execute("PRAGMA table_info(referrals)").fetchall()}
            if "signup_reward_requests" not in cols:
                db.execute("ALTER TABLE referrals ADD COLUMN signup_reward_requests INTEGER NOT NULL DEFAULT 0")

    def _new_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(8))

    def code_for(self, user_id: str) -> str:
        with self._connect() as db:
            row = db.execute("SELECT code FROM referral_codes WHERE user_id=?", (user_id,)).fetchone()
            if row:
                return str(row["code"])
            for _ in range(20):
                code = self._new_code()
                try:
                    db.execute(
                        "INSERT INTO referral_codes(user_id,code,created_at) VALUES(?,?,?)",
                        (user_id, code, time.time()),
                    )
                    return code
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("Unable to create referral code")

    def claim(self, referred_user_id: str, code: str) -> bool:
        code = str(code or "").strip().upper()
        if not code:
            return False
        with self._connect() as db:
            referrer = db.execute("SELECT user_id FROM referral_codes WHERE code=?", (code,)).fetchone()
            if not referrer:
                return False
            referrer_user_id = str(referrer["user_id"])
            if referrer_user_id == referred_user_id:
                return False
            existing = db.execute(
                "SELECT 1 FROM referrals WHERE referred_user_id=?",
                (referred_user_id,),
            ).fetchone()
            if existing:
                return False
            now = time.time()
            # A referral is claimed only after the referred account exists. Ensure both
            # users have subscription rows so registration rewards are durable.
            db.execute("INSERT OR IGNORE INTO subscriptions(user_id,updated_at) VALUES(?,?)", (referrer_user_id, now))
            db.execute("INSERT OR IGNORE INTO subscriptions(user_id,updated_at) VALUES(?,?)", (referred_user_id, now))
            db.execute(
                """INSERT INTO referrals(
                    referred_user_id,referrer_user_id,referral_code,attributed_at,status,signup_reward_requests
                ) VALUES(?,?,?,?, 'pending', ?)""",
                (referred_user_id, referrer_user_id, code, now, REFERRAL_SIGNUP_REWARD_REQUESTS),
            )
            db.execute(
                "UPDATE subscriptions SET bonus_requests=COALESCE(bonus_requests,0)+?,updated_at=? WHERE user_id=?",
                (REFERRAL_SIGNUP_REWARD_REQUESTS, now, referrer_user_id),
            )
            db.execute(
                "UPDATE subscriptions SET bonus_requests=COALESCE(bonus_requests,0)+?,updated_at=? WHERE user_id=?",
                (REFERRAL_SIGNUP_REWARD_REQUESTS, now, referred_user_id),
            )
            return True

    def qualify_paid_user(self, referred_user_id: str, event_id: str) -> bool:
        if not referred_user_id or not event_id:
            return False
        with self._connect() as db:
            row = db.execute(
                """SELECT referrer_user_id,status FROM referrals
                   WHERE referred_user_id=?""",
                (referred_user_id,),
            ).fetchone()
            if not row or str(row["status"]) == "rewarded":
                return False
            referrer_user_id = str(row["referrer_user_id"])
            if referrer_user_id == referred_user_id:
                return False
            sub = db.execute(
                "SELECT 1 FROM subscriptions WHERE user_id=?",
                (referrer_user_id,),
            ).fetchone()
            if not sub:
                return False
            try:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT status FROM referrals WHERE referred_user_id=?",
                    (referred_user_id,),
                ).fetchone()
                if not current or str(current["status"]) == "rewarded":
                    db.rollback()
                    return False
                db.execute(
                    """UPDATE subscriptions
                       SET bonus_requests=COALESCE(bonus_requests,0)+?, updated_at=?
                       WHERE user_id=?""",
                    (REFERRAL_PAID_REWARD_REQUESTS, time.time(), referrer_user_id),
                )
                db.execute(
                    """UPDATE referrals
                       SET qualified_at=?,reward_requests=?,reward_event_id=?,status='rewarded'
                       WHERE referred_user_id=?""",
                    (time.time(), REFERRAL_PAID_REWARD_REQUESTS, event_id, referred_user_id),
                )
                db.commit()
                return True
            except sqlite3.IntegrityError:
                db.rollback()
                return False

    def resolve_user_from_invoice(self, invoice: Any) -> str:
        customer = str(self._value(invoice, "customer", "") or "")
        subscription = str(self._value(invoice, "subscription", "") or "")
        with self._connect() as db:
            if subscription:
                row = db.execute(
                    "SELECT user_id FROM subscriptions WHERE stripe_subscription_id=?",
                    (subscription,),
                ).fetchone()
                if row:
                    return str(row["user_id"])
            if customer:
                row = db.execute(
                    "SELECT user_id FROM subscriptions WHERE billing_customer_id=?",
                    (customer,),
                ).fetchone()
                if row:
                    return str(row["user_id"])
        return ""

    def _value(self, obj: Any, key: str, default: Any = None) -> Any:
        try:
            return obj[key]
        except Exception:
            return getattr(obj, key, default)

    def summary(self, user_id: str) -> dict[str, Any]:
        code = self.code_for(user_id)
        with self._connect() as db:
            rows = db.execute(
                """SELECT status,reward_requests,signup_reward_requests,attributed_at,qualified_at
                   FROM referrals WHERE referrer_user_id=?
                   ORDER BY attributed_at DESC""",
                (user_id,),
            ).fetchall()
        paid = sum(1 for r in rows if str(r["status"]) == "rewarded")
        pending = sum(1 for r in rows if str(r["status"]) == "pending")
        signup_earned = sum(int(r["signup_reward_requests"] or 0) for r in rows)
        paid_earned = sum(int(r["reward_requests"] or 0) for r in rows)
        earned = signup_earned + paid_earned
        return {
            "code": code,
            "url": f"{self.base_url}/r/{code}",
            "signup_reward_requests": REFERRAL_SIGNUP_REWARD_REQUESTS,
            "paid_reward_requests": REFERRAL_PAID_REWARD_REQUESTS,
            "reward_requests": REFERRAL_PAID_REWARD_REQUESTS,
            "paid_referrals": paid,
            "pending_referrals": pending,
            "total_referrals": len(rows),
            "signup_earned_requests": signup_earned,
            "paid_earned_requests": paid_earned,
            "earned_requests": earned,
        }

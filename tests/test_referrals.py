import sqlite3
from pathlib import Path

from gpt_windows_connector.referrals import REFERRAL_REWARD_REQUESTS, ReferralService


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "referrals.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE users(id TEXT PRIMARY KEY);
        CREATE TABLE subscriptions(
            user_id TEXT PRIMARY KEY,
            bonus_requests INTEGER NOT NULL DEFAULT 0,
            updated_at REAL,
            billing_customer_id TEXT,
            stripe_subscription_id TEXT
        );
        INSERT INTO users(id) VALUES('referrer'),('friend');
        INSERT INTO subscriptions(user_id) VALUES('referrer'),('friend');
        """)
    return path


def test_referral_awards_3000_once(tmp_path):
    path = _db(tmp_path)
    service = ReferralService(path, "https://lucasmcp.com")
    code = service.code_for("referrer")
    assert service.claim("friend", code)
    assert not service.claim("friend", code)
    assert service.qualify_paid_user("friend", "evt_first_paid")
    assert not service.qualify_paid_user("friend", "evt_second_paid")
    with sqlite3.connect(path) as db:
        bonus = db.execute(
            "SELECT bonus_requests FROM subscriptions WHERE user_id='referrer'"
        ).fetchone()[0]
    assert bonus == REFERRAL_REWARD_REQUESTS == 3000


def test_self_referral_is_rejected(tmp_path):
    path = _db(tmp_path)
    service = ReferralService(path, "https://lucasmcp.com")
    code = service.code_for("referrer")
    assert service.claim("referrer", code) is False


def test_referral_summary_has_share_link(tmp_path):
    path = _db(tmp_path)
    service = ReferralService(path, "https://lucasmcp.com")
    summary = service.summary("referrer")
    assert summary["url"].startswith("https://lucasmcp.com/r/")
    assert summary["reward_requests"] == 3000

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "gpt_windows_connector"


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Referral rewards: registration gives both sides 1,000; first paid invoice gives referrer 10,000.
p = SRC / "referrals.py"
text = p.read_text(encoding="utf-8")
text = text.replace("REFERRAL_REWARD_REQUESTS = 3_000", "REFERRAL_SIGNUP_REWARD_REQUESTS = 1_000\nREFERRAL_PAID_REWARD_REQUESTS = 10_000\n# Backward-compatible alias used by older callers/tests.\nREFERRAL_REWARD_REQUESTS = REFERRAL_PAID_REWARD_REQUESTS")
text = text.replace(
'''            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);\n            CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);\n            \"\"\")''',
'''            CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);\n            CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);\n            \"\"\")\n            cols = {r[1] for r in db.execute(\"PRAGMA table_info(referrals)\").fetchall()}\n            if \"signup_reward_requests\" not in cols:\n                db.execute(\"ALTER TABLE referrals ADD COLUMN signup_reward_requests INTEGER NOT NULL DEFAULT 0\")''')
old_claim = '''            db.execute(\n                \"\"\"INSERT INTO referrals(\n                    referred_user_id,referrer_user_id,referral_code,attributed_at,status\n                ) VALUES(?,?,?,?, 'pending')\"\"\",\n                (referred_user_id, referrer_user_id, code, time.time()),\n            )\n            return True'''
new_claim = '''            now = time.time()\n            # A referral is claimed only after the referred account exists. Ensure both\n            # users have subscription rows so registration rewards are durable.\n            db.execute(\"INSERT OR IGNORE INTO subscriptions(user_id,plan,status,updated_at) VALUES(?, 'free','inactive',?)\", (referrer_user_id, now))\n            db.execute(\"INSERT OR IGNORE INTO subscriptions(user_id,plan,status,updated_at) VALUES(?, 'free','inactive',?)\", (referred_user_id, now))\n            db.execute(\n                \"\"\"INSERT INTO referrals(\n                    referred_user_id,referrer_user_id,referral_code,attributed_at,status,signup_reward_requests\n                ) VALUES(?,?,?,?, 'pending', ?)\"\"\",\n                (referred_user_id, referrer_user_id, code, now, REFERRAL_SIGNUP_REWARD_REQUESTS),\n            )\n            db.execute(\n                \"UPDATE subscriptions SET bonus_requests=COALESCE(bonus_requests,0)+?,updated_at=? WHERE user_id=?\",\n                (REFERRAL_SIGNUP_REWARD_REQUESTS, now, referrer_user_id),\n            )\n            db.execute(\n                \"UPDATE subscriptions SET bonus_requests=COALESCE(bonus_requests,0)+?,updated_at=? WHERE user_id=?\",\n                (REFERRAL_SIGNUP_REWARD_REQUESTS, now, referred_user_id),\n            )\n            return True'''
if old_claim not in text:
    raise SystemExit("claim block not found")
text = text.replace(old_claim, new_claim, 1)
text = text.replace("(REFERRAL_REWARD_REQUESTS, time.time(), referrer_user_id)", "(REFERRAL_PAID_REWARD_REQUESTS, time.time(), referrer_user_id)")
text = text.replace("(time.time(), REFERRAL_REWARD_REQUESTS, event_id, referred_user_id)", "(time.time(), REFERRAL_PAID_REWARD_REQUESTS, event_id, referred_user_id)")
text = text.replace(
'''                \"\"\"SELECT status,reward_requests,attributed_at,qualified_at\n                   FROM referrals WHERE referrer_user_id=?''',
'''                \"\"\"SELECT status,reward_requests,signup_reward_requests,attributed_at,qualified_at\n                   FROM referrals WHERE referrer_user_id=?''')
text = text.replace("        earned = sum(int(r[\"reward_requests\"] or 0) for r in rows)", "        signup_earned = sum(int(r[\"signup_reward_requests\"] or 0) for r in rows)\n        paid_earned = sum(int(r[\"reward_requests\"] or 0) for r in rows)\n        earned = signup_earned + paid_earned")
text = text.replace(
'''            \"reward_requests\": REFERRAL_REWARD_REQUESTS,\n            \"paid_referrals\": paid,''',
'''            \"signup_reward_requests\": REFERRAL_SIGNUP_REWARD_REQUESTS,\n            \"paid_reward_requests\": REFERRAL_PAID_REWARD_REQUESTS,\n            \"reward_requests\": REFERRAL_PAID_REWARD_REQUESTS,\n            \"paid_referrals\": paid,''')
text = text.replace('''            \"earned_requests\": earned,\n        }''', '''            \"signup_earned_requests\": signup_earned,\n            \"paid_earned_requests\": paid_earned,\n            \"earned_requests\": earned,\n        }''')
p.write_text(text, encoding="utf-8")

# 2) Add dashboard-native Refer & Earn markup in its own existing UI module.
p = SRC / "referral_ui.py"
text = p.read_text(encoding="utf-8")
if "def dashboard_referral_html" not in text:
    text += '''\n\ndef dashboard_referral_html() -> str:\n    return \"\"\"<div id=\"referral\" class=\"view hidden\"><div class=\"top\"><div><h2>Refer & Earn</h2><p class=\"muted\">Invite friends to Lucas and earn bonus Requests.</p></div></div><div id=\"referralError\" class=\"error hidden\"></div><div class=\"card\" style=\"margin-bottom:16px\"><h3 style=\"margin-bottom:6px\">Invite a friend</h3><p class=\"muted\" style=\"margin-top:0\">When your friend registers, you both get <b>1,000 bonus Requests</b>. When they make their first successful payment, you get another <b>10,000 bonus Requests</b>.</p><div class=\"row\"><input id=\"referralUrl\" class=\"input\" readonly><button class=\"btn primary\" onclick=\"copyReferralLink()\">Copy invite link</button></div><p class=\"muted\" style=\"margin-bottom:0\">Referral code: <b id=\"referralCode\">—</b></p></div><div class=\"grid\"><div class=\"card\"><div class=\"muted\">Registered referrals</div><div id=\"referralTotal\" class=\"metric\">—</div></div><div class=\"card\"><div class=\"muted\">Paid referrals</div><div id=\"referralPaid\" class=\"metric\">—</div></div><div class=\"card\"><div class=\"muted\">Requests earned</div><div id=\"referralEarned\" class=\"metric\">—</div></div></div><div class=\"card\" style=\"margin-top:16px\"><h3>How rewards work</h3><div class=\"grid\"><div><div class=\"muted\">Friend registers</div><div class=\"metric\" style=\"font-size:22px\">+1,000 each</div></div><div><div class=\"muted\">Friend becomes paid</div><div class=\"metric\" style=\"font-size:22px\">+10,000 to you</div></div><div><div class=\"muted\">Limits</div><div style=\"margin-top:8px\">One registration reward and one paid reward per referred account. Self-referrals are blocked.</div></div></div></div></div>\"\"\"\n'''
p.write_text(text, encoding="utf-8")

# 3) Separate referral dashboard runtime.
(SRC / "web_referral_runtime.py").write_text('''from __future__ import annotations\n\nREFERRAL_SCRIPT = r\"\"\"<script>\nasync function loadReferralView(){try{const e=document.getElementById('referralError');if(e)e.classList.add('hidden');const s=await api('/api/referrals/summary');referralUrl.value=s.url||'';referralCode.textContent=s.code||'—';referralTotal.textContent=Number(s.total_referrals||0).toLocaleString();referralPaid.textContent=Number(s.paid_referrals||0).toLocaleString();referralEarned.textContent=Number(s.earned_requests||0).toLocaleString()}catch(err){const e=document.getElementById('referralError');if(e){e.textContent=err?.message||String(err);e.classList.remove('hidden')}}}\nasync function copyReferralLink(){const e=document.getElementById('referralUrl');if(!e)return;try{await navigator.clipboard.writeText(e.value);toast('Invite link copied')}catch{e.select();document.execCommand('copy');toast('Invite link copied')}}\nwindow.loadReferralView=loadReferralView;window.copyReferralLink=copyReferralLink;\n</script>\"\"\"\n''', encoding="utf-8")

# 4) Compose referral runtime into the dashboard document.
p = SRC / "web_assets.py"
text = p.read_text(encoding="utf-8")
text = text.replace("from .web_i18n_runtime import I18N_SCRIPT\n", "from .web_i18n_runtime import I18N_SCRIPT\nfrom .web_referral_runtime import REFERRAL_SCRIPT\n")
text = text.replace("    + BILLING_SCRIPT\n    + CORE_SCRIPT", "    + BILLING_SCRIPT\n    + REFERRAL_SCRIPT\n    + CORE_SCRIPT")
p.write_text(text, encoding="utf-8")

# 5) Add the left-side navigation item in the requested order.
p = SRC / "web_dashboard_markup.py"
text = p.read_text(encoding="utf-8")
needle = '>Account & Security</button><button class="nav" data-view="billing"'
replacement = '>Account & Security</button><button class="nav" data-view="referral" onclick="view(\'referral\',this)">Refer & Earn</button><button class="nav" data-view="billing"'
if needle not in text:
    raise SystemExit("dashboard nav marker not found")
text = text.replace(needle, replacement, 1)
p.write_text(text, encoding="utf-8")

# 6) Teach dashboard router to treat /refer as a native view.
p = SRC / "web_core_runtime.py"
text = p.read_text(encoding="utf-8")
text = text.replace("account:\\'/account\\',billing:\\'/billing\\',admin:\\'/admin\\'", "account:\\'/account\\',referral:\\'/refer\\',billing:\\'/billing\\',admin:\\'/admin\\'")
text = text.replace("if(id===\\'billing\\'&&window.loadBillingView)window.loadBillingView();if(id===\\'admin\\')", "if(id===\\'referral\\'&&window.loadReferralView)window.loadReferralView();if(id===\\'billing\\'&&window.loadBillingView)window.loadBillingView();if(id===\\'admin\\')")
p.write_text(text, encoding="utf-8")

# 7) Serve /refer inside the dashboard shell and claim registration referrals on normal dashboard boot.
p = SRC / "webapp.py"
text = p.read_text(encoding="utf-8")
text = text.replace("from .referral_ui import referral_html", "from .referral_ui import dashboard_referral_html, referral_html")
account_marker = '''    account_marker = '<div id="account" class="view hidden">'\n    if account_marker in html and 'id="billing" class="view hidden"' not in html:\n        html = html.replace(account_marker, dashboard_billing_html() + account_marker, 1)\n    return html'''
account_new = '''    account_marker = '<div id="account" class="view hidden">'\n    if account_marker in html and 'id="billing" class="view hidden"' not in html:\n        html = html.replace(account_marker, dashboard_billing_html() + account_marker, 1)\n    if account_marker in html and 'id="referral" class="view hidden"' not in html:\n        html = html.replace(account_marker, dashboard_referral_html() + account_marker, 1)\n    return html'''
if account_marker not in text:
    raise SystemExit("dashboard html injection marker not found")
text = text.replace(account_marker, account_new, 1)
text = text.replace(
'''async def referral_page(request: Request):\n    try:\n        user=_auth_user(request)\n    except Exception:\n        return RedirectResponse("/dashboard",status_code=302)\n    referral_code=str(request.cookies.get("lucas_ref") or "").strip()\n    if referral_code:\n        gateway.billing.referrals.claim(user.id,referral_code)\n    return HTMLResponse(referral_html(gateway.billing.referrals.summary(user.id)),headers={"X-Robots-Tag":"noindex,nofollow"})''',
'''async def referral_page(request: Request):\n    try:\n        user=_auth_user(request)\n    except Exception:\n        return RedirectResponse("/dashboard",status_code=302)\n    referral_code=str(request.cookies.get("lucas_ref") or "").strip()\n    if referral_code:\n        gateway.billing.referrals.claim(user.id,referral_code)\n    return HTMLResponse(_dashboard_html(),headers={"X-Robots-Tag":"noindex,nofollow,noarchive"})''')
text = text.replace(
'''async def api_nodes(request: Request):\n    user = _auth_user(request)\n    authorized_nodes = await gateway.registry.list(user)''',
'''async def api_nodes(request: Request):\n    user = _auth_user(request)\n    referral_code=str(request.cookies.get("lucas_ref") or "").strip()\n    if referral_code:\n        gateway.billing.referrals.claim(user.id,referral_code)\n    authorized_nodes = await gateway.registry.list(user)''')
p.write_text(text, encoding="utf-8")

# 8) Update/add regression tests.
p = ROOT / "tests" / "test_referrals.py"
text = p.read_text(encoding="utf-8")
text = text.replace("from gpt_windows_connector.referrals import REFERRAL_REWARD_REQUESTS, ReferralService", "from gpt_windows_connector.referrals import REFERRAL_PAID_REWARD_REQUESTS, REFERRAL_SIGNUP_REWARD_REQUESTS, ReferralService")
text = text.replace("    assert service.claim(\"friend\", code)\n    assert not service.claim(\"friend\", code)", "    assert service.claim(\"friend\", code)\n    with sqlite3.connect(path) as db:\n        referrer_signup = db.execute(\"SELECT bonus_requests FROM subscriptions WHERE user_id='referrer'\").fetchone()[0]\n        friend_signup = db.execute(\"SELECT bonus_requests FROM subscriptions WHERE user_id='friend'\").fetchone()[0]\n    assert referrer_signup == friend_signup == REFERRAL_SIGNUP_REWARD_REQUESTS == 1000\n    assert not service.claim(\"friend\", code)")
text = text.replace("assert bonus == REFERRAL_REWARD_REQUESTS == 3000", "assert bonus == REFERRAL_SIGNUP_REWARD_REQUESTS + REFERRAL_PAID_REWARD_REQUESTS == 11000")
text = text.replace("assert summary[\"reward_requests\"] == 3000", "assert summary[\"signup_reward_requests\"] == 1000\n    assert summary[\"paid_reward_requests\"] == 10000")
p.write_text(text, encoding="utf-8")

(ROOT / "tests" / "test_referral_dashboard.py").write_text('''from gpt_windows_connector.referral_ui import dashboard_referral_html\nfrom gpt_windows_connector.web_assets import DASHBOARD_HTML\n\n\ndef test_referral_nav_is_present_between_account_and_billing():\n    account = DASHBOARD_HTML.index('data-view=\"account\"')\n    referral = DASHBOARD_HTML.index('data-view=\"referral\"')\n    billing = DASHBOARD_HTML.index('data-view=\"billing\"')\n    assert account < referral < billing\n    assert 'Refer & Earn' in DASHBOARD_HTML\n\n\ndef test_dashboard_referral_contract():\n    html = dashboard_referral_html()\n    assert 'id=\"referral\"' in html\n    assert '1,000 bonus Requests' in html\n    assert '10,000 bonus Requests' in html\n    assert '/api/referrals/summary' in DASHBOARD_HTML\n    assert "referral:'/refer'" in DASHBOARD_HTML\n''', encoding="utf-8")

print("Referral dashboard migration applied")

from __future__ import annotations

from html import escape


def referral_html(summary: dict) -> str:
    code = escape(str(summary.get("code") or ""))
    url = escape(str(summary.get("url") or ""))
    paid = int(summary.get("paid_referrals") or 0)
    pending = int(summary.get("pending_referrals") or 0)
    earned = int(summary.get("earned_requests") or 0)
    reward = int(summary.get("reward_requests") or 3000)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Refer & Earn · Lucas</title>
<link rel="icon" type="image/png" sizes="32x32" href="/assets/lucas-logo-square.png?v=20260908" />
<link rel="shortcut icon" type="image/png" href="/assets/lucas-logo-square.png?v=20260908" />
<style>
body{{margin:0;background:#070a12;color:#f5f7ff;font:15px/1.5 Inter,system-ui,sans-serif}}
.wrap{{max-width:920px;margin:0 auto;padding:42px 22px}} .card{{background:#101521;border:1px solid #242c3b;border-radius:18px;padding:22px;margin-top:16px}}
h1{{font-size:36px;margin:0 0 8px}} .muted{{color:#9ca8bd}} .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.metric{{font-size:30px;font-weight:700;margin-top:5px}} input{{width:100%;box-sizing:border-box;background:#090d16;color:#fff;border:1px solid #30394b;border-radius:10px;padding:12px}}
button,a.btn{{background:#5b7cff;color:#fff;border:0;border-radius:10px;padding:11px 15px;font-weight:650;text-decoration:none;display:inline-block;cursor:pointer}}
.row{{display:flex;gap:10px;align-items:center}} .row input{{flex:1}} @media(max-width:700px){{.grid{{grid-template-columns:1fr}}.row{{display:block}}.row button{{margin-top:10px;width:100%}}}}
</style></head><body><main class="wrap">
<a class="btn" href="/dashboard">← Dashboard</a>
<div class="card"><h1>Refer & Earn</h1><p class="muted">Invite a friend to Lucas. When they become a paying customer, you earn <b>{reward:,} bonus Requests</b>.</p>
<div class="row"><input id="refUrl" readonly value="{url}"><button onclick="copyRef()">Copy invite link</button></div>
<p class="muted">Referral code: <b>{code}</b>. Rewards are issued once per referred user after their first successful paid invoice.</p></div>
<div class="grid">
<div class="card"><div class="muted">Paid referrals</div><div class="metric">{paid}</div></div>
<div class="card"><div class="muted">Pending referrals</div><div class="metric">{pending}</div></div>
<div class="card"><div class="muted">Requests earned</div><div class="metric">{earned:,}</div></div>
</div></main><script>async function copyRef(){{const e=document.getElementById('refUrl');try{{await navigator.clipboard.writeText(e.value);event.target.textContent='Copied'}}catch{{e.select();document.execCommand('copy')}}}}</script></body></html>"""

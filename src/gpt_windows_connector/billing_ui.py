from __future__ import annotations

from .web_document import TRACKING_HEAD
from .web_i18n_runtime import I18N_SCRIPT


def pricing_html() -> str:
    """Public Beta pricing: a single free plan, no paid checkout links."""
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Lucas is free during Beta."><title>Lucas Beta — Free During Testing</title><style>body{margin:0;background:#080c18;color:#f6f8ff;font:16px/1.6 system-ui,sans-serif}nav{display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:#080c18;z-index:10;padding:24px 6%;border-bottom:1px solid #263047}a{color:inherit;text-decoration:none}main{max-width:680px;margin:75px auto;padding:0 22px;text-align:center}h1{font-size:clamp(36px,6vw,60px);line-height:1.1}.card{background:#141c30;border:1px solid #334363;border-radius:20px;padding:34px;text-align:left}.price{font-size:46px;font-weight:800}.cta{display:block;background:#6473f4;color:white;padding:14px;text-align:center;border-radius:10px;font-weight:700}li{margin:10px 0}.muted{color:#b5c0d8}</style></head><body><nav><a href="/">Lucas</a><a href="/dashboard">Sign in</a></nav><main><h1>Free during Beta</h1><p class="muted">Lucas is free to use while we test and improve the product. Plans and limits may change after Beta.</p><section class="card"><h2>Lucas Beta</h2><div class="price">$0 <small style="font-size:16px">/ month</small></div><ul><li>100,000 Operations per month</li><li>3 Computers</li><li>3 AI accounts</li><li>Multiple concurrent tasks</li><li>Full Lucas execution</li><li>No additional Lucas token fees</li></ul><a class="cta" href="/dashboard?signup=1">Start Free Beta</a></section><p class="muted">Operations are separate from model tokens. Your AI provider’s plan and usage limits still apply.</p></main></body></html>''').replace('<head>', '<head>'+TRACKING_HEAD, 1).replace('</body>', I18N_SCRIPT + '<script>localizeWeb()</script></body>')


def dashboard_billing_html() -> str:
    """Beta usage view; no purchase controls or legacy paid plan cards."""
    return '''<div id="billing" class="view hidden">
      <div class="top"><div><h2>Lucas Beta</h2>
      <p class="muted">Free during testing. 100,000 Operations/month, 3 Computers, 3 AI accounts. Plans and limits may change.</p></div></div>
      <div id="billingNotice" class="card hidden" style="margin-bottom:16px"></div>
      <div id="billingError" class="error hidden"></div>
      <div class="card" style="margin-bottom:16px"><div style="display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap">
        <div><div class="muted">Current plan</div><div id="billingPlan" class="metric">Lucas Beta</div><div id="billingRenew" class="muted"></div></div>
        <div id="billingPrice" style="font-size:22px;font-weight:750">$0</div>
      </div></div>
      <div class="grid" style="margin-bottom:22px">
        <div class="card"><div class="muted">Operations</div><div id="billingRequests" class="metric">—</div><div id="billingRequestsBar" style="height:7px;background:#eef1f5;border-radius:999px;margin-top:12px;overflow:hidden"><i style="display:block;height:100%;width:0;background:#155eef"></i></div></div>
        <div class="card"><div class="muted">Computers</div><div id="billingComputers" class="metric">—</div></div>
        <div class="card"><div class="muted">AI accounts</div><div id="billingAi" class="metric">—</div></div>
      </div>
      <p class="muted">Beta Notice: Plans, pricing, and limits may change during Beta.</p>
    </div>'''

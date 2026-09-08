from __future__ import annotations


def legal_html(title: str, body: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" type="image/png" href="/assets/lucas-logo-square.png?v=20260908"><title>{title} · Lucas</title><style>body{{margin:0;background:#05070d;color:#e8edf7;font:16px/1.75 Inter,system-ui,sans-serif}}main{{max-width:860px;margin:auto;padding:56px 28px 90px}}a{{color:#91a7ff}}h1,h2{{color:#fff}}.muted{{color:#9aa4bb}}nav{{margin-bottom:48px}}section{{margin:32px 0}}</style></head><body><main><nav><a href="/">← Lucas</a></nav><h1>{title}</h1>{body}<p class="muted">Last updated: September 8, 2026</p></main></body></html>'''


def privacy_html() -> str:
    return legal_html("Privacy Policy", '<p>Lucas connects AI clients to computers you explicitly authorize. Lucas stores account, subscription, connection metadata, usage counters and audit records needed to operate the service.</p><section><h2>Computer data</h2><p>Files, terminal output, browser state and desktop content are accessed only when an authorized AI action requests them. Local computer permissions and Allowed Folders remain enforced by the Lucas Node.</p></section><section><h2>Security</h2><p>Passwords are hashed, web sessions use secure authentication, and computer access requires local authorization. Keep your Lucas account and connected computers secure.</p></section><section><h2>Contact</h2><p>Privacy questions: <a href="mailto:support@lucasmcp.com">support@lucasmcp.com</a>.</p></section>')


def terms_html() -> str:
    return legal_html("Terms of Service", '<p>By using Lucas you agree to use it only on computers, accounts, files and services you are authorized to access.</p><section><h2>Acceptable use</h2><p>You are responsible for actions executed through your connected AI clients and computers. Do not use Lucas for unlawful access, abuse, malware, credential theft or harm to others.</p></section><section><h2>Service</h2><p>Lucas is an evolving service. Features, limits and supported platforms may change. Paid plan limits and prices shown at checkout control the applicable subscription.</p></section><section><h2>Account</h2><p>You are responsible for maintaining account and local computer security and reviewing permissions granted to connected AI clients.</p></section>')


def refund_html() -> str:
    return legal_html("Refund & Cancellation Policy", '<p>Subscriptions can be managed or cancelled from Plan & Billing. Cancellation stops future renewal and normally remains effective through the current paid billing period.</p><section><h2>Refunds</h2><p>If you believe you were charged incorrectly or the service did not work as purchased, contact <a href="mailto:support@lucasmcp.com">support@lucasmcp.com</a> with the account email and charge date. Refund requests are reviewed based on the circumstances and applicable law.</p></section><section><h2>Plan changes</h2><p>Upgrades may be prorated by Stripe. Downgrades can be scheduled for the next billing cycle.</p></section>')


def contact_html() -> str:
    return legal_html("Contact Lucas", '<p>For product support, billing questions, security reports or partnership inquiries, email <a href="mailto:support@lucasmcp.com">support@lucasmcp.com</a>.</p><p>Please do not send passwords, access tokens or other secrets by email.</p>')

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing marker: {label}")
    return text.replace(old, new, 1)


# Billing: exact annual totals and safe stripe interval lookup.
p = "src/gpt_windows_connector/billing.py"
s = read(p)
if "ANNUAL_TOTALS" not in s:
    s = once(s, "from .referrals import ReferralService\n", "from .referrals import ReferralService\n\nANNUAL_TOTALS = {\"pro\": 99.99, \"pro_plus\": 199.99, \"expansion\": 149.99}\n", "billing constants")
start = s.index("    def summary(self,user_id: str) -> dict[str,Any]:")
end = s.index("    def _require_checkout_configured", start)
summary = '''    def summary(self,user_id: str) -> dict[str,Any]:
        ent=snapshot(self.db_path,user_id); out=ent.as_dict(); out['billing_configured']=self.checkout_configured; out['webhook_configured']=self.webhook_configured
        with self._connect() as db:
            row=db.execute('SELECT billing_customer_id,stripe_subscription_id,stripe_price_id,scheduled_plan FROM subscriptions WHERE user_id=?',(user_id,)).fetchone()
        out['has_customer']=bool(row and row['billing_customer_id']); out['has_subscription']=bool(row and row['stripe_subscription_id']); out['scheduled_plan']=row['scheduled_plan'] if row else None
        stripe_price_id=str((row['stripe_price_id'] if row else '') or '')
        annual_ids={self.price_pro_annual,self.price_pro_plus_annual}
        interval='year' if stripe_price_id and stripe_price_id in annual_ids else 'month'
        out['billing_interval']=interval
        out['annual_billing_configured']=self.annual_checkout_configured
        monthly=float(PLANS[ent.plan]['price'])+ent.expansion_quantity*float(EXPANSION['price'])
        out['monthly_price']=round(monthly,2)
        if interval=='year':
            annual_total=float(ANNUAL_TOTALS.get(ent.plan,0.0))+ent.expansion_quantity*float(ANNUAL_TOTALS['expansion'])
            out['billing_total']=round(annual_total,2)
            out['monthly_equivalent']=round(annual_total/12,2)
        else:
            out['billing_total']=round(monthly,2)
            out['monthly_equivalent']=round(monthly,2)
        return out

'''
s = s[:start] + summary + s[end:]
write(p, s)

# Pricing UI must match Stripe annual products and truthful discount language.
for p in ["src/gpt_windows_connector/web_billing_runtime.py", "src/gpt_windows_connector/billing_ui.py"]:
    s = read(p)
    for old, new in [("$95.90", "$99.99"), ("$191.90", "$199.99"), ("$143.90", "$149.99"), ("Save 20%", "Save ~17%"), ("save 20%", "save ~17%")]:
        s = s.replace(old, new)
    write(p, s)

# Production-safe admin bootstrap: only configured owner becomes super_admin.
p = "src/gpt_windows_connector/auth.py"
s = read(p)
old = '''            configured_admin = os.getenv("GWC_SUPER_ADMIN_EMAIL", "").strip().lower()
            if configured_admin:
                db.execute("UPDATE users SET role='super_admin' WHERE email=? COLLATE NOCASE", (configured_admin,))
            if not db.execute("SELECT 1 FROM users WHERE role IN ('admin','super_admin') LIMIT 1").fetchone():
                first = db.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1").fetchone()
                if first:
                    db.execute("UPDATE users SET role='super_admin' WHERE id=?", (first["id"],))
'''
new = '''            configured_admin = os.getenv("GWC_SUPER_ADMIN_EMAIL", "").strip().lower()
            if configured_admin:
                db.execute("UPDATE users SET role='super_admin' WHERE email=? COLLATE NOCASE", (configured_admin,))
'''
s = once(s, old, new, "auth init fallback")
old = '''        with self._connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE role IN ('admin','super_admin') LIMIT 1").fetchone():
                db.execute("UPDATE users SET role='super_admin' WHERE id=?", (user_id,))
        return self.get_user(user_id)
'''
new = '''        with self._connect() as db:
            configured_admin = os.getenv("GWC_SUPER_ADMIN_EMAIL", "").strip().lower()
            if configured_admin and email == configured_admin:
                db.execute("UPDATE users SET role='super_admin' WHERE id=?", (user_id,))
        return self.get_user(user_id)
'''
s = once(s, old, new, "register fallback")
s = once(s, old, new, "google fallback")
write(p, s)

# Referral attribution and readiness are delegated to small modules so gateway stays an orchestrator.
p = "src/gpt_windows_connector/gateway.py"
s = read(p)
if "from .gateway_readiness import" not in s:
    s = once(s, "from .task_runs import TaskRunStore\n", "from .task_runs import TaskRunStore\nfrom .gateway_readiness import readiness_checks, critical_ready\nfrom .gateway_referral import claim_referral_cookie\n", "gateway helper imports")
s = once(s, '        auth.audit(user.id, "auth.register")\n        response = JSONResponse', '        auth.audit(user.id, "auth.register")\n        claim_referral_cookie(request, billing.referrals, user.id)\n        response = JSONResponse', "register referral")
s = once(s, '        auth.audit(user.id, "auth.email_verified")\n        response = JSONResponse', '        auth.audit(user.id, "auth.email_verified")\n        claim_referral_cookie(request, billing.referrals, user.id)\n        response = JSONResponse', "verify referral")
s = once(s, '        auth.audit(user.id, "auth.google_login")\n        response = RedirectResponse', '        auth.audit(user.id, "auth.google_login")\n        claim_referral_cookie(request, billing.referrals, user.id)\n        response = RedirectResponse', "google referral")
health_start = s.index("async def health(_: Request):")
health_end = s.index("\n\nasync def browser_events_websocket", health_start)
health = '''async def health(_: Request):
    try: version=importlib.metadata.version("gpt-windows-connector")
    except importlib.metadata.PackageNotFoundError: version="unknown"
    checks=readiness_checks(db_path,settings,billing,email_verification_enabled); ready=critical_ready(checks)
    return JSONResponse({"ok":ready,"version":version,"online_nodes":len(registry.nodes),"auth":"multi-user","checks":checks},status_code=200 if ready else 503)
'''
s = s[:health_start] + health + s[health_end:]
# Remove two obsolete architecture comments now documented in README/ARCHITECTURE.
s = s.replace('    # Do not preflight every operation with a separate workspace.info RPC. The\n    # Windows Node is the final security authority and Executor._prepare_call()\n    # validates local approval, Allowed Folders and the workspace immediately\n    # before the requested operation. A Gateway preflight only duplicated that\n    # check, added a full network round trip, and could block for up to 180s.\n', '')
write(p, s)

# Legal/support routes, sitemap entries, and footer links.
p = "src/gpt_windows_connector/webapp.py"
s = read(p)
if "from .legal_ui import" not in s:
    s = once(s, "from .entitlements import active_node_ids, ensure_node_capacity, set_active_node\n", "from .entitlements import active_node_ids, ensure_node_capacity, set_active_node\nfrom .legal_ui import privacy_html, terms_html, refund_html, contact_html\n", "legal import")
if "async def privacy_page" not in s:
    handlers = '''\n\nasync def privacy_page(_: Request): return HTMLResponse(privacy_html())
async def terms_page(_: Request): return HTMLResponse(terms_html())
async def refund_page(_: Request): return HTMLResponse(refund_html())
async def contact_page(_: Request): return HTMLResponse(contact_html())
'''
    s = once(s, "\n\nasync def pricing_page(_: Request):", handlers + "\n\nasync def pricing_page(_: Request):", "legal handlers")
route = '    Route("/pricing", pricing_page, methods=["GET"]),\n'
if 'Route("/privacy"' not in s:
    s = once(s, route, route + '    Route("/privacy", privacy_page, methods=["GET"]),\n    Route("/terms", terms_page, methods=["GET"]),\n    Route("/refunds", refund_page, methods=["GET"]),\n    Route("/contact", contact_page, methods=["GET"]),\n', "legal routes")
if "https://lucasmcp.com/privacy" not in s:
    s = s.replace("</urlset>", '  <url><loc>https://lucasmcp.com/privacy</loc><priority>0.3</priority></url>\n  <url><loc>https://lucasmcp.com/terms</loc><priority>0.3</priority></url>\n  <url><loc>https://lucasmcp.com/refunds</loc><priority>0.3</priority></url>\n  <url><loc>https://lucasmcp.com/contact</loc><priority>0.4</priority></url>\n</urlset>', 1)
if 'href="/privacy">Privacy</a>' not in s:
    s = s.replace('{seo_copy}</body>', '{seo_copy}<footer style="max-width:980px;margin:0 auto;padding:0 28px 42px;color:#7f8aa1;font:13px Inter,system-ui,sans-serif"><a style="color:inherit;margin-right:18px" href="/privacy">Privacy</a><a style="color:inherit;margin-right:18px" href="/terms">Terms</a><a style="color:inherit;margin-right:18px" href="/refunds">Refunds</a><a style="color:inherit" href="/contact">Contact</a></footer></body>', 1)
write(p, s)

print("prelaunch migration applied")

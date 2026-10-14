# Lucas PRD V2.1 implementation and acceptance

Updated: 2026-10-12. Target branch: staging. Node package: 1.7.55; extension: 2.1.0.

This is a trace of implementation and evidence, not a production acceptance declaration.

| Requirement | Implementation | Evidence / remaining gate |
|---|---|---|
| Free Beta pricing and visible Pricing navigation | billing_ui.py, entitlements.py, billing.py | Beta tests cover new/existing plans; paid checkout, expansion and billing portal changes blocked server-side; historical records preserved |
| 100,000 OP/month, 3 active computers, 3 AI accounts | entitlements.py, web_billing_runtime.py | Quota/device/account regression suite; existing explicitly granted admin bonuses remain supported |
| Registration CTA and language detection | billing_ui.py, web_core_runtime.py, web_i18n_runtime.py | Pricing register link, Chinese strings and sticky nav tested; visual acceptance still required |
| Authorized browser extension | extensions/lucas-browser, browser_extension.py, executor.py | Real local WebSocket tests cover pairing, owner isolation, expiry, revocation and disconnect; real Chromium integration passed in GitHub CI |
| Background browser operations | extension background.js | Navigation, inspection, observation, click/type/select/scroll, upload, screenshots and HTTP(S) link downloads implemented; real Chromium runtime test passed in GitHub CI |
| Manual verification handoff | extension background.js; browser.handoff | No CAPTCHA/passkey solver and no automatic tab activation; unsupported exports and new-tab grants return a handoff |
| No mandatory isolated Profile | gateway.py, browser.py | ALI/Eva hard-coded target removed; explicitly selected CDP remains supported; CDP failure never restarts browser |
| Existing user browser preservation | browser.close | CDP disconnect does not close existing context/browser; regression test |
| Windows local Node, updates, reconnect and Allowed Folders | existing Node/installer + executor.py | Regression suite; Windows tray pairing UI and actual Node update require Windows acceptance |
| Source, agent, task, session, approval and result audit | auth.py, oauth.py, gateway.py, node.py, security.py | OAuth client ID comes from verified signed token; task/session propagated; local approval outcomes recorded; secrets and payload text excluded |
| Staging then approved production release | PROJECT_RULES.md, CI and smoke_web_pages.py | Production release remains blocked until CI, deployed staging smoke and explicit production confirmation |
| Existing Stripe subscriptions | Existing billing summary warning and retained records | Live subscription audit/handling still required. Free Beta does not automatically cancel or pause already active Stripe subscriptions |
| macOS | PRD explicitly marks this as planned | Not part of current Windows P0 acceptance |

## Install and pair

1. Upgrade the test Windows Node from the staging source (production installer still follows main until the production release is approved).
2. Download `/download/Lucas-Browser.zip` from the deployed staging server, or load `extensions/lucas-browser` from this checkout with Chrome/Edge **Load unpacked**.
3. Open **Browser** in local Lucas Settings, copy the pairing token, and paste it into the extension popup. Default loopback port: 8766. The token is local-only and must not be shared with an AI or website.
4. Choose a Lucas account already approved on that Node, then click **Allow AI in this tab**. There is no forced Profile. The grant covers one HTTP(S) tab and expires after 8 hours or socket disconnect.
5. AI uses `browser_tool(action="extension_sessions")` to get its own session ID. Normal browser actions use that session ID. Revoking in the popup or closing the tab removes control. `close` ends automation without closing the user's tab.

The extension requires Chromium 116+ and the debugger API. Chrome displays its normal debugger indicator. ixBrowser support depends on whether that engine permits MV3 extensions and the debugger API; it needs its own live acceptance. The local bridge never binds a public address.

HTTP(S) download links use the tab's authenticated fetch and are limited to 20 MiB. CORS restrictions, button-driven exports, larger transfers and new-tab authorization require manual handoff; the extension never changes the user's global download directory. Upload/download paths are checked against the Node's Allowed Folders.

## Verification

- `python -m pytest -q`: normal regression suite and real loopback bridge tests.
- `RUN_EXTENSION_E2E=1 CHROME_BIN=/path/to/chrome python -m pytest -q tests/test_extension_chromium.py`: actual installed extension with raw CDP, including upload/download, screenshots, authorization and foreground-tab preservation. No Playwright automation is used by this test.
- `python -m compileall -q src` and `node --check` on both extension scripts.
- Build a wheel and confirm all five extension files are packaged.
- `python scripts/smoke_web_pages.py <deployed-staging-url>` before production.

Local verification result: **175 passed, 4 skipped**. The 28 user-visible HTTP routes passed against an isolated local server. Extension JavaScript syntax and wheel packaging passed. Browser rendering and deployed endpoints have separate gates.

## CI verification

Functional commit `e68257135223e82ae96e888dfc9407aff7fcbe0e` passed the real extension integration on Chromium in [CI run 38302416394](https://github.com/Neal86/Lucas/actions/runs/38302416394). This exercised real DOM reads/clicks/types/select/scroll, file upload/download, full-page and background screenshots, account isolation, navigation and tab revocation. Browser integration runs through direct CDP without Playwright automation. Windows and Linux regression results are recorded by the same workflow.

## Current environment gates

The local execution sandbox denies Chromium's Unix socket creation, so real browser integration cannot be completed here. Coolify project inspection returned HTTP 401 Unauthenticated, blocking deployed staging verification and live subscription review. These must not be reported as passing.

## Development acceptance: atomic OAuth admission (2026-10-14)

Based on staging `98919dd4dc329a8751771c026e58f0af159fc634`; proposed in a separate development branch, not deployed. This closes a concurrency gap in acceptance criterion 4 (AI-account enforcement agrees with the dashboard) and the security/reliability requirement.

- Consent and refresh-token admission now check capacity and insert the account relationship under one SQLite `BEGIN IMMEDIATE` transaction. Competing gateway workers cannot both claim the last available AI-account slot.
- Consent requests and authorization codes are consumed once under a write transaction. Concurrent repeat clicks or code exchanges cannot issue duplicate grants. Invalid client, redirect, or PKCE attempts do not consume a valid code.
- Existing authorized clients can reconnect/refresh at the limit. Beta's three-account limit, legacy paid limits, admin bonuses and bonus expiry still use the same entitlement calculation. No schema migration, subscription mutation, browser/Profile requirement, local permission change or production deployment is included.
- Entitlement helpers accept a caller-owned connection without committing it. Failed grant inserts roll back the new account relationship and preserve retryable consent.
- CI now also runs for pull requests targeting `staging`, so this development path receives the existing Linux/Windows matrix and real Chromium extension check.

Evidence:

- The four core race tests in `tests/test_oauth_concurrency.py` were run against unchanged staging first: **4 failed**, demonstrating over-limit admission and duplicate consent/code issuance.
- Final local Linux/Python 3.12 regression suite: **190 passed, 4 skipped**. All **15** new OAuth concurrency, replay, cancellation, invalid-PKCE/client/redirect, rollback, quota and bonus cases passed.
- Python compilation, both extension JavaScript syntax checks and Git whitespace checks passed.
- `scripts/smoke_web_pages.py` passed all **28 routes** against an isolated local HTTP server. This is not deployed-staging evidence or visual/browser acceptance.
- The four default skips are the optional browser smoke, two Windows PowerShell tests, and opt-in real extension integration. A separate real Chromium attempt failed before the browser started because this sandbox denies its process-singleton socket (`Operation not permitted`). The check is not counted as passing; exact-commit CI must establish Linux Chromium and Windows results.
- Independent code review found no blocking defects; production release still requires deployed staging smoke, existing-subscription audit/handling, Windows Node/browser acceptance and explicit confirmation.

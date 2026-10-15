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
| Source, agent, task, session, approval and result audit | auth.py, oauth.py, gateway.py, node.py, security.py, task_audit.py | Verified OAuth identity, task/session and approval outcomes retained; raw sub-operation commands excluded from stored/displayed task steps |
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

## Development acceptance: OAuth disconnect revocation (2026-10-15)

Follow-on to the atomic-admission change, based on draft PR #3 head
`88ea02b2b3ccbbd420c2aff83562402f23c11ddb`. This implements the Security and
Reliability requirement that an AI connection cannot keep operating after the
user disconnects it. These are code/test results, not deployed acceptance.

- `oauth_grants.py` owns durable per-user/per-client revocation generations.
  Signed OAuth access tokens carry the current generation. Authentication
  requires both an active connection and the matching generation, so Disconnect
  blocks subsequent authenticated requests immediately. Reconnecting the same
  client never restores its old access tokens. Browser-login tokens and other
  users/clients remain unaffected. Already-dispatched operations and existing
  `/ws/events` subscriptions are not cancelled; new WebSocket handshakes are checked.
- The dashboard increments the generation and removes ownership, codes, refresh
  tokens and metadata in one transaction. Tombstones remain after reconnect.
- Code redemption and refresh rotation validate, consume, issue replacements and
  sign access tokens in one SQLite write transaction. An in-flight exchange
  cannot recreate a disconnected relationship. Failed insertion/signing rolls
  back consumption and replacement grants so the caller can retry.
- Refresh retries retain the existing 30-second grace period, anchored to the
  first rotation. Replaying a refresh token cannot extend that window indefinitely.
- No routes, Beta limits/pricing, browser/Profile policy, device permissions,
  billing records or deployment settings change.

### Compatibility and migration

- AuthStore initialization additively creates `oauth_revocations`; no existing
  tables/records are dropped, rewritten or bulk-revoked. Startup is idempotent.
- Existing signed OAuth access tokens without the generation claim are treated
  as generation zero. They continue working for currently authorized connections
  until that connection is disconnected under the new code. Existing valid
  refresh tokens continue working and receive generation-bound replacements.
- An access token for an absent connection is rejected even without a tombstone.
  Fresh authorization is required after disconnect; it receives the next
  generation. Revocation state survives gateway restart.
- All gateway workers must run the new version for the guarantee to hold. An
  older binary ignores revocation generations and still has the issuance race;
  a rollback or mixed-version rollout must not be described as preserving this
  security fix. Production rollout/migration has not been run or authorized here.

### Verification

- Seven new regressions failed against the unchanged PR #3 baseline, demonstrating
  usable disconnected tokens, token revival, both grant/disconnect races,
  indefinitely sliding refresh grace and grant loss after failed issuance.
- `tests/test_oauth_revocation.py`: **16 passed**, including migration from a
  pre-generation database, legacy tokens, repeated reconnect, user/client
  isolation, rollback, orphan grants, invalid scope/client and actual dashboard
  and MCP authentication rejection.
- Local Linux/Python 3.12 full suite: **206 passed, 4 skipped**. Python compilation,
  both extension JavaScript syntax checks and Git whitespace checks passed.
- The isolated local HTTP smoke passed **28/28 routes**. This is not a deployed
  staging smoke result. Windows and real Chromium checks require the exact-head
  CI run linked in the PR before this follow-on is considered CI-verified.
- The prior release gates remain open: deployed staging smoke, live Windows
  Node/Edge/ixBrowser acceptance, existing Stripe subscription audit/handling and
  explicit production approval.

## Development acceptance: local policy and task-audit privacy (2026-10-15)

Based on PR #3 head `3b0dfc511cde48d50992096b97b1d4e415c79d25`.
This slice addresses acceptance criterion 5 and the local-authority/audit-privacy
requirements. No running Node configuration or device setting was changed.

### Behavior

- `domain_policy.py` computes the shared scope of machine and account domain
  grants. Parent domains include their descendants; `*.example.com` excludes
  the apex. Case and trailing-dot normalization are retained. Disjoint restricted
  lists produce an explicit deny-all policy rather than an unrestricted empty
  list. That marker survives subsequent intersections and Executor preflight.
- Configured grants must be a list/tuple of strings. Malformed containers or
  entries fail closed rather than becoming character-level or coerced host grants.
- Originally empty domain lists retain their unrestricted meaning. A configured
  domain restriction now rejects a detected network operation when its destination
  cannot be checked, such as a `git.push` without an identifiable destination or
  a non-host browser URL. This is intentionally fail-closed and may require a more
  explicit supported workflow under restrictive configurations.
- `process.start` and `shell.run` combine their primary operation policy with
  every detected software-installation, registry, service and high-risk gate.
  The strictest decision wins, including explicit blocks. A first matching
  category cannot hide a later blocked category in a compound command. Common
  Windows executable variants and PowerShell/cmd wrappers have regression coverage.
- An explicit `desktop_control=block` remains authoritative whether foreground
  confirmation is enabled or disabled, including UIA foreground fallback and
  visible browser launch. Existing non-blocked focus-toggle behavior is preserved.
- `task_audit.py` sanitizes TaskRunStore write and read boundaries. Each
  sub-operation is represented by the constant `shell.run`; command names,
  arguments, URLs, paths and literal values are never copied into that field.
  String-array shape, cardinality and separately recorded operation counts remain
  intact. Source, agent, task, device, session, approval, result and timing metadata
  remain available. Execution commands and internal accounting are not modified.

### Boundaries and compatibility

- These changes tighten source-code policy checks only; installing/updating a
  real Node and verifying its local prompt behavior remain release work.
- Command-risk and network-destination detection are conservative checks, not an
  exhaustive shell parser or operating-system sandbox/firewall. Indirect or
  obfuscated execution requires appropriate OS/network authority boundaries.
- Previously stored command details are projected safely on read without
  rewriting historical SQLite rows. Sensitive values may remain in historical
  databases/backups; removal requires separately authorized cleanup. The sanitizer
  covers `sub_operations`, not arbitrary user-entered metadata.
- No schema migration, API route change, live settings mutation, subscription
  action, billing/pricing change, required Eva/Profile isolation or deployment
  is included. Browser PR #2 remains separate; its corresponding policy paths
  still have the defects fixed here and must be reconciled without replacing
  the current OAuth or audit implementation wholesale.

### Verification

- Unchanged-baseline tests demonstrated **38 policy failures** and **13 audit
  privacy failures**, including actual Executor preflight and real SQLite
  persistence/display paths. No dangerous command or device action was executed.
- Review exposed a related malformed-configuration gap; all **12** added
  regressions failed before type validation and passed afterward.
- New focused suites: **87 passed**, covering domain intersection and 729
  domain/host truth-table combinations, compound risk/block precedence, focus
  blocks, raw database inspection, legacy non-mutation, malformed details and
  gateway success/error/runtime-trace paths with only execution dispatch stubbed.
- Final local Linux/Python 3.12 aggregate suite: **293 passed, 4 skipped**,
  including existing accounting, OAuth and Beta acceptance cases. Compilation,
  both extension JavaScript syntax checks and Git whitespace checks passed.
- Isolated local HTTP smoke: **28/28 routes passed**. Independent review found
  no blocking defects, independently passed the full suite, and passed a further
  **5,488-case** domain truth-table probe. Exact final Windows/Chromium CI evidence
  is recorded in the PR; local HTTP smoke is not deployed-staging acceptance.
- The production gates remain unchanged: deployed staging smoke, actual Windows
  Node/Edge/ixBrowser acceptance, existing-subscription handling and explicit
  production approval. Passing synthetic/stubbed policy tests does not satisfy
  those live acceptance gates.

## Development acceptance: shared password-login policy (2026-10-15)

Based on PR #3 head `5f4a06a934d8150953fe0e81b925b85379a2ca22`.
This slice closes the OAuth password-only login bypass and aligns the standalone
and composite gateways with the existing email-verification policy.

### Behavior and compatibility

- `login_policy.py` is the single implementation of password login, login-code
  verification and resend. Both gateway entry points and the OAuth browser UI
  use `/auth/login`, `/auth/login/verify` and `/auth/login/resend`. Password
  attempts share the existing 10-per-600-second IP/email bucket in each worker.
- A new/untrusted device receives HTTP 202 with `verification_required`,
  `challenge_id` and `email`, without an access cookie. A valid email code then
  sets the HttpOnly, SameSite=Lax access cookie (Secure on configured HTTPS).
  Remembered devices still require the password and the same network address;
  an address change invalidates remembered trust and requires a new code.
- **Standalone setup/API change:** direct use of
  `gpt_windows_connector.gateway:app` (or its module entry point) now fails closed
  with HTTP 503 when verification is required but SMTP is absent. The documented
  `gwc-gateway` command already targets the composite `server:main` and retains
  its verification policy.
  Configure `GWC_SMTP_HOST` and `GWC_SMTP_FROM`, plus the existing port/TLS and
  optional username/password settings from `.env.example`, before normal use.
  The already-supported explicit `GWC_BYPASS_LOGIN_VERIFICATION` development
  override remains recognized and audited; this patch does not enable it.
  Successful password/verification responses use `access_token: "cookie"`, as
  the composite server already did. Clients of the old standalone password-to-JWT
  response must handle the challenge and retain cookies. MCP OAuth clients still
  obtain their bearer tokens through the unchanged consent/PKCE token flow.
- `oauth_login_ui.py` supports password errors, code errors, remember choice,
  resend cooldown, Back and pre-authentication cancellation. It stores no password
  or code in browser storage and loads no external resources. Authentication
  returns only to the fixed same-origin resume route with an opaque request ID.
  Resume renders the existing explicit consent screen; signing in does not grant
  an AI connection. Cancellation atomically consumes the request and returns only
  to its previously validated registered redirect, preserving its original state.
- Old `/oauth/authorize/login` forms no longer authenticate submitted passwords.
  A valid old request renders the new sign-in flow so the user can restart safely;
  invalid/expired resume, cancel or legacy requests fail locally without redirect.
- The dashboard login-verification state is initialized in its own injected
  runtime rather than through a stale match against registration-state text.
  This fixes the reproduced `loginResendCooldownTimer` ReferenceError when a
  challenge starts and preserves the registration metadata state.
- No schema migration or token-format change is introduced. Existing web cookies,
  remembered-device rows, OAuth grants and tokens remain valid subject to their
  existing expiry/revocation checks, including sessions minted before this fix.
  This patch does not retrospectively reauthenticate or revoke those sessions.
  All serving workers must be upgraded to remove the old route bypass everywhere.

### Verification and remaining boundaries

- Before implementation, all three dedicated bypass regressions failed on the
  unchanged head: OAuth minted a cookie without email verification, the standalone
  gateway did so without SMTP, and alternating login routes escaped the limit.
- A separate rendered-JavaScript runtime regression reproduced the dashboard
  ReferenceError before the declaration fix. The final focused suite has
  **28 passing tests**, including actual gateway middleware/routes, new/trusted
  devices, changed networks, bad/expired/replayed codes, disabled accounts,
  resend rotation/limit, safe cancellation/resume, malformed input and old tokens.
- Final local Linux/Python 3.12 aggregate suite: **321 passed, 7 skipped**.
  Python compilation, both extension scripts and the OAuth script syntax checks,
  Git whitespace checks and isolated HTTP smoke (**28/28 routes**) passed.
  Independent review re-ran the aggregate suite and examined route/redirect and
  compatibility behavior. Exact-head CI is tracked in the PR.
- Three new opt-in real Chromium tests use real loopback HTTP, SQLite, password
  verification, cookies, consent and PKCE exchange. Only synthetic verification
  email delivery is captured instead of sent. They cover wrong passwords/codes,
  success, replay, Back/restart and cancellation before login/during a challenge.
  They run in CI with `RUN_LOGIN_E2E=1`; local Chromium startup was blocked by the
  environment's socket policy, while the real loopback HTTP flow was separately
  verified. This is **not** evidence of outbound email/provider delivery.
- Rate buckets remain process-local. Client IP still depends on the existing
  forwarded-header handling; trusted ingress must remove/overwrite untrusted
  `cf-connecting-ip`/`x-forwarded-for` headers. This is not a claim of a global
  distributed rate limit or hardened direct-to-gateway proxy trust.
- **Historical finding, addressed by the next slice below:** two independent `RegistrationSecurity`
  instances can concurrently accept one login code and create two trusted tokens.
  The reproduced interleaving reads the challenge before either write, then the
  second unchecked DELETE affects zero rows but still creates trust. Serializing
  validation, attempt accounting, code consumption and trust creation, including
  resend/verify races, was separate pending work at this head. Sequential replay was tested here;
  the authentication system is not claimed to be fully hardened by this slice.
- A separate inherited dashboard `showRegister` string replacement also misses
  the expanded registration function. Auth-mode switching while code verification
  was visible required dedicated UI reconciliation (implemented below); the timer/Back regression
  here does not claim to cover that mode-switch path.
- Beta pricing/navigation, historical billing data and non-mandatory browser
  Profile/Eva behavior are unchanged. Deployed staging smoke, live Windows Node,
  Edge/ixBrowser acceptance, existing Stripe subscription handling and explicit
  production approval remain outstanding release gates. No deployment occurred.


## Development acceptance: atomic email challenges and auth-mode transitions (2026-10-15)

Based on draft PR #3 head `7d1170c9a3898751ae17ad415c4fc419785c1c35`.
This closes the two follow-on findings recorded above. It is development
verification, not deployed staging or production acceptance.

### Challenge transaction boundaries

- Registration and login verification acquire a SQLite `BEGIN IMMEDIATE` writer
  transaction before reading a challenge. Validation, the five-attempt limit,
  consumption and user/trusted-device insertion are one transaction, including
  independent gateway workers sharing the database. Only one concurrent login
  verification can return success and receive access/trusted-device cookies.
- Resend uses the same writer boundary. If verification consumes a challenge
  first, resend fails instead of claiming to send a replacement for a deleted
  challenge. If resend wins, verification checks the new hash and rejects the old
  code. The latest committed resend/start code remains authoritative; outbound
  delivery order is outside the transaction.
- Registration hashes the password before taking the writer lock and then
  rechecks that the email has not been registered before upserting pending state.
  A start request waiting on hashing cannot recreate a consumed pending record
  after another worker finishes registering that account.
- Expiry is evaluated after the writer lock is acquired, so lock waiting cannot
  extend a code's validity. Wrong-code counters and login expiry/network-change
  invalidations still commit before their rejection errors. Unexpected write
  errors roll back the complete operation, preserving a retryable challenge and
  preventing partial user/trusted-device creation.
- Existing behavior is retained: registration resend can renew expired pending
  registration; login resend rejects expired challenges; resend resets attempts;
  successful remembered-device sessions retain their existing 30-day lifetime.
  No migration, token format, route or response-format change is introduced.

### Dashboard transitions

- `web_login_runtime.py` owns dashboard login/verification state and behavior.
  Composition no longer depends on replacing an outdated full `showRegister`
  function string. Mode switches and Back explicitly reset verification state.
- Pending challenge, entered code and resend timers are cleared when leaving a
  verification flow. Repeated submissions and late asynchronous responses are
  guarded so an old flow cannot replace a newer login/signup view. Login stays
  locked through dashboard boot. Initial boot and login-completion boot suppress
  stale `/auth/me`, refresh and 401-navigation effects after an auth-mode reset.
- These are browser-state safeguards. They do not revoke a code already issued
  by the server or cancel an authentication response already processed by the
  browser. Unused server challenges retain their normal expiry; no cancellation
  endpoint or retroactive session revocation is added.

### Verification boundaries

- Fail-before challenge regressions were run against the unchanged parent head
  with two independent service instances and a real temporary SQLite database.
  The tests cover duplicate login/registration acceptance, attempt limits,
  verify/resend ordering, registration start/verify, expiry after lock waiting,
  rollback and HTTP cookie issuance. Synthetic test email addresses and codes
  never leave the local test environment.
- Rendered-JavaScript tests and opt-in real Chromium dashboard tests cover
  interrupted/repeated login, Back, switching modes and late response handling.
  Chromium uses loopback HTTP and captured synthetic email delivery; it is not
  outbound SMTP/provider acceptance.
- SQLite still serializes database writers, with the existing 30-second timeout.
  This change does not implement distributed request-rate limits, ingress header
  trust, retries on database exhaustion, or whole-session cancellation.
- All serving workers must be upgraded to gain the atomicity guarantee. Existing
  cookies/tokens remain valid under their existing expiry/revocation rules.
- Beta pricing/navigation, historical billing and browser/Profile/Eva behavior
  are unchanged. Deployed staging smoke, live Windows Node/Edge/ixBrowser,
  existing Stripe subscription handling and explicit production approval remain
  release gates. No production data, device configuration or deployment changed.

### Final local evidence for this slice

- **19 challenge cases passed**, including deterministic cross-worker event gates;
  the unchanged parent failed **13** of those cases. Independent repeat runs
  reproduced the same fail-before result and passed the candidate repeatedly.
- **34 rendered dashboard runtime cases passed**; the unchanged parent failed
  **29**, including mode reset, late responses and dashboard boot transitions.
  The remaining cases protect compatibility, current errors and retry behavior.
- Real Chromium coverage adds two dashboard flows (English and Chinese) to the
  three existing OAuth cases. Local browser launch is blocked before page code
  executes by the sandbox's process-singleton socket policy. Exact-head CI must
  establish browser/Windows results; the PR records that run and its outcome.
- Final local Linux/Python 3.12 aggregate: **374 passed, 9 skipped**. Python
  compilation, rendered/extension JavaScript syntax and Git whitespace checks
  passed. Isolated local HTTP smoke passed **28/28 routes**. Default skips are
  the optional browser smoke, two Windows-only tests, the opt-in extension case
  and five opt-in OAuth/dashboard Chromium cases. Deployed staging was not tested.

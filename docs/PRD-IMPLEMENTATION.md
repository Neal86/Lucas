# Lucas PRD V2.1 implementation and acceptance

Updated: 2026-10-15. Target branch: staging. Node package: 1.7.55; extension: 2.1.0.

This is a trace of implementation and evidence, not a production acceptance declaration.

| Requirement | Implementation | Evidence / remaining gate |
|---|---|---|
| Free Beta pricing and visible Pricing navigation | billing_ui.py, entitlements.py, billing.py | Beta tests cover new/existing plans; paid checkout, expansion and billing portal changes blocked server-side; historical records preserved |
| 100,000 OP/month, 3 active computers, 3 AI accounts | entitlements.py, operation_admission.py, web_operation_usage_runtime.py | Atomic minimum admission, distinct completed/held usage and quota/device/account regressions; existing explicitly granted admin bonuses remain supported |
| Registration CTA, language detection and setup guidance | billing_ui.py, web_registration_runtime.py, web_i18n_runtime.py, node_docs_ui.py | Guarded registration flows and localized standalone guide; browser evidence below, deployed/device acceptance remains separate |
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
- `RUN_EXTENSION_E2E=1 CHROME_BIN=/path/to/chrome python -m pytest -q tests/test_extension_chromium.py`: actual installed extension with raw CDP, including upload/download, screenshots, authorization and foreground-tab preservation. Extension actions use raw CDP; the same isolated browser fixture also exercises the production Playwright-backed CDP fallback for password-observation redaction.
- `python -m compileall -q src` and `node --check` on every extension JavaScript file.
- Build a wheel and confirm the complete extension asset set is packaged.
- `python scripts/smoke_web_pages.py <deployed-staging-url>` before production.

Local verification result: **175 passed, 4 skipped**. The 28 user-visible HTTP routes passed against an isolated local server. Extension JavaScript syntax and wheel packaging passed. Browser rendering and deployed endpoints have separate gates.

## CI verification

Functional commit `e68257135223e82ae96e888dfc9407aff7fcbe0e` passed the real extension integration on Chromium in [CI run 38302416394](https://github.com/Neal86/Lucas/actions/runs/38302416394). This exercised real DOM reads/clicks/types/select/scroll, file upload/download, full-page and background screenshots, account isolation, navigation and tab revocation. Browser integration runs through direct CDP without Playwright automation. Windows and Linux regression results are recorded by the same workflow.

## Current environment gates

The local execution sandbox denies Chromium's Unix socket creation; exact-head GitHub CI provides the real Chromium evidence recorded below and on PR #3. The earlier Coolify HTTP 401 is historical: read-only access worked on 2026-10-15. The running app named Lucas-Staging is configured for main, with an image tagged f04f87af477ae77a14a5287d8f6a966b217111cb, not this development branch. Its test configuration bypasses login verification and has no SMTP, so it cannot establish production email-login acceptance. Deploying a reviewed commit to an explicitly approved, isolated staging target and checking its actual image/endpoints remain required. No deployment or live subscription handling was performed.

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

### Final-HTML correction discovered by real Chromium

- Exact-head CI run [38665194648](https://github.com/Neal86/Lucas/actions/runs/38665194648)
  for `eb75a459f4f804f34af5c6c808c5de4d778dd53a` passed the normal
  Linux/Windows suites, three OAuth browser cases and extension integration,
  but both new dashboard browser cases failed before the signup form appeared.
- Investigation reproduced two inherited assembly defects on the unchanged
  parent: dashboard runtime followed the closed i18n script without a new
  opening script tag, and server branding modified the landing component before
  its exact-match removal. The final dashboard rendered JavaScript as body text
  and retained the marketing landing. Syntax-only fragment checks missed this.
- The correction adds the runtime script boundary at composition and removes
  the dashboard's landing component before branding. Public-home composition
  remains separate. No route, authentication API, schema, permission, billing,
  persistent data or deployment behavior is changed.
- Regression checks parse the final server-composed HTML, require the complete
  runtime inside one executable script, reject unmatched script ends/body-text
  JavaScript, syntax-check all inline scripts together and separately, and check
  actual landing DOM exclusion while preserving public-home content. The
  unchanged parent fails three new assembly checks, with five controls passing.
- The failed CI run is retained as evidence. Browser acceptance requires the
  corrective commit's exact-head CI outcome; local syntax/unit checks alone do
  not establish real-browser success.
- Corrective local validation: **54 focused tests passed** and **377 passed,
  9 skipped** in the full suite. Python compilation, final-HTML JavaScript syntax,
  whitespace checks and isolated HTTP smoke **28/28 routes** passed. The public
  landing output is byte-identical to the parent. The smoke fixture had no
  super-admin account, so its separate readiness endpoint remained unavailable;
  these results establish page-route rendering, not deployment readiness.
- Independent corrective review passed **55 focused tests** and found no
  actionable source-level correctness/security/compatibility blockers. Real
  Chromium remains the final integration gate for this correction.

- Corrective exact-head [CI 38666160274](https://github.com/Neal86/Lucas/actions/runs/38666160274)
  passed for `da565636407bcf41a31012d836da722bb83046c4`: Linux Python
  3.11/3.12 each **377 passed, 9 skipped**, Windows Python 3.11 **379 passed,
  7 skipped**, real Chromium OAuth/dashboard **5 passed** and extension
  integration **1 passed**. Browser mail delivery remains synthetic only.

## Development acceptance: extension grant cancellation (2026-10-15)

Follow-on to PR #3 head `da565636407bcf41a31012d836da722bb83046c4`,
addressing the PRD requirement that local browser authorization stays explicit
and revocation cannot silently restore a cancelled tab grant. No real user
browser, device, credential, deployment or production data is changed.

- The unchanged extension could accept a late grant acknowledgement after
  Revoke all had completed, restoring a locally usable browser session. A
  deterministic runtime fixture reproduces the issue using the actual extension
  source, synthetic Chrome/WebSocket interfaces and no real browser or account.
- The fix isolates grant lifecycle state and cancellation from page actions,
  correlates grant requests with acknowledgements, binds work to its originating
  connection and prevents cancelled asynchronous setup from recreating access.
- Revocation prevents later command dispatch after asynchronous boundaries. It
  cannot undo a browser command already submitted to Chrome or reverse a page
  change that has already occurred.

### Compatibility and rollout boundaries

- No MCP route, database schema, pairing-token format, browser permission,
  Profile requirement or foreground-focus behavior changes. Existing approved
  account checks and tab-scoped grants remain authoritative.
- The updated extension requires a Node bridge that announces correlated grant
  acknowledgement support. With an older bridge, granting fails closed with an
  update message. The updated bridge retains legacy-extension compatibility;
  the cancellation guarantee requires updating the extension as well.
- The new lifecycle module must be present in both the extension ZIP and wheel
  assets. Pairing remains local-only, and reconnection never automatically
  authorizes a tab.

### Regression evidence and remaining acceptance

- **37 deterministic extension runtime cases passed**; the unchanged parent
  extension failed **29**, with **8** controls passing. The tests load the actual
  ES modules and cover cancellation before/after lookup and attachment, delayed
  acknowledgements, remote revoke, duplicate/mismatched replies, old sockets,
  overlapping pairing, timeouts, shared-tab owners and every multi-step command
  dispatch boundary. These are synthetic interface tests, not live Chrome.
- Independent review passed **21 interface-level probes** and the **37** runtime
  cases. It found no remaining actionable blocker after stale attachment-state
  and pending-acknowledgement revocation corrections. These extra state cases
  were deterministic fixtures, not additional live-browser demonstrations.
- Focused Python suite: **48 passed**. Full local Linux/Python 3.12 suite:
  **415 passed, 9 skipped**. Python compilation, extension/module/runtime-test
  JavaScript syntax and whitespace checks passed. Isolated HTTP page smoke:
  **28/28 routes passed**, without claiming deployed readiness.
- Built the wheel and generated the extension ZIP, then verified all **six**
  extension assets byte-for-byte against the final source, including the new
  lifecycle module. No extension store publication or device installation ran.
- The real Chromium integration now also verifies explicit revoke/re-grant,
  rejection of the old session and preservation of the unrelated foreground
  tab. Local Chromium launch remains sandbox-blocked; the PR records the
  published exact-head CI result for real-browser and Windows acceptance.
- Deployed staging, actual Windows Node/Edge/ixBrowser operation, existing Stripe
  subscription handling and explicit production approval remain release gates.
  PR #2 is a divergent browser implementation, not a prerequisite to merge
  wholesale: its additional capabilities require selective permission review.

- Exact-head [CI 38667864932](https://github.com/Neal86/Lucas/actions/runs/38667864932)
  passed for `84fd8e485acc59c56c2824181e1f0921f4ca173c`: Linux Python
  3.11/3.12 each **415 passed, 9 skipped**, Windows Python 3.11 **417 passed,
  7 skipped**, real Chromium extension **1 passed** and OAuth/dashboard
  **5 passed**. Extension acceptance includes revoke/re-grant and foreground-tab
  preservation; OAuth email delivery remains synthetic.

## Development acceptance: password-control observation redaction (2026-10-15)

The explicit CDP fallback now omits entered password-control values from the
structured `browser.observe` element text, matching the extension's protection.
Control identity, labels, type, visibility and disabled state remain available;
ordinary input values and page text retain their existing behavior. This does
not add arbitrary-page, screenshot or general sensitive-content redaction.

- The unchanged evaluator exposed a synthetic password through the actual
  Executor/observe path. Regression tests execute the production evaluator
  against synthetic controls and preserve account/session ownership checks.
- The existing isolated Chromium fixture connects an additional production CDP
  session to its test browser, observes real DOM controls, then detaches without
  closing the browser or changing foreground selection. No user browser or
  credentials are involved.
- No MCP response shape, route, schema, permissions, Profile requirements,
  pairing behavior, device configuration or deployment changes are made. Only
  the password control's text is withheld.
- Dedicated regression suite: **9 passed**, with **6 failing on the unchanged
  parent** and **3 compatibility controls passing**. Independent browser-focused
  verification passed **11 tests**, with the opt-in real Chromium integration
  explicitly skipped locally. Its extended fixture verifies both extension and
  production Playwright-backed CDP observation, including mixed-case password
  types, ownership checks and browser/foreground preservation after detach.
- Independent review found no remaining blocker. Real Chromium execution is
  pending published exact-head CI; local synthetic tests alone do not establish
  browser integration acceptance.

## Development acceptance: repeat computer activation (2026-10-15)

Re-activating an already active computer now synchronizes the active set inside
its existing SQLite transaction. The old branch opened a second writer while
holding its own write lock, so an ordinary repeated activation could wait until
SQLite raised `database is locked` instead of returning the selected computers.

- The unchanged real SQLite path reproduced the failure after its default
  **30-second timeout**. A regression fixture shortens only the test connection
  timeout and fails on that parent in **0.61 seconds**, without production
  timing changes or a live device.
- **27 dedicated transaction tests passed**, covering WAL and DELETE journals,
  repeat/stale requests, manual selection and eviction priority, bound-computer
  ownership, Beta/legacy/expansion limits, overrides and expiry, rollback, and
  HTTP audit/billing behavior after commit. Related activation/billing/admin/
  Beta/UI checks passed **44 tests**; independent activation/OAuth checks passed
  **53 tests** and found no remaining blocker.
- No response format, route, schema, entitlement limit, account binding,
  permission or deployment behavior changes. Existing manual choices and
  transaction rollback remain authoritative.

### Combined verification for the two fixes

- Full local Linux/Python 3.12 suite: **451 passed, 9 skipped**. Python
  compilation, extension JavaScript syntax and whitespace checks passed.
- Isolated HTTP page smoke: **28/28 routes passed**. This is a disposable local
  app fixture, not deployed staging or production readiness.
- Built the wheel and verified both corrected Python modules and all **six**
  extension assets byte-for-byte against source. No package publication or
  installation on a user computer was performed.
- Independent review passed **64 focused tests**, with **1** real Chromium test
  explicitly skipped locally. Windows and real Chromium acceptance remain
  pending the published exact-head CI result recorded on PR #3. Existing
  staging/device/subscription/production release gates remain open.

- Exact-head [CI 38669057105](https://github.com/Neal86/Lucas/actions/runs/38669057105)
  passed for `71eebf5ee9bc8fe6db263fd8009a5362cd8a6402`: Linux Python
  3.11/3.12 each **451 passed, 9 skipped**, Windows Python 3.11 **453 passed,
  7 skipped**, real Chromium extension/CDP-fallback privacy **1 passed**, and
  OAuth/dashboard **5 passed**. The fixture verified actual password-control
  redaction and browser/foreground preservation. CI's PR merge tree exactly
  matched the published development-head tree; email delivery was synthetic.

## Development acceptance: isolated staging data configuration (2026-10-15)

The development branch's `docker-compose.test.yml` directly bound the production
Docker volume's host data path into the test gateway. Deploying that source
unchanged could let staging read or modify production data. This source-only
correction replaces the bind with `lucas-staging-data:/data` and an empty
Compose-managed volume declaration. There is no global `name`, external volume
reference or host path; [Compose scopes the volume to its project](https://docs.docker.com/reference/compose-file/volumes/).
Production Compose and its data volume are unchanged.

- Dedicated source regressions passed **4 tests**; the unchanged source failed
  **3**, with its test-service configuration control passing. These validate
  the mount/declaration and retained test-only settings without Docker or data.
- No running application, mount, volume, credential, permissions, database or
  deployment was changed. The current main-based staging app already declares
  an independent named staging volume, which must be verified and preserved
  when a future deployment is approved. This change does not copy, migrate,
  delete or attach any data.
- Before deployment, verify the selected app, exact commit, rendered Compose
  mount, actual volume identity and separation from production. A new project
  may receive an empty test volume. The app name alone is not evidence of its
  branch or isolation. Runtime Docker and deployed-isolation acceptance remain
  separate gates; this environment has no local Docker executable.
- Full local Linux/Python 3.12 suite: **455 passed, 9 skipped**. Independent
  review passed the **4** focused tests, confirmed **3** parent failures and
  **1** passing control, and rejected five unsafe declaration/mount mutations.
  No blocking source issue remained. These are fixed-shape source contracts,
  not a general Compose parser or proof of a running mount.
- Python compilation, extension JavaScript syntax and whitespace checks passed;
  isolated local HTTP page smoke passed **28/28 routes**. Rebuilt wheel Python
  modules and all six extension assets exactly match source. Exact-head CI and
  future deployed acceptance are recorded separately on PR #3.


- Exact-head [CI 38670017946](https://github.com/Neal86/Lucas/actions/runs/38670017946)
  passed for `bad11e43a56c899a08617d8912c7254faae733e1`: Linux Python
  3.11/3.12 each **455 passed, 9 skipped**, Windows Python 3.11 **457 passed,
  7 skipped**, real Chromium extension/CDP **1 passed** and OAuth/dashboard
  **5 passed**. The tested merge tree matched the published source tree. These
  checks do not establish Docker rendering or deployed-volume isolation.

## Development acceptance: computer onboarding and Chinese Beta copy (2026-10-15)

The Connect computer dialog incorrectly counted every authorized computer as an
active slot and refused to open at the account limit, even when those computers
were offline. The backend already allows additional bindings and limits the
active subset. The dashboard now follows that existing model: it opens the
connection-code flow while local approval and server-side active limits remain
authoritative. Opening the dialog sends no access request and grants no access.

Chinese checklist, current connection instructions/status and Beta explanations
use the existing shared translation catalog. The dynamically created checklist
dialog also gets a localized accessible label. English remains the fallback.
The README now describes the free Beta offer and its distinction from model
tokens instead of advertising obsolete paid plans. Historical billing records
and paid-plan implementation are retained.

No API, schema, entitlement limit, permission, pairing, account/device setting
or deployment behavior changes are included. This does not complete live Node
installation/approval/reconnection, real email delivery or Stripe acceptance.

### Regression and integration evidence

- **54** executable rendered-runtime cases passed; **25 failed** on the
  unchanged parent, with **29 compatibility controls passing**. The harness
  loads actual composed functions/catalog and covers below/at/above-limit
  offline bindings, explicit-submit/code/local-approval behavior, dialog reset,
  reconnect prefill, dynamic Chinese checklist/labels and Beta notices.
- Independent focused review passed **102 tests**, with **7** opt-in Chromium
  cases skipped locally. Full local Linux/Python 3.12 suite: **509 passed,
  11 skipped**. Compilation, JavaScript syntax and whitespace checks passed.
- Isolated HTTP page smoke passed **28/28 routes**. Rebuilt wheel Python modules
  and all six extension assets exactly match source.
- Two new English/Chinese Chromium cases use real rendered UI, production HTTP
  handlers and disposable SQLite records for offline computers. They exercise
  the modal at capacity, immediate offline-request rejection, reconnect,
  checklist/Beta localization and active-slot replacement without a live Node.
  An independent fixture smoke verified login 202/200, offline-request 400 and
  activation 200 with three active/four connected computers, and rejection of
  the demoted computer; no RPC occurred.
- Exact-head [CI 38671142116](https://github.com/Neal86/Lucas/actions/runs/38671142116)
  passed for `236b3d8b81f687d2582ca100b0a0e7d3d23a9938`: Linux Python
  3.11/3.12 each **509 passed, 11 skipped**, Windows Python 3.11 **511 passed,
  9 skipped**, real Chromium extension/CDP **1 passed** and OAuth/dashboard/
  onboarding **7 passed**. The tested merge tree matched the published source
  tree. Browser email delivery was synthetic; no live Node was used.

## Development acceptance: native browser handoff and popup errors (2026-10-15)

The extension's fixed page-action function is isolated in `page_actions.js` and
remains serialized into the authorized tab without accepting caller-supplied
JavaScript. Directly resolvable light-DOM link and form navigation targets are
checked before clicking:
named/new contexts, inherited `base` targets and submitter `formtarget` overrides
return the existing manual-handoff result. Explicit same-context overrides,
ordinary same-tab controls and background operation remain supported. Native
label forwarding to a submit control uses the same target check. A new target
still needs the user's separate explicit tab authorization.

This is a native light-DOM target guard, not a sandbox for arbitrary website
event handlers, shadow/slotted activation, script-created windows or later page
navigation. No automatic grant,
new host/debugger permission, forced browser Profile or focus change is added.

The popup presents action failures in a separate accessible error region that
status polling does not overwrite. Rejected pairing requests retain their input
for correction; transport and action errors are caught, and a successful retry
clears the action error. A successful pair response only accepts the connection
attempt: it does not establish that the Node has authenticated the supplied token.
Existing connection status continues to report that later outcome.

The distributable ZIP includes the new module along with the existing six
assets. No bridge protocol, MCP API, database/schema, entitlement, real-user
credential, live-device, deployment or persisted-user-data change is included.
The extension must be updated to receive these source fixes.

### First verification attempt

- **131** serialized page-action runtime cases passed; the identical suite on
  the unchanged parent failed **67**, with **64 compatibility controls passing**.
  The harness runs the actual background-generated CDP expression in a separate
  page context and checks that handoff happens before click/event side effects.
- **23** shipped-popup runtime cases passed; the unchanged parent failed **20**,
  with **3 positive controls passing**. Coverage includes polling, rejected and
  malformed responses, transport failures, stale replies and revoke during a
  pending tab query, plus retained input and ordinary owner/session rendering.
- Independent review passed **200 focused tests**, with the opt-in Chromium
  case skipped locally. The enclosing-anchor/label interaction and a browser
  fixture assertion mismatch were corrected and rechecked; no blocker remained.
- Full local Linux/Python 3.12 suite: **663 passed, 11 skipped**. Python and all
  extension JavaScript syntax checks, whitespace, isolated HTTP smoke **28/28**,
  wheel/source parity for all 77 Python modules and seven extension assets, and
  ZIP asset/content/CRC checks passed.
- The first Chromium fixture added the actual popup button retry flow,
  **19** blocked native cross-context cases, **12** intended same-tab
  navigation controls and ordinary controls. The initial run did not pass all
  of those checks. Tab snapshots, a named unrelated tab,
  request/click sentinels, unchanged grants and preserved foreground selection
  accompany the prior upload/download/revocation/password/CDP checks.
- Initial exact-head [CI 38672415949](https://github.com/Neal86/Lucas/actions/runs/38672415949)
  failed for `f00b1579539db956f0f5ab3a25464dd21dc8a2d3`: both Linux suites
  passed **663/11**, but the real Chromium fixture exposed an incorrect
  assumption that an empty link target overrides an external base target.
  Windows separately had one Node subprocess timeout in the existing password
  observation fixture (**664 passed, 9 skipped, 1 failed**); no privacy assertion
  failed. OAuth browser checks were skipped after the extension failure. This
  failed run is retained, and the correction requires fresh exact-head CI.
  The local browser restriction was not retried. These fixtures do not establish
  live Windows Node, Edge/ixBrowser, staging or provider-email acceptance.

### Chromium empty-target compatibility correction

CI exposed a real difference between the [HTML target algorithm](https://html.spec.whatwg.org/multipage/semantics.html#get-an-element%27s-target)
and Chromium's native behavior. A present empty `target` is preserved by that
standard algorithm, but Chromium falls back to the first `base[target]` for an
empty effective target. An empty submitter `formtarget` still overrides its
form's target before that base fallback. The guard now conservatively handles
this engine behavior; explicit `_self` remains unambiguous and empty targets
without an external base continue working. The compatibility guard does not
rewrite page attributes or click first to discover the destination.

- Corrected serialized runtime suite: **159 passed**. The identical suite fails
  **16** cases on the first fix, with **143 controls passing**; against the
  original pre-extraction source it fails **84**, with **75 controls passing**.
  Both original and failed-first-fix evidence are retained.
- Expanded real Chromium fixture now has **27** blocked native target cases and
  **15** same-tab navigation controls, including empty anchor/form/submitter
  targets under named and blank bases, no-base empties and explicit self
  overrides. Exact-head CI must establish the corrected browser behavior.
- The pre-existing observation test gives the Node subprocess **30 seconds on
  Windows and 10 elsewhere**. The CI failure was a timeout in a finite synthetic
  map/JSON expression, with no failed privacy assertion; precise runner cause
  was not measured. All assertions remain, with no retry or added skip. The
  nine privacy cases pass locally and both timeout branches were checked.
- Final full local Linux/Python 3.12 suite: **691 passed, 11 skipped**. Independent
  corrected-source review passed **237 focused tests**, with **1** opt-in
  Chromium case skipped and no remaining blocker. All extension JavaScript and
  Python syntax, whitespace, HTTP smoke **28/28**, rebuilt wheel/source parity
  for all 77 Python modules/seven assets, and ZIP content/CRC checks passed.
  Fresh exact-head Windows and real Chromium CI remains the acceptance gate.

- Corrected exact-head [CI 38673170272](https://github.com/Neal86/Lucas/actions/runs/38673170272)
  passed for `b9761c79c04b428bccdd9c785ec32120917652a2`: Linux Python
  3.11/3.12 each **691 passed, 11 skipped**, Windows Python 3.11 **693 passed,
  9 skipped**, actual Chromium extension/CDP **1 passed** with all 27 blocked
  targets and 15 same-tab navigation controls, and OAuth/dashboard/onboarding
  **7 passed** with synthetic email delivery. The CI merge tree exactly matched
  the tested/published source tree. The preceding failed run remains recorded.

## Atomic Operation admission and reviewable unresolved work

The gateway now reserves the minimum required quota before dispatching a Node
RPC. The new `operation_admission.py` service uses an additive
`operation_reservations` table and a SQLite `BEGIN IMMEDIATE` transaction, shared
with the entitlement check. The lock ends before the remote await, preserving
concurrent tasks below the limit while preventing two callers from consuming
the same final available unit. Every serving gateway must be upgraded for this
guarantee; a mixed fleet with the old check-only path is not covered.

An explicit negative Node response is a confirmed failure. Confirmed success or
failure atomically creates its task step, updates task/usage totals, writes the
execution audit, and settles the reservation. Repeating settlement does not
charge again or change the first confirmed outcome. The Node wire protocol is
unchanged. Timeout, transport loss, cancellation and expired pending work remain
separate unresolved records: they do not establish failure, create completed
task steps, or increment success/error totals.

The entitlement projection keeps `requests_used` as confirmed completed usage,
adds `requests_pending` and `requests_unconfirmed`, and subtracts all three from
`request_remaining`. Both held and completed units use the admission timestamp
within the effective current billing period. A late result therefore converts
its hold to completed usage in the same period without charging twice; it does
not move into the completion month. This also applies when paid subscription
windows overlap after a plan change. Beta uses fixed UTC calendar months, so
prior-month unresolved records stop holding the next month's capacity while
remaining available for review. Original admission-period boundaries remain
historical metadata, not a separate timer that refunds current quota.

This admission/review layer never retries or refunds unknown work. Existing
same-request transport reconnect/replay behavior is unchanged; this is not an
end-to-end exactly-once execution guarantee. Its deadline changes
the displayed state rather than cancelling the Node operation. Pending records
survive process restart; reading the recovered store marks expired records
unconfirmed. If a confirmed Node result arrives but its local settlement fails,
all accounting writes roll back. The original result is preserved without
re-dispatch, and best-effort metadata labels the record **Accounting unconfirmed**
with the known success/failure. If storage also rejects that annotation, the
durable pending minimum remains and becomes outcome-unconfirmed after recovery.
An administrator can review evidence and use the existing Extra Operations
control to grant replacement capacity; that does not settle the unknown result.
No new release, refund or retry endpoint is provided.

Shell admission still reserves a minimum of one unit. A confirmed result uses
the existing runtime operation count, with the existing static fallback; it can
exceed that minimum and the plan limit, after which further admission is blocked.
This is not a hard execution ceiling. A count lost with a gateway crash cannot
be reconstructed without a larger Node protocol change; the minimum remains
reviewable. Commands, output and exception messages are not persisted in the
new ledger. Source/agent/session/task metadata is sanitized, and transition
audits carry a reservation ID linking to that metadata.

Dashboard, billing, task history and admin user detail share the isolated
`web_operation_usage_runtime.py` renderer. English and Chinese labels distinguish
completed Operations, pending/unconfirmed held units, remaining quota, current
reset and historical records. The task/admin APIs add owner-scoped unresolved
records with the existing node/time filters; completed summaries retain their
old meaning. Beta's free-price explanation and paid-control suppression remain.
The existing privacy test now uses the explicit confirmed-error type for its
known-failure fixture; the onboarding runtime harness includes the new composed
renderer. Their assertions remain intact.

This is source and disposable-fixture validation only. The additive schema is
initialized when the new admission path is used; no live database migration,
deployment, provider operation or real-user device action was performed.

### Verification

- The same barrier-held last-slot gateway regression dispatches **two** RPCs on
  unchanged parent `1f479030457462af20fa15ae60268316109fc6d4`, and exactly **one**
  with the fix. Below-limit calls still overlap rather than serializing remote
  work. All activity uses disposable stores and synthetic registry responses.
- **64 new tests** pass: **24** service/SQLite cases, **28** gateway/HTTP cases,
  and **12** composed-JavaScript/API cases. Coverage includes cross-process
  admission, duplicate settlement, transactional failure at each accounting
  stage, double bookkeeping faults, restart/deadline behavior, month/day and paid
  overlap attribution, owner isolation, shell counts, sanitized metadata and
  English/Chinese rendering.
- Independent review passed **186 focused tests** with no remaining source
  blocker, plus a 32-reservation concurrent-settlement/snapshot stress probe.
  Review corrected the paid-overlap attribution and late accounting-evidence
  enrichment. Full regression caught a context-manager integration mismatch in
  the snapshot helper; its existing connection contract was restored without
  changing the active-computer tests.
- Final local Linux/Python 3.12 suite: **755 passed, 13 skipped**. Python compile,
  all three final-page JavaScript blocks, extension module syntax, whitespace,
  isolated real HTTP page smoke **28/28**, and wheel/source parity for **79**
  Python modules and all **7** extension assets passed.
- The two new real-Chromium English/Chinese cases preserve all seven previous
  cases. They cover dashboard/billing/task/admin usage distinctions, historical
  records, metadata, authorization, localized reset/review help and Beta's $0
  offer. Their disposable HTTP fixture passes with real production handlers,
  SQLite and synthetic mail; browser execution remains the exact-head CI gate.
  Local Chromium restrictions were not retried. Staging, live Windows Node,
  Edge/ixBrowser, provider email and existing Stripe handling remain separate
  acceptance gates.

- Exact-head [CI 38674977570](https://github.com/Neal86/Lucas/actions/runs/38674977570)
  passed for `988ad2984589273de324e0fcbb89be3d858c727b`: Linux Python
  3.11/3.12 each **755 passed, 13 skipped**, Windows Python 3.11 **757 passed,
  11 skipped**, real Chromium extension/CDP **1 passed**, and
  OAuth/dashboard/onboarding/usage **9 passed** with synthetic mail. The two
  new English/Chinese usage flows passed in the real browser. Merge
  `f36cf39c82b1b02dc4869c5e41b9850aa8510357` had exactly the tested/published
  tree `ea60427d5cd3d9e41c97f1c7474b7036cd27f523`, covering all 185 blobs.

## Registration UI state and localized Computer Node guidance

The registration client now lives in `web_registration_runtime.py`, composed by
the existing core runtime. Registration, verification and resend share the
existing auth-mode generation. Mode switches clear pending email/code/metadata,
cooldowns and disabled state. Requests capture their own payload and target;
duplicate submissions and overlapping verification/resend are blocked. Stale
responses cannot reopen the old form, replace the current error, reset Turnstile,
restart cooldowns, fire completion tracking or start an obsolete dashboard boot.
Current successful flows retain their busy lock through the existing guarded
`/auth/me` and dashboard refresh sequence.

These are client-side state guarantees. Server registration/verification may
already have committed, sent mail or issued a cookie before a response becomes
stale; ignoring that response does not undo those effects. No server cancellation,
revocation, HTTP API, schema or authentication-policy change is included. Existing
password/email/Turnstile payloads, backend expiry/resend rules, 60-second client
cooldown and login behavior remain in place.

The standalone `/docs/computer-node` page now uses the shared browser-language
runtime and authoritative English/Chinese catalog, including page title,
description, HTML language and accessible labels. English remains the fallback.
Its existing sticky/responsive layout, download/navigation destinations and
checklist separation remain. Setup explicitly states that a newly requesting
account requires local approval after code verification. The connection-code
FAQ describes current/regenerated codes rather than claiming automatic expiry.

The guide documents the existing Settings → General → Lucas Node update controls,
version/reconnection checks and local permissions. It does not add or run an
updater. The current default installer/updater reads GitHub `main`; a development
checkout or staging page does not establish that those changes are installed on
a Windows computer. Actual install/update/reconnection and Edge/ixBrowser
compatibility still need an explicitly authorized device acceptance session.

The CI browser step includes a separate guide test file alongside the existing
OAuth/dashboard suite. All fixtures use loopback HTTP, isolated state and
synthetic email; source checks do not replace staging or real-device acceptance.

### Verification

- Unchanged `348fbc1b0f6d7e4b4019398af10e1401b3b9f3d7` failed **15**
  supplied registration guard regressions, with **1** existing resend control
  passing. Separate actual-composed-boot probes demonstrated late registration
  and verification opening the old dashboard after a mode change.
- The fixed registration runtime passes **71** dedicated cases and preserves
  all **34** existing auth-mode tests. Coverage includes current success/error
  retry, payload snapshots, mutual exclusion, stale responses/finally callbacks,
  mode reset, English/Chinese labels, and current/stale boot and refresh results.
- The final guide contract/runtime set passes **25** cases; identical tests
  against unchanged `348fbc1` fail **14**, with **11** compatibility controls
  passing. Six Chinese language variants/fallbacks, English/unsupported-language
  fallback, all translated text/attributes, unchanged links and update/approval
  guidance are covered. Existing setup/checklist assertions remain.
- Full local Linux/Python 3.12 suite: **849 passed, 43 skipped**. Python compile,
  final dashboard/guide script syntax, all extension JavaScript, whitespace,
  real isolated HTTP page smoke **28/28** and wheel parity for **80** Python
  modules plus all **7** extension assets pass.
- Independent review passed **247 focused tests**, **90** response-order stress
  combinations and **12** real boot/refresh-ownership probes, with no remaining
  source/test blocker. The fixture's ASGI observer and response gate preserve
  chunked bodies, cookies/headers, early errors and non-HTTP pass-through.
- The browser suite preserves its original **9** cases, adds **28** parameterized
  English/Chinese registration cases and **2** standalone guide cases. Real
  production HTTP/SQLite handlers pass synthetic-mail fixture smoke, including
  held verification, cookies, errors and guide/logo responses. Guide cases check
  actual accessibility names, desktop/mobile layout and sticky behavior without
  activating downloads or updater actions. All **39** web cases still require
  exact-head CI; no local Chromium retry was performed.

### Cross-platform fixture correction

- First exact-head [CI 38676427766](https://github.com/Neal86/Lucas/actions/runs/38676427766)
  for `5346900cb83a600bb9bc7e62bfbea60d1d521f8d` passed Linux Python 3.11/3.12
  (**849 passed, 43 skipped** each), real Chromium extension/CDP (**1 passed**)
  and all **39** web browser cases. Windows had **106 failed, 745 passed,
  41 skipped**: every failure was `WinError 206` while starting the shared
  dashboard-auth Node fixture, before any JavaScript assertion could execute.
  This failed run is retained rather than represented as full acceptance.
- The rendered command measured **40,990 UTF-16 command-line units** in an
  independent probe, above the [Windows CreateProcessW limit](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw).
  `tests/test_dashboard_auth_modes.py` now supplies the unchanged generated
  script through [Node's stdin entry point](https://nodejs.org/api/cli.html),
  explicitly using UTF-8. The shared-login-policy test already delegates to this
  helper and needs no file change. Production code and existing assertions are
  unchanged.
- An enclosing function preserves the fixture's previous declaration scope.
  Plain stdin alone exposed functions on `globalThis`, where named DOM stubs
  overwrote `authError`; the initial local stdin-only attempt failed **107**
  cases and was corrected before publication. Independent review reproduced
  this scope issue, including the ineffective explicit CommonJS-mode variant.
- A new large Chinese-script regression failed on the original `-e` transport
  and checks short argv, explicit UTF-8, scope wrapper and completed execution.
  It adds no skips, retries or relaxed assertions. Windows and real Chromium
  still require a fresh exact-head CI result for the corrective commit.
- Corrected full local Linux/Python 3.12 regression: **850 passed, 43 skipped**.
  Independent focused review: **134 passed**; all existing test assertions are
  unchanged, six generated EN/Chinese/boot/refresh inner scripts are byte-identical
  to the previous transport, and a greater-than-1-MiB Unicode stdin stress probe
  passes. Python compile and whitespace checks pass; the unchanged product wheel
  still matches all **80** Python modules and **7** extension assets.

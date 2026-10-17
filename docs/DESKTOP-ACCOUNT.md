# Desktop account source contract

This review-only batch adapts the main branch's desktop account sign-in to the
shared login policy on top of PR5. It is not a deployment, device acceptance or
new authorization grant. Plugin synchronization was paused by the user on
2026-10-17 and is excluded from this batch.

## One login policy, two response types

- The installed Settings Account page uses `/auth/desktop/login`,
  `/auth/desktop/login/verify` and `/auth/desktop/login/resend`.
- `desktop_auth.py` only adapts the response format. `login_policy.py` remains
  the single authority for passwords, disabled accounts, email availability,
  process-local login/resend rate buckets and the explicit existing staging
  bypass. No new environment switch or bypass is introduced.
- Desktop login always requests its own email challenge. It does not reuse
  browser trusted-device cookies. After successful verification it returns a
  bearer token with no-store headers and no browser cookie. Web login continues
  returning its HttpOnly cookie and the literal `cookie` response marker.
- Login challenge purpose is persisted and checked inside the existing SQLite
  writer transaction before resend/consumption. A web challenge cannot be
  exchanged for a desktop bearer response or vice versa. A wrong-purpose request
  does not consume the correct challenge or modify its attempts.
- Initialization additively creates `login_verifications.purpose`, defaulting
  existing rows to `web`. Existing users, challenges, subscriptions, entitlements,
  OAuth relationships and Node bindings are not rewritten. Challenge attempts,
  IP checks, one-use consumption and lifetime remain the existing shared rules.
- All server workers must run the new source before the desktop flow is enabled
  in a real distribution. Older workers do not understand the purpose column;
  mixed-version operation cannot establish this contract. No mixed rollout is
  performed or authorized by this source change.

## Desktop account and local authority

`local_account.py`, `local_account_state.py` and `credential_vault.py` own the
account HTTP client, origin/account generation and DPAPI persistence. The
Settings account UI and asynchronous lifecycle are separate modules. Small
Settings/gateway composition changes wire them in without importing another
branch's monolithic UI or server.

- The configured gateway is normalized to its account server origin. Invalid,
  credential-bearing or non-HTTPS remote addresses fail closed.
- Persisted account state is bound to that server. An account token cannot
  silently follow a changed gateway address. An unbound legacy state is not
  trusted automatically; sign-in is required.
- Persisted sessions have a validated finite expiry. The UI identifies a locally
  saved session; it does not claim that cached state proves live server/account
  status. An expired or malformed lifetime requires sign-in again.
- Tokens are protected with Windows DPAPI; there is no plaintext persistence or
  non-Windows fallback. Tests use synthetic tokens and fake native APIs. They do
  not read any user credential store or make a real sign-in request.
- Each state writer creates, writes and fsyncs its own temporary file. Final
  replacement is serialized by a canonical-path reentrant lock shared with
  account-state operations in this process, including raw helper calls. Different
  paths remain independent. Replacement errors propagate and temporary files are
  cleaned up; this does not provide cross-process serialization.
- Latest-operation and account-generation ownership prevent delayed login,
  verification or `/auth/me` responses from recreating a signed-out session,
  replacing another account, or signing out a newer session on a stale 401.
- UI work runs off the Tk thread; completion is applied only by an alive,
  current page/session owner. Closing the page, canceling verification or signing
  out invalidates pending UI ownership. This suppresses stale local commits and
  callbacks; it cannot undo an HTTP request already dispatched to the server.
- Sign-in, Verify and Resend submissions capture the displayed account/challenge
  generation before acquiring lifecycle ownership. A stale form is refreshed
  without dispatching or claiming a newer challenge, so closing or canceling it
  cannot clear a replacement sign-in from another page.
- Account sign-in does not authorize this Node, change Allowed Folders, create an
  AI OAuth relationship, alter Beta limits or grant OS/browser permissions.
  Local computer authorization remains a separate existing user-approved flow.
- Gateway edits apply when Settings is reopened. A malformed gateway does not
  prevent opening the rest of Settings to correct it.

## Verification and remaining gates

The batch has dedicated real SQLite/HTTP tests with isolated synthetic users and
email delivery, concurrent challenge tests, fake-native DPAPI tests, temporary
account-state races and synthetic Tk lifecycle tests. Existing authentication,
OAuth, Beta, Node, web and extension regression suites remain mandatory. Exact
source/CI counts are recorded in the review PR, including skips and failures.

Real Windows Settings rendering, actual DPAPI under an intended Windows user,
mail delivery, a supported review distribution, deployed staging and subsequent
production approval remain separate gates. Review builds retain PR5's fail-closed
in-app updater. No installer/device operation, deployment, version release,
credential enrollment or permission change is part of this batch. Plugin
synchronization and remote plugin execution are not delivered by this batch.

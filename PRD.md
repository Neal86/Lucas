# Lucas Product Requirements Document (PRD)

Version: 2.1 — 2026-10-11
Status: Product requirements; implementation and production acceptance tracked separately.

## Product
Lucas connects a user's existing AI assistant to authorized local computers and browser sessions through a secure gateway, with no additional Lucas model-token fee. AI-provider limits remain applicable.

## Beta pricing and navigation (P0)
- Keep the public Pricing navigation item and /pricing route; do not hide the page.
- Show one card only: **Lucas Beta — $0/month, free during testing**.
- Entitlements for all new and existing users during Beta: **100,000 Operations/month, 3 computers, 3 AI accounts, multiple concurrent tasks, full Lucas execution**.
- Hide old Free, Pro, Pro+, Expansion Pack cards and monthly/annual selector from the public pricing page and dashboard billing view. Retain the underlying historical subscription data and code for future reinstatement.
- Disable **new** paid checkout, upgrades and expansion purchases during Beta on the server, not only in the UI. Existing Stripe subscriptions must be audited and handled separately to prevent unintended charges; do not delete billing records or silently cancel existing subscriptions.
- Remove upsell copy from quota errors during Beta; show the actual limit and next reset instead.
- Public disclaimer: **Free during Beta. Plans and limits may change.**
- Operations are distinct from model tokens. Lucas charges no additional token fees; upstream AI provider plans/limits still apply.

## Browser control (P0)
- Chrome/Chromium extension to operate user-authorized tabs, read page structure, click/type/scroll, navigate, upload/download and screenshot.
- Background operation by default. Explicit confirmation for actions that seize desktop focus; handoff for CAPTCHA, passkeys, identity verification or other manual steps.
- Do not enforce mandatory dedicated profile isolation; authorization must still be scoped to the user-approved browser sessions and tabs.
- Support existing Chrome/Edge and ixBrowser where technically feasible, without circumventing site security.

## Computer Node (P0)
- Windows Node for files, shell, Git, application and desktop operations; macOS support planned.
- Local authorization, allowed paths, reconnection, updates, and complete per-action audit trail.
- Multiple AI accounts and computers under one Lucas account.

## Web and onboarding (P0)
- Responsive, sticky header; sign-in and start-free registration flow; browser-language localization and clear onboarding.
- Dashboard: connected computers, AI connections, operation usage, task logs, permissions and session controls.

## Security and reliability (P0)
- Preserve local OS authority and explicit user permission. Prevent accidental foreground focus, cross-session control and destructive operations without applicable authorization.
- Audit operation source, agent, task, device, session, approval and result. Avoid sensitive data leakage.
- Stage changes first, run tests and web smoke checks, obtain confirmation before production release, then verify deployed commit and endpoints.

## Acceptance criteria
1. /pricing and navigation show only Lucas Beta and $0, no paid buttons.
2. New and existing users receive the stated Beta entitlements regardless of historical paid plan.
3. No new Stripe checkout or expansion purchases can be created while Beta mode is active; existing subscriptions are safely handled.
4. Quota, device and AI account enforcement agree with the dashboard.
5. Browser/desktop permissions, focus behavior and task logs pass regression tests.
6. All required web routes and onboarding flows pass staging smoke tests before production approval.

## Implementation status
PRD requirements are not evidence of deployed functionality. Verify each acceptance criterion in code, tests, staging, and production separately.

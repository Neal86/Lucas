# Lucas

**Website:** https://lucasmcp.com/

Lucas is an MCP-native bridge that lets compatible AI assistants work on computers you explicitly authorize: files, terminal, Git, browser, and desktop applications. The computer makes an outbound secure WebSocket connection to the Lucas Gateway, so no inbound port is required on the user's computer.

## Current product flow

1. Create a Lucas account or sign in with Google.
2. Install and open Lucas Node on Windows.
3. In **Dashboard → Computers**, enter the computer Node ID and its current 8-digit Connection Code.
4. Approve the requesting account locally and choose its access policy / Allowed Folders.
5. Connect an MCP-compatible AI client to Lucas and authorize the same account.
6. The AI can execute only through computers and local permissions that account is allowed to use.

Previously approved accounts remain connected until their local access is revoked. A computer can authorize multiple Lucas accounts.

## Account-synced integrations

Lucas can sign in from the local Windows Settings app and synchronize GPT/MCP-compatible integration metadata across computers. Standard remote MCP server definitions can be installed once and appear on other signed-in Lucas devices.

What syncs:
- integration name, MCP endpoint, transport, enabled state and version metadata;
- per-device installation state;
- per-AI/agent allow or deny state.

What does **not** sync:
- Allowed Folders, foreground-control policy, Windows permissions or other local security authority;
- browser cookies or local application sessions;
- plaintext access tokens, passwords, API keys or client secrets.

Local Lucas account tokens are protected with Windows DPAPI. Synced plugin manifests are sanitized before storage.

## Browser automation

Lucas uses Playwright/CDP for browser work so normal page reading, clicking, typing, navigation and diagnostics can run without desktop mouse/keyboard input or foreground focus. Windows Nodes can also connect an ixBrowser profile through the official ixBrowser Local API and reuse that profile's authenticated session, fingerprint, proxy and extensions.

When a site requires CAPTCHA, 2FA, passkey, login or identity verification, browser automation can return a structured `requires_user_action` handoff to the AI conversation and later resume the same browser session. See [Browser Automation Architecture](docs/BROWSER_AUTOMATION.md).

## Plans

| Plan | Monthly | Annual | Requests / month | Active Computers | AI accounts |
|---|---:|---:|---:|---:|---:|
| Free | $0 | — | 1,000 | 1 | 1 |
| Pro | $9.99 | $99.99 | 25,000 | 3 | 1 |
| Pro+ | $19.99 | $199.99 | 100,000 | 6 | 3 |

Expansion Pack (Pro+ only): **$14.99/month or $149.99/year**, adding **100,000 Requests, 6 active Computers, and 1 AI account**.

## Referral rewards

When a new account is created through a referral link, both users receive **1,000 bonus Requests**. When the referred user first becomes a paid customer, the referrer receives an additional **10,000 Requests**.

## Security model

- Local Node approval is the authority for computer access.
- Allowed Folders constrain direct file access and workspace operations.
- Passwords are hashed with Argon2.
- Browser sessions use HttpOnly authentication cookies.
- Node transport uses a persistent device credential and WSS.
- Sensitive fields are redacted from dashboard audit output.
- Admin accounts are never created by public “first signup” behavior; production deployments must configure `GWC_SUPER_ADMIN_EMAIL`.

Shell and desktop actions still execute with the Windows account's OS permissions. For higher-risk workloads, use a dedicated Windows account or VM and grant the minimum Lucas permissions required.

## Gateway endpoints

- Website: `https://lucasmcp.com/`
- Dashboard: `https://lucasmcp.com/dashboard`
- Pricing: `https://lucasmcp.com/pricing`
- MCP: `https://lucasmcp.com/mcp`
- Node WSS: `wss://lucasmcp.com/ws/node`
- Health/readiness: `https://lucasmcp.com/health`

## Development

> Development and AI-assisted changes must follow [PROJECT_RULES.md](PROJECT_RULES.md). In particular: present the change plan and file list before editing, and isolate new features in new modules/files whenever practical.

Python 3.11+:

```bash
git clone https://github.com/Neal86/Lucas.git
cd Lucas
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Run the gateway:

```bash
gwc-gateway
```

The production deployment uses the included Dockerfile. Keep `GWC_DATA_DIR` on persistent storage so the database and generated JWT secret survive container replacement.

## Production checklist

- Set `GWC_PUBLIC_BASE_URL=https://lucasmcp.com`.
- Set `GWC_SUPER_ADMIN_EMAIL`.
- Keep `GWC_DATA_DIR` on persistent storage.
- Configure Turnstile and SMTP/email verification.
- Configure Google OAuth redirect URI exactly.
- Configure all six Stripe Price IDs and the Stripe webhook secret.
- Confirm `/health` reports critical readiness.
- Require the latest `main` CI to pass on Windows and Ubuntu before deployment.

Customer-facing Privacy, Terms, Refund, and Contact pages are linked from the Lucas website.

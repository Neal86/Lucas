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

## Lucas Beta — $0/month

**Free during Beta. Plans and limits may change.** The public [Pricing page](https://lucasmcp.com/pricing) remains available.

New and existing accounts receive the same base Beta access:

- 100,000 Operations per month
- 3 active computers and 3 AI accounts
- Multiple concurrent tasks and full Lucas execution
- No additional Lucas model-token fee; your AI provider's plan and usage limits still apply

Operations are distinct from model tokens. Connecting an additional computer does not raise the active-computer limit: choose which authorized computers are active from the dashboard. Connection codes and local approval are still required. Existing explicit bonuses remain supported.

New paid checkout, upgrades and expansion purchases are disabled during Beta. Historical subscription data and billing code are retained. Beta does not automatically cancel or pause existing Stripe subscriptions; those must be audited and handled separately before release to prevent unintended charges.

## Referral rewards

A qualifying referral signup grants both accounts 1,000 bonus Operations. Historical paid-referral rewards and records are retained, but new paid purchases are disabled during Beta.

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
- Confirm Beta paid-checkout blocking and separately audit/handle existing Stripe subscriptions; preserve historical billing records.
- Confirm `/health` reports critical readiness.
- Require the latest `main` CI to pass on Windows and Ubuntu before deployment.

Customer-facing Privacy, Terms, Refund, and Contact pages are linked from the Lucas website.

# GPT Windows Connector

Remote-first, model-independent Windows execution MCP for ChatGPT, Claude, Gemini, and other MCP-compatible AI clients.

It exposes project files, shell, long-running processes, Git, browser automation, and Windows desktop/UI Automation without calling Codex, Claude Code, or Gemini CLI internally.

## Product model

All AI ↔ Windows traffic goes through the VPS Gateway. Windows nodes never need a public inbound port.

```text
ChatGPT / Claude / Gemini / other Remote-MCP client
                    |
                    | HTTPS / Remote MCP
                    v
                 VPS Gateway
                    |
                    | WSS
                    v
               Windows Node
                    |
      +-------------+-------------+
      |             |             |
 files/workspace  shell/process   git
      |             |             |
      +------- browser/computer --+
```

The connector is multi-user. The unique project binding key is:

```text
(user_id, project_id)
        |
        +-- node_id
        `-- workspace folder
```

Different users may use the same `project_id` without seeing each other's project, node, or workspace. There is intentionally **no conversation binding**.

## Authentication

### Email registration/login

Register:

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "a-password-at-least-10-characters",
  "name": "User"
}
```

Login:

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "a-password-at-least-10-characters"
}
```

Both return a JWT access token and also set an HttpOnly session cookie. Use the returned token for Remote MCP:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

Current user:

```http
GET /auth/me
```

Passwords are hashed with Argon2. JWTs are signed by the VPS Gateway. If `GWC_JWT_SECRET` is not supplied, the gateway generates a persistent secret in `GWC_DATA_DIR/jwt-secret.txt`.

### Google login

Configure a Google OAuth **Web application** and set:

```text
GWC_GOOGLE_CLIENT_ID
GWC_GOOGLE_CLIENT_SECRET
GWC_GOOGLE_REDIRECT_URI=https://gwc.example.com/auth/google/callback
```

Start login at:

```text
https://gwc.example.com/auth/google/start
```

The gateway uses Google's authorization-code flow with `openid email profile`, exchanges the returned code on the VPS, reads the authenticated Google profile from Google's OpenID Connect UserInfo endpoint, and creates or links the local user by email.

Optional:

```text
GWC_AUTH_SUCCESS_URL=https://your-web-ui.example.com/login/callback
```

If configured, the callback redirects there with the access token in the URL fragment. Otherwise the callback returns JSON containing the token.

## Multi-user isolation

Each authenticated user gets independent:

- projects
- project bindings
- Windows nodes
- node pairing codes/tokens
- desktop/browser control locks
- audit entries

A user cannot bind or operate another user's node. The same project name can exist under multiple users safely.

## Project binding

- `project_bind(project_id, node_id, workspace, name?)`
- `project_get(project_id)`
- `project_list()`
- `project_unbind(project_id)`

The gateway resolves the authenticated user automatically, so MCP tools still only need `project_id`; the actual lookup is `(user_id, project_id)`.

A workspace is verified against the live Windows node before it is saved.

## Files

`files_tool(project_id, action, params)` supports:

- `list`
- `read`
- `write`
- `patch` — exact-match safe patching
- `search`
- `stat`
- `mkdir`
- `move`
- `copy`
- `delete`

Direct file paths are sandboxed inside the bound workspace.

## Shell

`shell_run(project_id, command, timeout, shell_type)` supports PowerShell and CMD, returning stdout, stderr and exit code.

## Long-running processes

`process_tool(project_id, action, params)` supports:

- `start`
- `poll`
- `stop`
- `list`
- incremental stdout/stderr cursors

Use it for dev servers, builds, tests, Docker commands and other long tasks.

## Git

`git_tool(project_id, action, params)` supports:

- `status`
- `diff`
- `log`
- `branch`
- `branch_create`
- `branch_switch`
- `add`
- `commit`
- `pull`
- `push`
- `show`

## Browser

`browser_tool(project_id, action, params)` uses Playwright:

- `discover` — common Chrome / Edge / iXBrowser installs and profiles
- `connect_cdp`
- `launch_persistent`
- `pages`
- `new_page`
- `navigate`
- `inspect`
- `click`
- `type`
- `select`
- `upload` — source restricted to the project workspace
- `download` — destination restricted to the project workspace
- `screenshot`
- `close`

Browser CDP remains local to the Windows node. The AI never connects directly to the Windows machine; commands/results are relayed through the VPS Gateway.

## Windows desktop / UI Automation

`computer_tool(project_id, action, params)` supports:

- system/process information
- launch applications
- list/activate windows
- screenshots
- mouse click/move/drag/scroll
- keyboard input, key presses, hotkeys
- Unicode text input using clipboard fallback
- clipboard read/write
- `ui_elements`
- `ui_click`
- `ui_set_text`

Screenshots and desktop results are returned Windows Node → VPS Gateway → AI client.

## Multi-node

One VPS Gateway can serve many users and many Windows PCs:

```text
VPS Gateway
├── User A
│   ├── Office-PC
│   └── Home-PC
└── User B
    └── Warehouse-PC
```

Each project independently selects one of the authenticated user's nodes and a workspace on that node.

## Desktop/browser control lock

Projects can read files/Git independently, but interactive browser/desktop control is protected by a per-node lease:

- `control_acquire(project_id, ttl_seconds?)`
- `control_status(project_id)`
- `control_release(project_id)`

Mutating browser/desktop operations automatically acquire or refresh the lease.

## Pairing and reconnect

A logged-in user creates a one-time pairing code:

- `node_pair(node_id, name?, ttl_seconds?)`
- `node_list()`

The pairing code is tied to that user. On first connection the VPS Gateway issues a persistent random node token and records the node owner. The Windows node stores the token locally, reconnects automatically with exponential backoff, and sends heartbeats.

## Permission levels

Set `GWC_PERMISSION_LEVEL` on each Windows node:

- `read` — inspection/read tools only
- `operate` — normal coding and automation operations
- `admin` — additionally permits direct `files.delete` and `git.push`

Default: `operate`.

`GWC_ALLOWED_ROOTS` restricts which folders may become project workspaces.

**Important:** `shell_run` and long-running shell processes execute with the Windows account's normal OS permissions. `GWC_ALLOWED_ROOTS` is a hard boundary for the connector's direct file tools and project selection, not an OS-level PowerShell sandbox. Use a dedicated Windows account/VM for strong machine-level isolation.

## Gateway install

Requires Python 3.11+.

```powershell
git clone https://github.com/Neal86/gpt-windows-connector.git
cd gpt-windows-connector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Gateway configuration:

```powershell
$env:GWC_HOST = "0.0.0.0"
$env:GWC_PORT = "8787"
$env:GWC_DATA_DIR = ".\data"
$env:GWC_PUBLIC_BASE_URL = "https://gwc.example.com"
$env:GWC_JWT_SECRET = "replace-with-a-long-random-secret"
gwc-gateway
```

Endpoints:

```text
Remote MCP:        https://gwc.example.com/mcp
Node WebSocket:    wss://gwc.example.com/ws/node
Health:            https://gwc.example.com/health
Email register:    https://gwc.example.com/auth/register
Email login:       https://gwc.example.com/auth/login
Google login:      https://gwc.example.com/auth/google/start
Google callback:   https://gwc.example.com/auth/google/callback
Current user:      https://gwc.example.com/auth/me
```

`GWC_PUBLIC_BASE_URL` automatically creates the MCP Host/Origin allowlist used by DNS-rebinding protection. For non-standard reverse-proxy setups, override with comma-separated `GWC_ALLOWED_HOSTS` and `GWC_ALLOWED_ORIGINS`.

A Dockerfile and `docker-compose.yml` are included for the VPS Gateway. Use HTTPS/WSS at the public reverse proxy.

## Windows node

Install the same package on Windows and create a pairing code after logging in through the VPS Gateway.

```powershell
$env:GWC_NODE_ID = "Office-PC"
$env:GWC_NODE_NAME = "Office PC"
$env:GWC_GATEWAY_WS = "wss://gwc.example.com/ws/node"
$env:GWC_PAIRING_CODE = "123456"
$env:GWC_ALLOWED_ROOTS = "G:\;D:\Projects"
$env:GWC_PERMISSION_LEVEL = "operate"
gwc-node
```

After first pairing, the node token is persisted under the current user's local application-data directory.

## Bind a project

After `Office-PC` is online:

```text
project_bind(
  project_id="NiceC-WMS",
  node_id="Office-PC",
  workspace="G:\\NiceC-WMS",
  name="NiceC-WMS"
)
```

Then:

```text
files_tool("NiceC-WMS", "search", {"query": "login"})
shell_run("NiceC-WMS", "npm run build")
git_tool("NiceC-WMS", "diff")
```

The authenticated user is inferred from the JWT; no `user_id` parameter is exposed to the model tools.

## Intended coding loop

```text
read/search code
      -> patch/write
      -> run build/test
      -> inspect errors
      -> patch again
      -> git diff/status
      -> commit/push when permitted
```

No tool invokes Codex, Claude Code, or Gemini CLI.

## Security

This software can execute commands and control a Windows desktop.

- All AI ↔ Windows traffic should go through the VPS Gateway.
- Use HTTPS/WSS for remote deployment.
- Use a strong persistent `GWC_JWT_SECRET`.
- Configure Google OAuth redirect URIs exactly.
- Restrict `GWC_ALLOWED_ROOTS`.
- Prefer `read`/`operate`; use `admin` only when required.
- Run Windows nodes under dedicated low-privilege Windows users when practical.
- Treat JWTs and persistent node tokens as secrets.
- Do not expose Windows-node services directly to the public internet.

The project pins MCP Python SDK `>=1.27.2,<2` and enables explicit Host/Origin transport-security allowlists for the public MCP hostname.

## Storage

The VPS Gateway stores multi-user state in:

```text
GWC_DATA_DIR/gateway.db
```

SQLite tables include users, OAuth state, project bindings, node ownership/tokens, and audit logs. JWT signing material is stored separately in `GWC_DATA_DIR/jwt-secret.txt` when not supplied through `GWC_JWT_SECRET`.

## Windows-MCP upstream reference

This repository remains independent from CursorTouch/Windows-MCP. Windows-MCP is not required at runtime.

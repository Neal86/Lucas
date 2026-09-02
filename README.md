# GPT Windows Connector

**Website:** [https://lucasmcp.com/](https://lucasmcp.com/)

Remote-first, multi-user Windows execution MCP for ChatGPT, Claude, Gemini, and other MCP-compatible AI clients.

The product exposes local project files, Shell, long-running processes, Git, browser automation, and Windows desktop/UI Automation through a VPS Gateway. Codex, Claude Code, and Gemini CLI are not used as an execution layer.

## Final architecture

```text
ChatGPT / Claude / Gemini / other Remote-MCP client
                    |
                    | HTTPS / MCP
                    v
              VPS Gateway
          account / projects / logs
                    |
                    | WSS
                    v
              Windows Node
                    |
        files / shell / git / browser / desktop
```

All AI-to-Windows traffic is relayed through the VPS. A Windows computer makes an outbound WSS connection and does not require a public inbound port.

## User experience

1. Open the VPS Gateway website.
2. Register with email/password or sign in with Google.
3. Pair a Windows computer from **Windows Nodes**.
4. Create a project from **Projects**.
5. Select an online Windows computer.
6. Browse that computer's allowed folder tree and select a workspace.
7. Connect the Remote MCP endpoint to the AI client using the same account.
8. The AI uses the project ID; the VPS resolves the correct user, Windows Node, and workspace automatically.

There is intentionally **no conversation binding**.

```text
(user_id, project_id)
        |
        +-- node_id
        `-- workspace
```

## Built-in VPS dashboard

Running `gwc-gateway` serves both the web dashboard and Remote MCP endpoint.

Dashboard sections:

- **Dashboard** — project/node/activity overview
- **Projects** — project → Windows computer → folder bindings
- **Windows Nodes** — online/offline nodes and one-time pairing codes
- **Activity Logs** — user-scoped audit history with filters
- **Account & Security** — account/provider and security information

The folder picker never reads the VPS filesystem. It requests directory information from the selected Windows Node through the VPS WebSocket and only exposes directories inside `GWC_ALLOWED_ROOTS`.

## Authentication

Supported login methods:

- Email/password registration and login
- Google OAuth 2.0 / OpenID Connect
- JWT access tokens for MCP/API clients
- HttpOnly login cookie for the built-in web dashboard

Passwords are hashed with Argon2. User/project/node/audit data is stored in the VPS `gateway.db` SQLite database. If `GWC_JWT_SECRET` is omitted, a random secret is generated once and persisted under `GWC_DATA_DIR`.

### Google login

Create a Google OAuth Web application and configure:

```text
GWC_GOOGLE_CLIENT_ID=...
GWC_GOOGLE_CLIENT_SECRET=...
GWC_GOOGLE_REDIRECT_URI=https://gwc.example.com/auth/google/callback
```

If `GWC_GOOGLE_REDIRECT_URI` is omitted while client ID/secret are present, the gateway derives it from `GWC_PUBLIC_BASE_URL`. Google login returns to the built-in dashboard by default.

## Project binding and folder picker

The Windows Node advertises only configured allowed roots:

```powershell
$env:GWC_ALLOWED_ROOTS = "G:\;D:\Projects"
```

The VPS dashboard can browse:

```text
Office-PC
├─ G:\
│  ├─ NiceC-WMS
│  ├─ OpenAkita
│  └─ PartyGame
└─ D:\Projects
   └─ another-project
```

A selected project binding is persisted on the VPS:

```text
user_id + "NiceC-WMS"
  -> Office-PC
  -> G:\NiceC-WMS
```

The Node validates the selected folder before the Gateway saves it. Paths outside allowed roots are rejected.

## MCP tools

### Projects and nodes

- `project_bind`
- `project_get`
- `project_list`
- `project_unbind`
- `node_pair`
- `node_list`
- `control_acquire`
- `control_status`
- `control_release`

### Files

`files_tool(project_id, action, params)` supports:

- list
- read
- write
- patch
- search
- stat
- mkdir
- move
- copy
- delete

Direct file operations are sandboxed inside the project's bound workspace.

### Shell and processes

- `shell_run` — PowerShell/CMD, stdout/stderr/exit code, timeout
- `process_tool` — start/poll/stop/list with incremental output cursors

### Git

`git_tool` supports status, diff, log, branch, branch create/switch, add, commit, pull, push, and show.

### Browser

`browser_tool` supports browser discovery, CDP attach, persistent profile launch, tabs/pages, navigation, DOM inspection, click/type/select, workspace-scoped upload/download, screenshots, and close.

### Windows desktop

`computer_tool` supports system/process information, application launch, window listing/activation, screenshots, mouse/keyboard, clipboard, and Windows UI Automation inspection/click/text entry.

## Activity Logs

The VPS writes user-scoped audit events to `gateway.db`. The dashboard exposes only the authenticated user's records. Sensitive fields such as passwords, access tokens, authorization headers, cookies, clipboard data, and full content values are redacted by the UI API.

## Multi-node and control locking

One account can have multiple Windows computers:

```text
Gateway
├─ Office-PC
├─ Warehouse-PC
└─ Home-PC
```

Interactive browser/desktop operations use a per-node project lease so two projects do not fight over the same mouse/window.

## Permission levels

Set on each Windows Node:

```text
GWC_PERMISSION_LEVEL=read | operate | admin
```

- `read`: inspection/read methods only
- `operate`: normal coding and automation
- `admin`: also allows direct file deletion and Git push

`GWC_ALLOWED_ROOTS` is a hard boundary for direct connector file operations and workspace selection. Shell commands still run with the normal Windows account permissions, so use a dedicated low-privilege Windows user or VM when strong OS-level isolation is required.

## Install Gateway on VPS

Python 3.11+:

```bash
git clone https://github.com/Neal86/gpt-windows-connector.git
cd gpt-windows-connector
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Configure:

```bash
export GWC_HOST=0.0.0.0
export GWC_PORT=8787
export GWC_DATA_DIR=./data
export GWC_PUBLIC_BASE_URL=https://gwc.example.com
gwc-gateway
```

Public endpoints:

```text
Dashboard:   https://gwc.example.com/
Remote MCP:  https://gwc.example.com/mcp
Node WSS:    wss://gwc.example.com/ws/node
Health:      https://gwc.example.com/health
```

A Dockerfile and `docker-compose.yml` are included. Put HTTPS/WSS in front of the service in production.

## Install Windows Node

Install the package on Windows, create a one-time pairing code from the VPS dashboard, then run:

```powershell
$env:GWC_NODE_ID = "Office-PC"
$env:GWC_NODE_NAME = "Office PC"
$env:GWC_GATEWAY_WS = "wss://gwc.example.com/ws/node"
$env:GWC_PAIRING_CODE = "123456"
$env:GWC_ALLOWED_ROOTS = "G:\;D:\Projects"
$env:GWC_PERMISSION_LEVEL = "operate"
gwc-node
```

After successful pairing, the Gateway issues a persistent random node token. The Node stores it in the current user's local app-data directory and reconnects automatically with heartbeat + exponential backoff.

## Security

- Use HTTPS/WSS in production.
- Restrict `GWC_ALLOWED_ROOTS`.
- Prefer `read` or `operate`; grant `admin` only when necessary.
- Treat JWTs and persistent node tokens as secrets.
- Run the Windows Node under a dedicated Windows account where practical.
- The MCP Python SDK is pinned to `>=1.27.2,<2` and explicit Host/Origin transport security is enabled.
- The Windows Node is outbound-only; do not expose local CDP, Shell, or Node ports publicly.

## Intended coding loop

```text
AI -> VPS -> Windows Node
   read/search code
   -> patch/write
   -> build/test
   -> inspect errors
   -> patch again
   -> git diff/status
   -> commit/push when permitted
   -> VPS -> AI
```

The repository remains independent from CursorTouch/Windows-MCP. Windows-MCP is not required at runtime.

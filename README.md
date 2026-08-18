# GPT Windows Connector

Remote-first, model-independent Windows execution MCP for ChatGPT, Claude, Gemini, and other MCP-compatible AI clients.

It exposes the local execution capabilities normally supplied by coding agents—project files, shell, long-running processes, Git, browser automation, and Windows desktop/UI Automation—without calling Codex, Claude Code, or Gemini CLI internally.

## Product model

The connector has **one context layer only: project binding**.

```text
AI project_id
     |
     v
Project Binding
     |
     +-- Windows node_id
     `-- Workspace folder
```

There is intentionally **no conversation binding**. Every conversation using the same stable `project_id` resolves to the same Windows computer and folder.

> The MCP protocol does not magically expose the ChatGPT/Claude/Gemini sidebar project ID to a server. The AI client/integration must pass a stable `project_id` (for example a project name or project identifier) when it calls the tools. Once that ID is bound, the gateway persists the mapping.

## Architecture

```text
ChatGPT / Claude / Gemini / other Remote-MCP client
                    |
                    | Streamable HTTP
                    v
              GWC Gateway
             /mcp   /ws/node
               |       |
               |    WebSocket
               |       |
               +--> Windows Node
                       |
      +----------------+----------------+
      |                |                |
 workspace/files   shell/process       git
      |                |                |
      +---------- browser/computer -----+
                       |
                    Windows
```

The Windows node creates the outbound WebSocket connection, so the Windows PC does not need a public inbound port.

## Capabilities

### Project binding

- `project_bind(project_id, node_id, workspace, name?)`
- `project_get(project_id)`
- `project_list()`
- `project_unbind(project_id)`
- Binding is persisted on the gateway
- A workspace is verified against the live node before the binding is saved
- No conversation-level override exists

### Files

`files_tool(project_id, action, params)`:

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

Direct file-tool paths are sandboxed inside the bound workspace.

### Shell

`shell_run(project_id, command, timeout, shell_type)`:

- PowerShell
- CMD
- stdout / stderr / exit code
- configurable timeout
- workspace as the command working directory

### Long-running processes

`process_tool(project_id, action, params)`:

- `start`
- `poll`
- `stop`
- `list`
- incremental stdout/stderr cursors
- process ownership scoped to the project workspace

Use this for dev servers, builds, tests, Docker commands, and other long tasks.

### Git

`git_tool(project_id, action, params)`:

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

### Browser

`browser_tool(project_id, action, params)` uses Playwright:

- `discover` — discover common Chrome / Edge / iXBrowser installs and profiles
- `connect_cdp` — attach to an already running Chromium browser
- `launch_persistent`
- `pages`
- `new_page`
- `navigate`
- `inspect`
- `click`
- `type`
- `select`
- `upload` — source files are restricted to the project workspace
- `download` — destination is restricted to the project workspace
- `screenshot`
- `close`

### Windows desktop / UI Automation

`computer_tool(project_id, action, params)`:

- system/process information
- launch applications
- list/activate windows
- screenshots
- mouse click/move/drag/scroll
- keyboard input, key presses, hotkeys
- Unicode text input using clipboard fallback
- clipboard read/write
- `ui_elements` — inspect Windows UI Automation controls
- `ui_click` — invoke/click a UI Automation control
- `ui_set_text` — set text through UI Automation with keyboard fallback

## Multi-node

One gateway can serve multiple Windows PCs:

```text
GWC Gateway
├── Office-PC
├── Warehouse-PC
└── Home-PC
```

Each project independently selects its node and workspace.

## Desktop/browser control lock

Projects can read files/Git independently, but interactive browser/desktop control is protected by a per-node lease so two projects do not fight over the same mouse/window.

- `control_acquire(project_id, ttl_seconds?)`
- `control_status(project_id)`
- `control_release(project_id)`

Mutating browser/desktop operations automatically acquire or refresh the lease.

## Pairing and reconnect

A Windows node authenticates with a one-time pairing code on first connection. The gateway issues a persistent random node token, which the node stores locally and uses after reconnect/restart.

- `node_pair(node_id, name?, ttl_seconds?)`
- `node_list()`
- heartbeat
- exponential automatic reconnect
- duplicate node connection replacement

## Permission levels

Set `GWC_PERMISSION_LEVEL` on each Windows node:

- `read` — inspection/read tools only
- `operate` — normal coding and automation operations
- `admin` — additionally permits direct `files.delete` and `git.push`

Default: `operate`.

`GWC_ALLOWED_ROOTS` restricts which folders may become project workspaces.

**Important:** `shell_run` and long-running shell processes execute with the Windows account's normal OS permissions. A shell can access paths outside the workspace if the command explicitly does so; `GWC_ALLOWED_ROOTS` is a hard boundary for the connector's direct file tools and project selection, not an OS-level PowerShell sandbox. Use a dedicated Windows account/VM if you need strong machine-level isolation.

## Install

### Gateway

Requires Python 3.11+.

```powershell
git clone https://github.com/Neal86/gpt-windows-connector.git
cd gpt-windows-connector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Configure:

```powershell
$env:GWC_HOST = "0.0.0.0"
$env:GWC_PORT = "8787"
$env:GWC_DATA_DIR = ".\data"
$env:GWC_PUBLIC_BASE_URL = "https://gwc.example.com"
$env:GWC_ADMIN_TOKEN = "replace-with-a-long-random-token"
gwc-gateway
```

Endpoints:

```text
Remote MCP: https://gwc.example.com/mcp
Node WS:    wss://gwc.example.com/ws/node
Health:     https://gwc.example.com/health
```

`GWC_PUBLIC_BASE_URL` automatically creates the MCP Host/Origin allowlist used by DNS-rebinding protection. For non-standard reverse-proxy setups, override it with comma-separated `GWC_ALLOWED_HOSTS` and `GWC_ALLOWED_ORIGINS`.

A Dockerfile and `docker-compose.yml` are included for the gateway. Use HTTPS/WSS at the public reverse proxy.

### Windows node

Install the package on Windows and create a pairing code through `node_pair`.

```powershell
$env:GWC_NODE_ID = "Office-PC"
$env:GWC_NODE_NAME = "Office PC"
$env:GWC_GATEWAY_WS = "wss://gwc.example.com/ws/node"
$env:GWC_PAIRING_CODE = "123456"
$env:GWC_ALLOWED_ROOTS = "G:\;D:\Projects"
$env:GWC_PERMISSION_LEVEL = "operate"
gwc-node
```

After first pairing, the node token is persisted under the current user's local application-data directory. The pairing code is not needed again unless the node credential is reset.

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

Then use that project ID for every operation:

```text
files_tool("NiceC-WMS", "search", {"query": "login"})
shell_run("NiceC-WMS", "npm run build")
git_tool("NiceC-WMS", "diff")
```

## Browser attachment

For an existing Chrome/Edge instance started with remote debugging:

```text
browser_tool(
  "NiceC-WMS",
  "connect_cdp",
  {"endpoint": "http://127.0.0.1:9222"}
)
```

Or use `launch_persistent` with a dedicated browser profile directory.

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

- Use HTTPS/WSS for remote deployment.
- Set a strong `GWC_ADMIN_TOKEN`, or put the MCP HTTP endpoint behind a proper authentication proxy.
- Restrict `GWC_ALLOWED_ROOTS`.
- Prefer `read`/`operate`; use `admin` only when required.
- Run the Windows node as a dedicated low-privilege Windows user when practical.
- Treat persistent node tokens as secrets.
- Do not expose an unauthenticated gateway to the public internet.

The project pins MCP Python SDK `>=1.27.2,<2` and enables explicit Host/Origin transport-security allowlists for the public MCP hostname.

## Windows-MCP upstream reference

This repository remains independent from CursorTouch/Windows-MCP. To keep that project available only as a reference remote in a local clone:

```powershell
git remote add windows-mcp-upstream https://github.com/CursorTouch/Windows-MCP.git
git fetch windows-mcp-upstream
```

Windows-MCP is not required at runtime.

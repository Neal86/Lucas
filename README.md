# GPT Windows Connector

Remote-first, model-independent Windows execution MCP for ChatGPT, Claude, Gemini, and other MCP-compatible AI clients.

The connector exposes the local execution capabilities normally provided by coding agents—project workspaces, direct file editing, shell commands, long-running processes, Git, browser automation, and Windows desktop control—without using Codex, Claude Code, or Gemini CLI as an execution layer.

## Product model

There is **one workspace context only: project binding**.

```text
AI Project ID
     |
     v
Project Binding
     |
     +-- Windows Node ID
     `-- Workspace Folder
```

There is intentionally **no conversation binding**. Every conversation that uses the same project ID resolves to the same Windows node and workspace.

## Architecture

```text
ChatGPT / Claude / Gemini / other MCP client
                    |
                    | Remote MCP (Streamable HTTP)
                    v
              GWC Gateway
        /mcp              /ws/node
          |                   |
          |               WebSocket
          |                   |
          +------------> Windows Node
                              |
          +-------------------+-------------------+
          |                   |                   |
      workspace/files     shell/process        git
          |                   |                   |
          +------------- browser/computer --------+
                              |
                           Windows
```

The Windows node makes the outbound WebSocket connection, so the Windows machine does not need a public inbound port.

## Capabilities

### Project binding

- `project_bind(project_id, node_id, workspace)`
- `project_get(project_id)`
- `project_list()`
- `project_unbind(project_id)`
- Project binding is persisted by the gateway
- The gateway verifies the workspace against the live node before saving the binding

### Files

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

Every path is sandboxed inside the bound workspace.

### Shell

`sh​​ell_run(project_id, command, timeout, shell_type)` supports:

- PowerShell
- CMD
- stdout / stderr / exit code
- configurable timeout
- execution from the bound project workspace

### Long-running processes

`process_tool(project_id, action, params)` supports:

- `start`
- `poll`
- `stop`
- `list`
- incremental stdout/stderr cursors

This is intended for dev servers, tests, builds, Docker commands, and other tasks that cannot fit in one MCP request.

### Git

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

### Browser

`browser_tool(project_id, action, params)` uses Playwright and supports:

- attach to an existing Chromium browser through CDP
- persistent browser profile launch
- page/tab listing
- navigation
- DOM text inspection
- click / type / select
- file upload
- screenshots

### Windows desktop

`computer_tool(project_id, action, params)` supports:

- system/process information
- launch applications
- list/activate windows
- screenshots
- mouse click/move/drag/scroll
- keyboard input and hotkeys
- Unicode input through clipboard fallback
- clipboard read/write

## Multi-node

One gateway can serve multiple Windows computers:

```text
GWC Gateway
├── Office-PC
├── Warehouse-PC
└── Home-PC
```

Each project chooses its own node and workspace.

## Pairing and reconnect

Windows nodes authenticate with a one-time pairing code on first connection. The gateway then issues a persistent node token which is saved locally on the Windows machine. The node automatically reconnects with exponential backoff and sends heartbeats while connected.

MCP tools:

- `node_pair(node_id)`
- `node_list()`

## Permission levels

Set `GWC_PERMISSION_LEVEL` on each Windows node:

- `read` — read-only files/Git/browser/desktop inspection
- `operate` — normal coding and automation operations
- `admin` — also allows destructive file deletion and Git push

Default: `operate`.

Workspace access is separately restricted by `GWC_ALLOWED_ROOTS`.

## Install

### Gateway

Python 3.11+:

```powershell
git clone https://github.com/Neal86/gpt-windows-connector.git
cd gpt-windows-connector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Configure and start:

```powershell
$env:GWC_HOST = "0.0.0.0"
$env:GWC_PORT = "8787"
$env:GWC_DATA_DIR = ".\data"
$env:GWC_ADMIN_TOKEN = "replace-with-a-long-random-token"
gwc-gateway
```

Remote MCP endpoint:

```text
https://YOUR-GATEWAY/mcp
```

Health endpoint:

```text
https://YOUR-GATEWAY/health
```

Put TLS in front of the gateway in production.

### Windows node

Install the same package on Windows, then create a pairing code through the MCP `node_pair` tool.

Example:

```powershell
$env:GWC_NODE_ID = "Office-PC"
$env:GWC_NODE_NAME = "Office PC"
$env:GWC_GATEWAY_WS = "wss://YOUR-GATEWAY/ws/node"
$env:GWC_PAIRING_CODE = "123456"
$env:GWC_ALLOWED_ROOTS = "G:\;D:\Projects"
$env:GWC_PERMISSION_LEVEL = "operate"
gwc-node
```

After the first successful pairing the node token is persisted under the user's local application data directory, so the pairing code is no longer required.

## Bind a project

Once `Office-PC` is online:

```text
project_bind(
  project_id="NiceC-WMS",
  node_id="Office-PC",
  workspace="G:\\NiceC-WMS",
  name="NiceC-WMS"
)
```

Then all execution calls use only the project ID:

```text
files_tool("NiceC-WMS", "search", {"query": "login"})
shell_run("NiceC-WMS", "npm run build")
git_tool("NiceC-WMS", "diff")
```

The AI client is responsible for passing a stable project ID (for example the project name or an ID supplied by its project integration). The connector does not create per-conversation state.

## Browser attachment

For an existing Chrome/Edge profile, start Chromium with remote debugging enabled and call:

```text
browser_tool("NiceC-WMS", "connect_cdp", {"endpoint": "http://127.0.0.1:9222"})
```

Or use `launch_persistent` with a dedicated browser profile directory.

## Development loop

The intended coding workflow is:

```text
read/search code
      -> patch/write
      -> run build/test
      -> inspect errors
      -> patch again
      -> git diff/status
      -> commit/push when allowed
```

No tool calls Codex, Claude Code, or Gemini CLI internally.

## Security

This connector can execute commands and control a Windows desktop. For production use:

- use HTTPS/WSS only
- set a strong `GWC_ADMIN_TOKEN` or place the MCP endpoint behind a proper OAuth/authentication proxy
- restrict `GWC_ALLOWED_ROOTS`
- use `read` or `operate` unless `admin` is genuinely needed
- never expose the Windows node WebSocket directly without gateway authentication
- treat paired node tokens as secrets

## Windows-MCP upstream reference

This repository remains independent. To keep the CursorTouch Windows-MCP project available as a reference remote in a local clone:

```powershell
git remote add windows-mcp-upstream https://github.com/CursorTouch/Windows-MCP.git
git fetch windows-mcp-upstream
```

The connector does not require Windows-MCP at runtime.

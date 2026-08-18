# GPT Windows Connector

Universal Windows MCP connector that exposes a local Windows machine directly to MCP-compatible AI clients such as ChatGPT, Claude, and Gemini.

The project is designed to provide the local execution capabilities normally supplied by coding agents—workspace access, file editing, shell commands, Git, processes, browser/desktop automation—without requiring Codex or Claude Code as an execution layer.

## V0.1 scope

- Workspace binding and path sandboxing
- File listing, reading, writing, searching, and exact text patching
- PowerShell command execution
- Long-running process start/poll/stop
- Git status, diff, log, branch, commit, pull, and push
- Windows process/application listing and launching
- MCP stdio transport for local MCP clients

## Architecture

```text
ChatGPT / Claude / Gemini
          |
          | MCP
          v
GPT Windows Connector
  |-- workspace.*
  |-- files.*
  |-- shell.*
  |-- process.*
  |-- git.*
  `-- computer.*
          |
          v
       Windows
```

The MCP protocol layer is model-independent. No tool calls Codex, Claude Code, or Gemini CLI internally.

## Safety model

All filesystem operations are restricted to an explicitly configured workspace root. Shell and Git commands run with that workspace as their working directory. This avoids exposing the whole machine by default.

## Install

Requires Windows and Python 3.11+.

```powershell
git clone https://github.com/Neal86/gpt-windows-connector.git
cd gpt-windows-connector
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Set a workspace:

```powershell
$env:GWC_WORKSPACE = "G:\\your-project"
```

Run the MCP server:

```powershell
gpt-windows-connector
```

## Example MCP client configuration

```json
{
  "mcpServers": {
    "gpt-windows-connector": {
      "command": "gpt-windows-connector",
      "env": {
        "GWC_WORKSPACE": "G:\\your-project"
      }
    }
  }
}
```

## Roadmap

V0.2 will add Playwright browser sessions and richer Windows UI Automation. V0.3 will add remote node pairing/gateway support so one MCP endpoint can control multiple Windows machines.

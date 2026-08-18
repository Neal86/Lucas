param(
  [string]$InstallDir = "$env:LOCALAPPDATA\gpt-windows-connector"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python 3.11+ is required."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
python -m venv "$InstallDir\.venv"
& "$InstallDir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$InstallDir\.venv\Scripts\pip.exe" install -e (Resolve-Path "$PSScriptRoot\..")

Write-Host "Installed GPT Windows Connector node runtime at $InstallDir"
Write-Host "Configure GWC_GATEWAY_WS, GWC_NODE_ID, GWC_ALLOWED_ROOTS and GWC_PAIRING_CODE, then run:"
Write-Host "  $InstallDir\.venv\Scripts\gwc-node.exe"

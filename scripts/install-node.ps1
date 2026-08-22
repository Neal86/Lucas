param(
  [string]$GatewayUrl = "wss://lucas.autozon.xyz/ws/node",
  [string]$PairingCode = "",
  [string]$NodeName = "$env:COMPUTERNAME",
  [string]$AllowedRoot = "$env:USERPROFILE",
  [ValidateSet("read", "operate", "admin")]
  [string]$Permission = "operate",
  [string]$InstallDir = "$env:LOCALAPPDATA\Lucas"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Venv = Join-Path $InstallDir "runtime"
$ConfigFile = Join-Path $InstallDir "node-config.json"
$StateFile = Join-Path $InstallDir "node-state.json"
$HasSavedToken = $false
if (Test-Path $StateFile) {
  try {
    $SavedState = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
    $HasSavedToken = -not [string]::IsNullOrWhiteSpace([string]$SavedState.node_token)
  } catch {
    $HasSavedToken = $false
  }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          LUCAS WINDOWS NODE" -ForegroundColor Cyan
Write-Host "   Connect this PC to your Lucas AI" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ([string]::IsNullOrWhiteSpace($PairingCode) -and -not $HasSavedToken) {
  $PairingCode = Read-Host "Lucas pairing code"
}
if ([string]::IsNullOrWhiteSpace($PairingCode) -and -not $HasSavedToken) {
  throw "A Lucas pairing code is required. Generate one from Lucas > Windows Nodes."
}

if ([string]::IsNullOrWhiteSpace($NodeName)) {
  $NodeName = $env:COMPUTERNAME
}
if ([string]::IsNullOrWhiteSpace($AllowedRoot)) {
  $AllowedRoot = $env:USERPROFILE
}
$AllowedRoot = [System.IO.Path]::GetFullPath((Resolve-Path $AllowedRoot).Path)

$PythonCommand = $null
$PythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  $PythonCommand = "py"
  $PythonArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $PythonCommand = "python"
} else {
  throw "Python 3.11+ is required. Install Python from python.org, then run this script again."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Venv = Join-Path $InstallDir "runtime"
$ConfigFile = Join-Path $InstallDir "node-config.json"
$StateFile = Join-Path $InstallDir "node-state.json"

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
  Write-Host "[Lucas] Creating local Python runtime..." -ForegroundColor Yellow
  & $PythonCommand @PythonArgs -m venv $Venv
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
$PyVersionOk = (& $VenvPython -c "import sys; print('1' if sys.version_info >= (3, 11) else '0')").Trim()
if ($PyVersionOk -ne "1") { throw "Lucas Node requires Python 3.11 or newer." }
Write-Host "[Lucas] Installing/updating Lucas Node..." -ForegroundColor Yellow
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }
& $VenvPython -m pip uninstall --disable-pip-version-check -y gpt-windows-connector | Out-Null
& $VenvPython -m pip install --disable-pip-version-check --no-cache-dir "https://github.com/Neal86/Lucas/archive/refs/heads/main.zip"
if ($LASTEXITCODE -ne 0) { throw "Failed to install the latest Lucas Node." }
$InstalledVersion = (& $VenvPython -c "import importlib.metadata; print(importlib.metadata.version('gpt-windows-connector'))").Trim()
Write-Host "[Lucas] Installed Lucas Node $InstalledVersion" -ForegroundColor Green

$MachineGuid = ""
try {
  $MachineGuid = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name MachineGuid -ErrorAction Stop).MachineGuid
} catch {
  $MachineGuid = [guid]::NewGuid().ToString()
}
$NodeId = (("{0}-{1}" -f $env:COMPUTERNAME, $MachineGuid.Substring(0, [Math]::Min(12, $MachineGuid.Length))).ToLower() -replace '[^a-z0-9._-]', '-')

$ExistingConfig = $null
if (Test-Path $ConfigFile) {
  try { $ExistingConfig = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json } catch { $ExistingConfig = $null }
}
if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.node_id)) { $NodeId = [string]$ExistingConfig.node_id }
$ConfigNodeName = if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.node_name)) { [string]$ExistingConfig.node_name } else { $NodeName }
$ConfigPermission = if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.permission_level)) { [string]$ExistingConfig.permission_level } else { $Permission }
$ConfigRoots = @($AllowedRoot)
if ($ExistingConfig -and $ExistingConfig.allowed_roots -and @($ExistingConfig.allowed_roots).Count -gt 0) { $ConfigRoots = @($ExistingConfig.allowed_roots | ForEach-Object { [string]$_ }) }
$ConfigPairingCode = $null
if (-not $HasSavedToken) { $ConfigPairingCode = $PairingCode.Trim() }
$Config = [ordered]@{
  gateway_ws_url = $GatewayUrl.TrimEnd('/')
  node_id = $NodeId
  node_name = $ConfigNodeName
  pairing_code = $ConfigPairingCode
  permission_level = $ConfigPermission
  allowed_roots = $ConfigRoots
}
$Config | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigFile -Encoding UTF8

$env:GWC_GATEWAY_WS = $Config.gateway_ws_url
$env:GWC_NODE_ID = $Config.node_id
$env:GWC_NODE_NAME = $Config.node_name
$env:GWC_PAIRING_CODE = $Config.pairing_code
$env:GWC_PERMISSION_LEVEL = $Config.permission_level
$env:GWC_ALLOWED_ROOTS = ($Config.allowed_roots -join [System.IO.Path]::PathSeparator)
$env:GWC_NODE_STATE = $StateFile

Write-Host ""
Write-Host "[Lucas] Ready" -ForegroundColor Green
Write-Host "  Node:      $($Config.node_name)"
Write-Host "  Gateway:   $($Config.gateway_ws_url)"
Write-Host "  Folder(s): $($Config.allowed_roots -join '; ')"
Write-Host "  Permission:$($Config.permission_level)"
Write-Host ""
Write-Host "[Lucas] Connecting... Keep this window open." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop Lucas Node. Run this script again anytime to re-pair or update."
Write-Host ""

$LucasNode = Join-Path $Venv "Scripts\lucas-node.exe"
if (-not (Test-Path $LucasNode)) {
  $LucasNode = Join-Path $Venv "Scripts\gwc-node.exe"
}
& $LucasNode

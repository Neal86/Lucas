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

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          LUCAS WINDOWS NODE" -ForegroundColor Cyan
Write-Host "   Connect this PC to your Lucas AI" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ([string]::IsNullOrWhiteSpace($PairingCode)) {
  $PairingCode = Read-Host "Lucas pairing code"
}
if ([string]::IsNullOrWhiteSpace($PairingCode)) {
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
Write-Host "[Lucas] Installing/updating Lucas Node..." -ForegroundColor Yellow
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
& $VenvPython -m pip install --disable-pip-version-check --upgrade "https://github.com/Neal86/Lucas/archive/refs/heads/main.zip"

$MachineGuid = ""
try {
  $MachineGuid = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name MachineGuid -ErrorAction Stop).MachineGuid
} catch {
  $MachineGuid = [guid]::NewGuid().ToString()
}
$NodeId = (("{0}-{1}" -f $env:COMPUTERNAME, $MachineGuid.Substring(0, [Math]::Min(12, $MachineGuid.Length))).ToLower() -replace '[^a-z0-9._-]', '-')

$Config = [ordered]@{
  gateway_ws_url = $GatewayUrl.TrimEnd('/')
  node_id = $NodeId
  node_name = $NodeName
  pairing_code = $PairingCode.Trim()
  permission_level = $Permission
  allowed_roots = @($AllowedRoot)
}
$Config | ConvertTo-Json -Depth 5 | Set-Content -Path $ConfigFile -Encoding UTF8

$env:GWC_GATEWAY_WS = $Config.gateway_ws_url
$env:GWC_NODE_ID = $Config.node_id
$env:GWC_NODE_NAME = $Config.node_name
$env:GWC_PAIRING_CODE = $Config.pairing_code
$env:GWC_PERMISSION_LEVEL = $Config.permission_level
$env:GWC_ALLOWED_ROOTS = $AllowedRoot
$env:GWC_NODE_STATE = $StateFile

Write-Host ""
Write-Host "[Lucas] Ready" -ForegroundColor Green
Write-Host "  Node:      $NodeName"
Write-Host "  Gateway:   $GatewayUrl"
Write-Host "  Folder:    $AllowedRoot"
Write-Host "  Permission:$Permission"
Write-Host ""
Write-Host "[Lucas] Connecting... Keep this window open." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop Lucas Node. Run this script again anytime to re-pair or update."
Write-Host ""

$LucasNode = Join-Path $Venv "Scripts\lucas-node.exe"
if (-not (Test-Path $LucasNode)) {
  $LucasNode = Join-Path $Venv "Scripts\gwc-node.exe"
}
& $LucasNode

param(
  [string]$GatewayUrl = "wss://lucasmcp.com/ws/node",
  [string]$PairingCode = "",
  [string]$NodeName = "$env:COMPUTERNAME",
  [string]$AllowedRoot = "$env:USERPROFILE",
  [ValidateSet("read", "operate", "admin")]
  [string]$Permission = "operate",
  [string]$InstallDir = "$env:LOCALAPPDATA\Lucas"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Test-Python311 {
  param([string]$Command, [string[]]$Arguments)
  try {
    & $Command @Arguments -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Venv = Join-Path $InstallDir "runtime"
$ConfigFile = Join-Path $InstallDir "node-config.json"
$StateFile = Join-Path $InstallDir "node-state.json"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

$SavedState = $null
$HasSavedToken = $false
if (Test-Path $StateFile) {
  try {
    $SavedState = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
    $HasSavedToken = -not [string]::IsNullOrWhiteSpace([string]$SavedState.node_token)
  } catch {
    $SavedState = $null
    $HasSavedToken = $false
  }
}

$ExistingConfig = $null
if (Test-Path $ConfigFile) {
  try { $ExistingConfig = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json } catch { $ExistingConfig = $null }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          LUCAS WINDOWS NODE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ([string]::IsNullOrWhiteSpace($PairingCode) -and -not $HasSavedToken) {
  $PairingCode = Read-Host "Lucas pairing code"
}
if ([string]::IsNullOrWhiteSpace($PairingCode) -and -not $HasSavedToken) {
  throw "A Lucas pairing code is required. Generate one from Lucas > Computer Nodes."
}

$PythonCommand = $null
$PythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  foreach ($Selector in @("-3.13", "-3.12", "-3.11", "-3")) {
    if (Test-Python311 "py" @($Selector)) {
      $PythonCommand = "py"
      $PythonArgs = @($Selector)
      break
    }
  }
}
if (-not $PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
  if (Test-Python311 "python" @()) { $PythonCommand = "python" }
}
if (-not $PythonCommand) {
  throw "Python 3.11+ is required. Install Python 3.11 or newer, then run Lucas-Node.bat again."
}

if (Test-Path $VenvPython) {
  $VenvOk = $false
  try {
    & $VenvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    $VenvOk = ($LASTEXITCODE -eq 0)
  } catch { $VenvOk = $false }
  if (-not $VenvOk) {
    Write-Host "[Lucas] Rebuilding outdated local runtime..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $Venv
  }
}

if (-not (Test-Path $VenvPython)) {
  Write-Host "[Lucas] Creating local Python runtime..." -ForegroundColor Yellow
  & $PythonCommand @PythonArgs -m venv $Venv
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) { throw "Failed to create the Lucas Python runtime." }
}

Get-Process -Name "lucas-node","gwc-node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "[Lucas] Installing the latest Lucas Node..." -ForegroundColor Yellow
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }

& $VenvPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('gpt_windows_connector') else 1)" 2>$null
$PackageAlreadyInstalled = ($LASTEXITCODE -eq 0)
$PackageUrl = "https://github.com/Neal86/Lucas/archive/refs/heads/main.zip"
if ($PackageAlreadyInstalled) {
  & $VenvPython -m pip install --disable-pip-version-check --force-reinstall --no-deps --no-cache-dir $PackageUrl
} else {
  & $VenvPython -m pip install --disable-pip-version-check --no-cache-dir $PackageUrl
}
if ($LASTEXITCODE -ne 0) { throw "Failed to install the latest Lucas Node." }

$InstalledVersion = (& $VenvPython -c "import importlib.metadata; print(importlib.metadata.version('gpt-windows-connector'))").Trim()
if ([string]::IsNullOrWhiteSpace($InstalledVersion)) { throw "Lucas Node installation verification failed." }
Write-Host "[Lucas] Installed Lucas Node $InstalledVersion" -ForegroundColor Green

$MachineGuid = ""
try {
  $MachineGuid = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name MachineGuid -ErrorAction Stop).MachineGuid
} catch {
  $MachineGuid = [guid]::NewGuid().ToString()
}
$GeneratedNodeId = (("{0}-{1}" -f $env:COMPUTERNAME, $MachineGuid.Substring(0, [Math]::Min(12, $MachineGuid.Length))).ToLower() -replace '[^a-z0-9._-]', '-')
$NodeId = $GeneratedNodeId
if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.node_id)) { $NodeId = [string]$ExistingConfig.node_id }
elseif ($SavedState -and -not [string]::IsNullOrWhiteSpace([string]$SavedState.node_id)) { $NodeId = [string]$SavedState.node_id }

if ([string]::IsNullOrWhiteSpace($NodeName)) { $NodeName = $env:COMPUTERNAME }
$ConfigNodeName = $NodeName
if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.node_name)) { $ConfigNodeName = [string]$ExistingConfig.node_name }

$ConfigPermission = $Permission
if ($ExistingConfig -and -not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.permission_level)) { $ConfigPermission = [string]$ExistingConfig.permission_level }
if ($ConfigPermission -notin @("read", "operate", "admin")) { $ConfigPermission = "operate" }

if ([string]::IsNullOrWhiteSpace($AllowedRoot)) { $AllowedRoot = $env:USERPROFILE }
$AllowedRoot = [System.IO.Path]::GetFullPath((Resolve-Path $AllowedRoot).Path)
$ConfigRoots = @($AllowedRoot)
if ($ExistingConfig -and $ExistingConfig.allowed_roots -and @($ExistingConfig.allowed_roots).Count -gt 0) {
  $ConfigRoots = @($ExistingConfig.allowed_roots | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
if ($ConfigRoots.Count -eq 0) { $ConfigRoots = @($AllowedRoot) }

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
if ($Config.pairing_code) { $env:GWC_PAIRING_CODE = $Config.pairing_code } else { Remove-Item Env:GWC_PAIRING_CODE -ErrorAction SilentlyContinue }
$env:GWC_PERMISSION_LEVEL = $Config.permission_level
$env:GWC_ALLOWED_ROOTS = ($Config.allowed_roots -join [System.IO.Path]::PathSeparator)
$env:GWC_NODE_STATE = $StateFile

Write-Host ""
Write-Host "[Lucas] Ready" -ForegroundColor Green
Write-Host "  Node:      $($Config.node_name)"
Write-Host "  Gateway:   $($Config.gateway_ws_url)"
Write-Host "  Permission:$($Config.permission_level)"
Write-Host ""
Write-Host "[Lucas] Connecting..." -ForegroundColor Green
Write-Host "After pairing, manage this computer from Lucas > Computer Nodes."
Write-Host "Press Ctrl+C to stop the local node process."
Write-Host ""

$LucasNode = Join-Path $Venv "Scripts\lucas-node.exe"
if (-not (Test-Path $LucasNode)) { $LucasNode = Join-Path $Venv "Scripts\gwc-node.exe" }
if (-not (Test-Path $LucasNode)) { throw "Lucas Node launcher was not installed correctly." }
& $LucasNode
exit $LASTEXITCODE

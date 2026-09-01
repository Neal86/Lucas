param(
  [string]$GatewayUrl = "wss://lucasmcp.com/ws/node",
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

function Resolve-Python311 {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Selector in @("-3.14", "-3.13", "-3.12", "-3.11", "-3")) {
      if (Test-Python311 "py" @($Selector)) {
        return [pscustomobject]@{ Command = "py"; Arguments = @($Selector) }
      }
    }
  }

  $PythonExe = Get-Command python -ErrorAction SilentlyContinue
  if ($PythonExe -and $PythonExe.Source -notmatch '\\WindowsApps\\' -and (Test-Python311 $PythonExe.Source @())) {
    return [pscustomobject]@{ Command = $PythonExe.Source; Arguments = @() }
  }

  $CandidatePaths = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    (Join-Path $env:ProgramFiles "Python314\python.exe"),
    (Join-Path $env:ProgramFiles "Python313\python.exe"),
    (Join-Path $env:ProgramFiles "Python312\python.exe"),
    (Join-Path $env:ProgramFiles "Python311\python.exe")
  )
  foreach ($Candidate in $CandidatePaths) {
    if ((Test-Path $Candidate) -and (Test-Python311 $Candidate @())) {
      return [pscustomobject]@{ Command = $Candidate; Arguments = @() }
    }
  }

  return $null
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Venv = Join-Path $InstallDir "runtime"
$ConfigFile = Join-Path $InstallDir "node-config.json"
$StateFile = Join-Path $InstallDir "node-state.json"
$DeviceCredentialFile = Join-Path $InstallDir "node-device-credential.json"
$StateBackupFile = "$StateFile.pre-update"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvPythonw = Join-Path $Venv "Scripts\pythonw.exe"
$TrayPidFile = Join-Path $InstallDir "lucas-tray.pid"
$StatusFile = Join-Path $InstallDir "node-status.json"
$TaskName = "Lucas Node"

$SavedState = $null
$HasSavedToken = $false
if (Test-Path $StateFile) {
  try {
    $SavedState = Get-Content -Raw -Path $StateFile | ConvertFrom-Json
    $HasSavedToken = -not [string]::IsNullOrWhiteSpace([string]$SavedState.node_token)
    if ($HasSavedToken) { Copy-Item -Force -Path $StateFile -Destination $StateBackupFile }
  } catch {
    $SavedState = $null
    $HasSavedToken = $false
  }
}
if (-not $HasSavedToken -and (Test-Path $DeviceCredentialFile)) {
  try {
    $SavedState = Get-Content -Raw -Path $DeviceCredentialFile | ConvertFrom-Json
    $HasSavedToken = -not [string]::IsNullOrWhiteSpace([string]$SavedState.node_token)
    if ($HasSavedToken) {
      $SavedState | ConvertTo-Json -Depth 5 | Set-Content -Path $StateFile -Encoding UTF8
      Copy-Item -Force -Path $StateFile -Destination $StateBackupFile
    }
  } catch {
    $SavedState = $null
    $HasSavedToken = $false
  }
}

$ExistingConfig = $null
$ExistingConfigRaw = $null
$ConfigBackupFile = "$ConfigFile.pre-update"
if (Test-Path $ConfigFile) {
  try {
    $ExistingConfigRaw = Get-Content -Raw -Path $ConfigFile
    $ExistingConfig = $ExistingConfigRaw | ConvertFrom-Json -ErrorAction Stop
    Copy-Item -Force -Path $ConfigFile -Destination $ConfigBackupFile
  } catch {
    throw "Existing Lucas configuration could not be read. Update aborted without changing local settings: $($_.Exception.Message)"
  }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "          LUCAS WINDOWS NODE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Lucas Nodes self-register with a local device credential and do not use account pairing codes.

$Python = Resolve-Python311
if (-not $Python) {
  Write-Host "[Lucas] Python 3.11+ not found. Installing automatically..." -ForegroundColor Yellow

  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "[Lucas] Installing Python 3.12 with Windows Package Manager..." -ForegroundColor Yellow
    try {
      & winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
    } catch {
      Write-Host "[Lucas] Windows Package Manager install was unavailable; trying the direct installer..." -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 2
    $Python = Resolve-Python311
  }

  if (-not $Python) {
    $PythonVersion = "3.12.10"
    $PythonInstaller = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
    Write-Host "[Lucas] Downloading the official Python runtime..." -ForegroundColor Yellow
    try {
      [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -UseBasicParsing $PythonUrl -OutFile $PythonInstaller
      $InstallProcess = Start-Process -FilePath $PythonInstaller -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=0","Include_launcher=1","Include_pip=1","Include_test=0","Include_doc=0","Shortcuts=0" -Wait -PassThru
      if ($InstallProcess.ExitCode -ne 0) {
        Write-Host "[Lucas] Python installer exited with code $($InstallProcess.ExitCode)." -ForegroundColor Yellow
      }
    } catch {
      Write-Host "[Lucas] Automatic Python installation failed: $($_.Exception.Message)" -ForegroundColor Red
    } finally {
      Remove-Item -Force -ErrorAction SilentlyContinue $PythonInstaller
    }
    $Python = Resolve-Python311
  }
}

if (-not $Python) {
  throw "Lucas could not install Python 3.11+ automatically. Check the internet connection or software-installation policy and run Lucas-Node.bat again."
}

$PythonCommand = [string]$Python.Command
$PythonArgs = @($Python.Arguments)
Write-Host "[Lucas] Python runtime ready." -ForegroundColor Green

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

# Stop every old Lucas tray/node process before replacing the runtime. Older builds
# can leave a base-Python Node behind whose command line no longer contains the venv
# path. That stale process owns the single-instance mutex and keeps the old Node ID
# online while the Settings UI shows the new configuration. Match Lucas modules
# directly so upgrades cannot leave a ghost Node behind.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
  $CommandLine = [string]$_.CommandLine
  $CommandLine -and (
    $CommandLine -match 'gpt_windows_connector\.tray' -or
    $CommandLine -match 'gpt_windows_connector\.node' -or
    $CommandLine -match 'lucas-node\.exe' -or
    $CommandLine -match 'gwc-node\.exe'
  )
} | ForEach-Object {
  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}
Start-Sleep -Milliseconds 500
Remove-Item -Force -ErrorAction SilentlyContinue $TrayPidFile
Remove-Item -Force -ErrorAction SilentlyContinue $StatusFile

Write-Host "[Lucas] Installing the latest Lucas Node..." -ForegroundColor Yellow
& $VenvPython -m pip install --disable-pip-version-check --upgrade pip | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to update pip." }

& $VenvPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('gpt_windows_connector') else 1)" 2>$null
$PackageAlreadyInstalled = ($LASTEXITCODE -eq 0)
$PackageUrl = "https://github.com/Neal86/Lucas/archive/refs/heads/main.zip"
if ($PackageAlreadyInstalled) {
  & $VenvPython -m pip install --disable-pip-version-check --force-reinstall --no-cache-dir $PackageUrl
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

# The local node name is always the real Windows computer name. User-facing
# aliases are managed on the Lucas website and must not be written back locally.
$ConfigNodeName = $env:COMPUTERNAME
if ([string]::IsNullOrWhiteSpace($ConfigNodeName)) { $ConfigNodeName = $NodeName }

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

$ConnectionEnabled = $true
if ($ExistingConfig -and $null -ne $ExistingConfig.connection_enabled) {
  $ConnectionEnabled = [bool]$ExistingConfig.connection_enabled
}
$LaunchAtStartup = $true
if ($ExistingConfig -and $null -ne $ExistingConfig.launch_at_startup) { $LaunchAtStartup = [bool]$ExistingConfig.launch_at_startup }
$SecurityConfig = $null
if ($ExistingConfig -and $null -ne $ExistingConfig.security) { $SecurityConfig = $ExistingConfig.security }
if ($ExistingConfig -and $ExistingConfigRaw) {
  # Preserve existing settings, but repair Gateway values persisted by old local
  # development builds. A production Node must never keep dialing its own 127.0.0.1.
  $ExistingGateway = ([string]$ExistingConfig.gateway_ws_url).Trim().TrimEnd('/')
  $StaleLocalGateways = @(
    "ws://127.0.0.1:8787/ws/node",
    "ws://localhost:8787/ws/node",
    "wss://127.0.0.1:8787/ws/node",
    "wss://localhost:8787/ws/node"
  )
  if ($ExistingGateway -in $StaleLocalGateways) {
    $ExistingConfig.gateway_ws_url = $GatewayUrl.TrimEnd('/')
    $ExistingConfig | ConvertTo-Json -Depth 20 | Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "[Lucas] Repaired old local Gateway -> $($ExistingConfig.gateway_ws_url)" -ForegroundColor Yellow
  } else {
    # Keep unknown future fields byte-for-byte when no migration is required.
    $ExistingConfigRaw | Set-Content -Path $ConfigFile -Encoding UTF8
  }
  $Config = Get-Content -Raw -Path $ConfigFile | ConvertFrom-Json -ErrorAction Stop
} else {
  $Config = [ordered]@{
    gateway_ws_url = $GatewayUrl.TrimEnd('/')
    node_id = $NodeId
    node_name = $ConfigNodeName
    permission_level = $ConfigPermission
    allowed_roots = $ConfigRoots
    connection_enabled = $ConnectionEnabled
    launch_at_startup = $LaunchAtStartup
    security = $SecurityConfig
  }
  $Config | ConvertTo-Json -Depth 10 | Set-Content -Path $ConfigFile -Encoding UTF8
}

$env:GWC_GATEWAY_WS = $Config.gateway_ws_url
$env:GWC_NODE_ID = $Config.node_id
$env:GWC_NODE_NAME = $Config.node_name
Remove-Item Env:GWC_PAIRING_CODE -ErrorAction SilentlyContinue
$env:GWC_PERMISSION_LEVEL = $Config.permission_level
$env:GWC_ALLOWED_ROOTS = ($Config.allowed_roots -join [System.IO.Path]::PathSeparator)
$env:GWC_NODE_STATE = $StateFile

Write-Host ""
Write-Host "[Lucas] Ready" -ForegroundColor Green
Write-Host "  Node:      $($Config.node_name)"
Write-Host "  Gateway:   $($Config.gateway_ws_url)"
Write-Host "  Permission:$($Config.permission_level)"
Write-Host ""
Write-Host "[Lucas] Installing background startup..." -ForegroundColor Green

if (-not (Test-Path $VenvPythonw)) { throw "Lucas background launcher was not installed correctly." }

$TaskAction = New-ScheduledTaskAction -Execute $VenvPythonw -Argument "-m gpt_windows_connector.tray"
$TaskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$TaskSettings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -DontStopOnIdleEnd `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
  -MultipleInstances IgnoreNew

try {
  Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $TaskAction `
    -Trigger $TaskTrigger `
    -Settings $TaskSettings `
    -Description "Lucas Windows Node background agent" `
    -Force | Out-Null
} catch {
  Write-Host "[Lucas] ScheduledTasks registration failed, using compatibility mode..." -ForegroundColor Yellow
  $TaskCommand = "`"$VenvPythonw`" -m gpt_windows_connector.tray"
  & schtasks.exe /Create /TN $TaskName /SC ONLOGON /TR $TaskCommand /F | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Failed to register Lucas startup task." }
}

if (-not $LaunchAtStartup) {
  try { Disable-ScheduledTask -TaskName $TaskName | Out-Null } catch { & schtasks.exe /Change /TN $TaskName /DISABLE | Out-Null }
}

Write-Host "[Lucas] Creating Start menu and desktop shortcuts..." -ForegroundColor Green
try {
  $WshShell = New-Object -ComObject WScript.Shell
  $ShortcutTargets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Lucas.lnk"),
    (Join-Path (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs") "Lucas.lnk")
  )
  foreach ($ShortcutPath in $ShortcutTargets) {
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $VenvPythonw
    $Shortcut.Arguments = "-m gpt_windows_connector.launcher"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "Open or start Lucas"
    $Shortcut.Save()
  }
} catch {
  Write-Host "[Lucas] Could not create one or more shortcuts: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "[Lucas] Starting in the Windows notification area..." -ForegroundColor Green
# Start through Task Scheduler so Windows owns and supervises the tray process
# immediately. If Task Scheduler cannot start it, fall back to direct launch.
$TrayStarted = $false
try {
  Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
  Start-Sleep -Seconds 2
  $TrayStarted = $true
} catch {
  Write-Host "[Lucas] Scheduled tray start failed; using direct fallback..." -ForegroundColor Yellow
}
if (-not $TrayStarted) {
  Start-Process -FilePath $VenvPythonw -ArgumentList "-m","gpt_windows_connector.tray" -WindowStyle Hidden
  Start-Sleep -Seconds 2
}

# Installation always finishes by opening the Lucas app (Settings). The tray and
# node are already running in the background; Settings is the visible app surface.
Write-Host "[Lucas] Opening Lucas..." -ForegroundColor Cyan
Start-Process -FilePath $VenvPythonw -ArgumentList "-m","gpt_windows_connector.node","--configure" -WindowStyle Hidden

Write-Host ""
Write-Host "[Lucas] Installed successfully." -ForegroundColor Green
Write-Host "Lucas now runs in the background with a system tray icon."
Write-Host "Open Lucas from the desktop or Start menu. If Lucas is already running, the shortcut opens Settings."
Write-Host "Use the tray icon to connect/disconnect, reconnect, restart Lucas, view logs, or change startup behavior."
Write-Host "Share the Node ID shown in Lucas Settings; each Lucas account must be approved locally before access."
Write-Host "After reboot or sign-in, Lucas starts automatically when Launch at startup is enabled."
Write-Host ""
exit 0

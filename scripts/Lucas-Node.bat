@echo off
setlocal EnableExtensions

title Lucas Windows Node

echo.
echo ========================================
echo          LUCAS WINDOWS NODE
echo ========================================
echo.

rem Lightweight bootstrapper:
rem - Keeps a cached copy of the PowerShell installer.
rem - Uses ETag / Last-Modified to download it only when the server copy changed.
rem - Reuses the cached installer when unchanged or when the network is temporarily unavailable.
rem - The PowerShell installer itself performs the incremental Lucas update and preserves local settings.

set "LUCAS_DIR=%LOCALAPPDATA%\Lucas"
set "LUCAS_BOOTSTRAP_DIR=%LUCAS_DIR%\bootstrap"
set "LUCAS_PS1=%LUCAS_BOOTSTRAP_DIR%\Lucas-Node.ps1"
set "LUCAS_META=%LUCAS_BOOTSTRAP_DIR%\Lucas-Node.meta.json"
set "LUCAS_URL=https://lucasmcp.com/download/Lucas-Node.ps1"

if not exist "%LUCAS_BOOTSTRAP_DIR%" mkdir "%LUCAS_BOOTSTRAP_DIR%" >nul 2>&1

echo [Lucas] Checking bootstrap updates...

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$url=$env:LUCAS_URL; $target=$env:LUCAS_PS1; $metaPath=$env:LUCAS_META;" ^
  "$headers=@{}; $oldMeta=$null;" ^
  "if(Test-Path $metaPath){try{$oldMeta=Get-Content -Raw -LiteralPath $metaPath | ConvertFrom-Json}catch{}};" ^
  "if($oldMeta){if($oldMeta.ETag){$headers['If-None-Match']=[string]$oldMeta.ETag}; if($oldMeta.LastModified){$headers['If-Modified-Since']=[string]$oldMeta.LastModified}};" ^
  "$tmp=$target+'.download';" ^
  "try{" ^
    "try{$r=Invoke-WebRequest -UseBasicParsing -Uri $url -Headers $headers -OutFile $tmp -PassThru}catch{if($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 304){Write-Host '[Lucas] Bootstrap is already current.' -ForegroundColor Green; exit 0}else{throw}};" ^
    "if(-not (Test-Path $tmp)){if(Test-Path $target){Write-Host '[Lucas] Bootstrap is already current.' -ForegroundColor Green; exit 0}; throw 'Bootstrap download produced no file.'};" ^
    "if((Get-Item -LiteralPath $tmp).Length -lt 100){throw 'Downloaded bootstrap is unexpectedly small.'};" ^
    "$newHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $tmp).Hash; $oldHash=''; if(Test-Path $target){$oldHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash};" ^
    "if($newHash -ne $oldHash){Move-Item -Force -LiteralPath $tmp -Destination $target; Write-Host '[Lucas] Bootstrap updated.' -ForegroundColor Green}else{Remove-Item -Force -LiteralPath $tmp -ErrorAction SilentlyContinue; Write-Host '[Lucas] Bootstrap unchanged; no download replacement needed.' -ForegroundColor Green};" ^
    "$etag=''; $last=''; if($r.Headers){$etag=[string]$r.Headers['ETag']; $last=[string]$r.Headers['Last-Modified']};" ^
    "@{ETag=$etag;LastModified=$last;SHA256=$newHash;CheckedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath $metaPath;" ^
  "}catch{" ^
    "Remove-Item -Force -LiteralPath $tmp -ErrorAction SilentlyContinue;" ^
    "if(Test-Path $target){Write-Host ('[Lucas] Update check failed; using cached bootstrap: '+$_.Exception.Message) -ForegroundColor Yellow; exit 0};" ^
    "Write-Host ('[Lucas] Could not download bootstrap: '+$_.Exception.Message) -ForegroundColor Red; exit 1" ^
  "}"

if errorlevel 1 goto :failed
if not exist "%LUCAS_PS1%" goto :failed

echo [Lucas] Starting incremental update / Node launcher...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LUCAS_PS1%" %*
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
  echo [Lucas] Node exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%

:failed
echo.
echo [Lucas] No usable Lucas bootstrap is available.
pause
exit /b 1

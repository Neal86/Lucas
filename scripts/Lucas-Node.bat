@echo off
setlocal
title Lucas Windows Node
echo.
echo ========================================
echo          LUCAS WINDOWS NODE
echo ========================================
echo.
set "LUCAS_PS1=%TEMP%\Lucas-Node.ps1"
echo [Lucas] Downloading latest pairing script...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing 'https://lucasmcp.com/download/Lucas-Node.ps1' -OutFile '%LUCAS_PS1%' } catch { Write-Host $_ -ForegroundColor Red; exit 1 }"
if errorlevel 1 goto :failed
echo [Lucas] Starting...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LUCAS_PS1%"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
  echo [Lucas] Node exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
:failed
echo.
echo [Lucas] Could not download the latest node script.
pause
exit /b 1

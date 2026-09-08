@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0tools\Install-Manager.ps1" -EnableStartup -StartMonitor
if errorlevel 1 (
  echo Installation failed. Read the message above.
  pause
  exit /b 1
)
pause

@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0updater.ps1"
set "UPDATE_EXIT=%ERRORLEVEL%"

echo.
if "%UPDATE_EXIT%"=="0" (
  echo Update finished.
) else (
  echo Update failed. Exit code: %UPDATE_EXIT%
)
pause
exit /b %UPDATE_EXIT%

@echo off
setlocal
cd /d "%~dp0"

rem Locate the install root: this folder, or its parent when the repair zip
rem was extracted into a sub folder of the tool root.
set "ROOT=%~dp0"
if not exist "%ROOT%version.json" (
  if exist "%ROOT%..\version.json" for /f %I in ("%ROOT%..") do set "ROOT=%~fI\
)
if not exist "%ROOT%version.json" (
  echo Please extract ALL files from the zip into the tool root folder
  echo ^(the folder that contains version.json^), then run this file again.
  pause
  exit /b 1
)

rem When run from a repair-zip sub folder, sync the bundled updater and
rem update package into the install root before updating.
if /I not "%ROOT%"=="%~dp0" (
  if exist updater.ps1 copy /y updater.ps1 "%ROOT%updater.ps1" >nul
  copy /y *-v*.zip "%ROOT%" >nul 2>&1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%updater.ps1"
set "UPDATE_EXIT=%ERRORLEVEL%"

echo.
if "%UPDATE_EXIT%"=="0" (
  echo Update finished.
) else (
  echo Update failed. Exit code: %UPDATE_EXIT%
)
pause
exit /b %UPDATE_EXIT%

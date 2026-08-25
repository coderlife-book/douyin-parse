@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0更新工具.ps1"
set "UPDATE_EXIT=%ERRORLEVEL%"

echo.
if "%UPDATE_EXIT%"=="0" (
  echo 更新流程已结束。
) else (
  echo 更新失败，错误码：%UPDATE_EXIT%
)
pause
exit /b %UPDATE_EXIT%

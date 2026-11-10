@echo off
rem Step 2, only for the live simulator: right-click, Run as administrator
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp02_enable_wsl.ps1"  %*
echo.
pause

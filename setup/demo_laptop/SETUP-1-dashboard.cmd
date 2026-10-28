@echo off
rem Step 1: dashboard (20-30 min)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp01_setup_dashboard.ps1"  %*
echo.
pause

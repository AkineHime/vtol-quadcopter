@echo off
rem Dashboard + a fake aircraft circling the field (no WSL needed)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_demo.ps1" -Fake %*
echo.
pause

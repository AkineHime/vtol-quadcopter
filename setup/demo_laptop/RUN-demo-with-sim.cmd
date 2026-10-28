@echo off
rem Dashboard + the autopilot in JSBSim flying the dashboard's plan
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_demo.ps1" -Sim %*
echo.
pause

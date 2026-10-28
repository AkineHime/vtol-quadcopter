@echo off
rem Step 3, only for the live simulator: ArduPilot + JSBSim in WSL (1-2 h)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp03_setup_sim.ps1"  %*
echo.
pause

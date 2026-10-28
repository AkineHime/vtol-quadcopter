# Coconut VTOL: run 3_setup_sim.sh inside WSL Ubuntu 24.04 (ArduPilot SITL + JSBSim).
#   Run:  double-click SETUP-3-simulator.cmd
param([string]$Dir = "C:\coconut")
$ErrorActionPreference = "Stop"
$Repo = Join-Path $Dir "vtol-quadcopter"
if (-not (Test-Path (Join-Path $Repo "flight_software\sim_runner.py"))) { throw "No repo at ${Repo}: run SETUP-1-dashboard.cmd first." }

# copy the script into Ubuntu with Unix line endings (mail and zip tools sometimes add CRLF)
$sh = ([IO.File]::ReadAllText((Join-Path $PSScriptRoot "3_setup_sim.sh"))) -replace "`r`n", "`n"
$tmp = Join-Path $env:TEMP "coconut_setup_sim.sh"
[IO.File]::WriteAllText($tmp, $sh, (New-Object Text.UTF8Encoding($false)))

$wslTmp = (wsl.exe -d Ubuntu-24.04 -- wslpath -a ($tmp -replace "\\", "/")).Trim()
$wslRepo = (wsl.exe -d Ubuntu-24.04 -- wslpath -a ($Repo -replace "\\", "/")).Trim()
if (-not $wslTmp -or -not $wslRepo) { throw "Ubuntu-24.04 is not ready: run SETUP-2-wsl.cmd and restart first." }

Write-Host "Setting up the simulator inside Ubuntu: about 1-2 hours. Keep the laptop plugged in and awake." -ForegroundColor Cyan
wsl.exe -d Ubuntu-24.04 -- bash $wslTmp $wslRepo
if ($LASTEXITCODE -ne 0) { throw "Simulator setup failed: scroll up for the first error, or see CHECKLIST.md." }

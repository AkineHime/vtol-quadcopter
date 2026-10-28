# Coconut VTOL demo: start the dashboard and open it, optionally with an aircraft.
#   RUN-demo.cmd            dashboard only (farm, plan, prediction, phone camera, past flights)
#   RUN-demo-fake.cmd       + a fake aircraft circling the field (no WSL needed)
#   RUN-demo-with-sim.cmd   + the real autopilot in JSBSim flying the dashboard's plan (~10 min)
param(
    [string]$Repo = "",             # default: see paths.ps1
    [switch]$Fake,
    [switch]$Sim
)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "paths.ps1")
$Repo = Resolve-Repo $Repo
$GS = Join-Path $Repo "ground_station"
$py = Join-Path $GS ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Not set up yet: run SETUP-1-dashboard.cmd first." }

function Up { try { Invoke-RestMethod "http://127.0.0.1:8080/api/plan" -TimeoutSec 2 | Out-Null; $true } catch { $false } }

if (-not (Up)) {
    Start-Process powershell -WorkingDirectory $GS -ArgumentList "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle = 'Coconut dashboard (close to stop)'; & '$py' -u run.py"
    $i = 0
    while (-not (Up)) {
        Start-Sleep -Seconds 1
        if (++$i -gt 40) { throw "The dashboard did not start: look at the 'Coconut dashboard' window for the error." }
    }
}
Start-Process "http://localhost:8080"
Write-Host "Dashboard: http://localhost:8080  (phones and tablets: the https address in the dashboard window)" -ForegroundColor Green

if ($Fake) {
    Start-Process powershell -WorkingDirectory $GS -ArgumentList "-NoExit", "-Command",
        "`$host.UI.RawUI.WindowTitle = 'Fake aircraft (close to stop)'; & '$py' tests\fake_vehicle.py"
    Write-Host "Fake aircraft started: it appears on the map within a few seconds." -ForegroundColor Green
}

if ($Sim) {
    $ids = ((Invoke-RestMethod "http://127.0.0.1:8080/api/plan").stops | ForEach-Object { $_.tree }) -join ","
    if (-not $ids) { throw "The plan has no stops: mark a palm as target in the dashboard first." }
    $wslRepo = (wsl.exe -d Ubuntu-24.04 -- wslpath -a ($Repo -replace "\\", "/")).Trim()
    $name = "demo_" + (Get-Date -Format "yyyyMMdd_HHmm")
    Write-Host "Flying $($ids.Split(',').Count) stops in JSBSim ($name). The drone appears on the dashboard in about a minute; the flight takes ~10 min." -ForegroundColor Cyan
    wsl.exe -d Ubuntu-24.04 -- bash -lc "source ~/venv-ardupilot/bin/activate && cd '$wslRepo/flight_software' && python sim_runner.py $name --physics jsbsim --strategy hybrid --targets $ids --timeout 2400 2>&1 | tail -1 | cut -c1-300"
    Write-Host "Flight finished. Open Flights (rail, left) for the replay and the post-flight report." -ForegroundColor Green
}

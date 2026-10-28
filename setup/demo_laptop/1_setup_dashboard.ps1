# Coconut VTOL ground station: set up the dashboard on a new Windows laptop.
#   Installs Git, Python 3.13 and Node.js (winget) if missing, clones the repo,
#   installs the Python and web dependencies, builds the dashboard and makes
#   its HTTPS certificate. Safe to run again: it skips what is already there.
#
#   Run:  double-click SETUP-1-dashboard.cmd   (or)
#         powershell -ExecutionPolicy Bypass -File 1_setup_dashboard.ps1 [-Dir C:\coconut] [-Branch name]
param(
    [string]$Dir = "C:\coconut",
    [string]$Branch = "dashboard-ml-mission-link"
)
$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/AkineHime/vtol-quadcopter.git"
$Repo = Join-Path $Dir "vtol-quadcopter"
$GS = Join-Path $Repo "ground_station"

function Step($m) { Write-Host "`n== $m" -ForegroundColor Cyan }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function RefreshPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Run([string]$exe, [string[]]$a) {
    $ErrorActionPreference = "Continue"
    & $exe @a
    if ($LASTEXITCODE -ne 0) { throw "failed ($LASTEXITCODE): $exe $($a -join ' ')" }
}
function PyVersion {        # a Python the dashboard is tested on (3.11-3.13), via the py launcher
    if (-not (Have py)) { return $null }
    foreach ($v in "3.13", "3.12", "3.11") {
        $ErrorActionPreference = "Continue"     # py writes to stderr when a version is missing
        $null = & py "-$v" --version 2>&1
        if ($LASTEXITCODE -eq 0) { return $v }
    }
    return $null
}

$t0 = Get-Date
RefreshPath          # pick up tools installed since this window opened

Step "1/5  Tools: Git, Python 3.13, Node.js LTS"
if (-not (Have winget)) {
    throw "winget is missing: install 'App Installer' from the Microsoft Store, then run this again."
}
$tools = @(
    @{ name = "Git"; ok = { Have git }; id = "Git.Git" },
    @{ name = "Python"; ok = { [bool](PyVersion) }; id = "Python.Python.3.13" },
    @{ name = "Node.js"; ok = { Have npm }; id = "OpenJS.NodeJS.LTS" }
)
foreach ($t in $tools) {
    if (& $t.ok) { Write-Host "  $($t.name): found" ; continue }
    Write-Host "  $($t.name): installing (a Windows prompt may ask for permission)"
    winget install -e --id $t.id --silent --accept-source-agreements --accept-package-agreements
    RefreshPath
    if (-not (& $t.ok)) { throw "$($t.name) did not install. Install it by hand, close this window, and run the script again." }
}

Step "2/5  Code: $Repo ($Branch)"
if (Test-Path (Join-Path $Repo ".git")) {
    Run git @("-C", $Repo, "fetch", "origin")
    Run git @("-C", $Repo, "checkout", $Branch)
    Run git @("-C", $Repo, "pull", "--ff-only")
} else {
    New-Item -ItemType Directory -Force $Dir | Out-Null
    Run git @("clone", "--branch", $Branch, $RepoUrl, $Repo)
}

Step "3/5  Python packages (ground_station\.venv)"
$py = Join-Path $GS ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Run py @("-$(PyVersion)", "-m", "venv", (Join-Path $GS ".venv")) }
Run $py @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Run $py @("-m", "pip", "install", "--quiet", "-r", (Join-Path $GS "requirements.txt"))

Step "4/5  Dashboard build (frontend\dist)"
Push-Location (Join-Path $GS "frontend")
try {
    Run npm @("ci", "--no-audit", "--no-fund")
    Run npm @("run", "build")
} finally { Pop-Location }

Step "5/5  HTTPS certificate + quick check"
Push-Location $GS
try {
    Run $py @("-c", "from backend import config; from backend.certs import ensure_cert; c, k, ips = ensure_cert(config.CERT_DIR); print('  certificate for', ', '.join(['localhost', *ips]))")
    Run $py @("-c", "import backend.app; print('  backend imports OK')")
} finally { Pop-Location }

$ca = Join-Path $GS "certs\ca.pem"
$thumb = (New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $ca).Thumbprint
$mins = [math]::Round(((Get-Date) - $t0).TotalMinutes)
Write-Host "`nDone in $mins min." -ForegroundColor Green
Write-Host @"

Next (see CHECKLIST.md):
  * Start the demo:   double-click RUN-demo.cmd   (dashboard at http://localhost:8080)
  * Optional, removes the browser warning on https://<this laptop>:8443 -- run it yourself:
        certutil -user -addstore Root "$ca"
    Windows asks to confirm; the thumbprint must be $thumb.
    Then close every browser window and reopen.
"@

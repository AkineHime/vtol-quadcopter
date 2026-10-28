# Coconut VTOL: turn on WSL2 with Ubuntu 24.04 (needed only for the live simulator).
#   Needs administrator rights and a restart.
#   Run:  right-click SETUP-2-wsl.cmd -> Run as administrator
$ErrorActionPreference = "Stop"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "Run this as administrator (right-click SETUP-2-wsl.cmd -> Run as administrator)." }

$have = (wsl.exe -l -q 2>$null) -replace "`0", "" | Where-Object { $_ -match "Ubuntu-24.04" }
if ($have) {
    Write-Host "Ubuntu-24.04 is already installed. Next: SETUP-3-simulator.cmd" -ForegroundColor Green
    exit 0
}
wsl.exe --install -d Ubuntu-24.04
if ($LASTEXITCODE -ne 0) { throw "wsl --install failed ($LASTEXITCODE). Virtualization may be off in the BIOS (see CHECKLIST.md)." }
Write-Host @"

WSL is installing. Now:
  1. Restart the laptop.
  2. Ubuntu opens by itself after the restart (or start 'Ubuntu 24.04' from the Start menu).
     It asks for a new UNIX username and password: pick any, and remember the password
     (the simulator setup asks for it once).
  3. Close Ubuntu, then double-click SETUP-3-simulator.cmd.
"@ -ForegroundColor Green

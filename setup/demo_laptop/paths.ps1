# Where the repo is, with no drive or user folder written into the scripts.
# Dot-sourced by the other setup scripts:   . (Join-Path $PSScriptRoot "paths.ps1")
#
#   -Repo PATH given          -> that folder (a relative path counts from the current directory)
#   scripts inside a clone    -> that clone (they live in <repo>\setup\demo_laptop)
#   scripts unzipped alone    -> a "vtol-quadcopter" folder next to the scripts' folder
function Resolve-Repo([string]$Repo) {
    if ($Repo) {
        if (-not [IO.Path]::IsPathRooted($Repo)) { $Repo = Join-Path (Get-Location).Path $Repo }
        return [IO.Path]::GetFullPath($Repo)
    }
    $clone = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
    if (Test-Path (Join-Path $clone "ground_station\run.py")) { return $clone }
    return [IO.Path]::GetFullPath((Join-Path (Split-Path $PSScriptRoot -Parent) "vtol-quadcopter"))
}

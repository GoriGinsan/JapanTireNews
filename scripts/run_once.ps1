$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$StampPath = Join-Path $ProjectRoot ".venv\requirements.stamp"
$RequirementsPath = Join-Path $ProjectRoot "requirements.txt"
$NeedsInstall = -not (Test-Path $StampPath)

if (-not $NeedsInstall) {
    $NeedsInstall = (Get-Item $RequirementsPath).LastWriteTimeUtc -gt (Get-Item $StampPath).LastWriteTimeUtc
}

if ($NeedsInstall) {
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    New-Item -ItemType File -Path $StampPath -Force | Out-Null
}

& ".\.venv\Scripts\python.exe" -m japan_tire_news


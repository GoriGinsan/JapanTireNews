$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$LogsDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null

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

$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
$RunLogPath = Join-Path $LogsDir ("run_{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

try {
    $Output = & ".\.venv\Scripts\python.exe" -m japan_tire_news 2>&1
    $ExitCode = $LASTEXITCODE
    $Output | Tee-Object -FilePath $RunLogPath

    if ($ExitCode -ne 0) {
        throw "japan_tire_news exited with code $ExitCode"
    }
} catch {
    $FailureText = @(
        "JapanTireNews scheduled run failed.",
        "",
        "Time: $Stamp",
        "Machine: $env:COMPUTERNAME",
        "Project: $ProjectRoot",
        "Log: $RunLogPath",
        "",
        "Error:",
        '```',
        "$($_.Exception.Message)",
        '```',
        "",
        "Output:",
        '```',
        ($Output -join "`r`n"),
        '```'
    ) -join "`r`n"

    $IssueTitle = "JapanTireNews scheduled run failed on $env:COMPUTERNAME"
    $HashInput = "$($_.Exception.Message)`n$($Output -join "`n")"
    $HashBytes = [System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($HashInput))
    $FailureHash = [Convert]::ToHexString($HashBytes)
    $LastFailureHashPath = Join-Path $LogsDir "last_failure_issue_hash.txt"
    $LastFailureHash = if (Test-Path $LastFailureHashPath) {
        Get-Content -LiteralPath $LastFailureHashPath -Raw
    } else {
        ""
    }

    if ($LastFailureHash.Trim() -ne $FailureHash) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\create_github_issue.ps1" -Title $IssueTitle -Body $FailureText -Labels @("bug", "automation", "fatal")
        $FailureHash | Set-Content -LiteralPath $LastFailureHashPath -Encoding ASCII
    } else {
        Write-Warning "Skipping GitHub issue creation because this failure was already reported."
    }

    throw
}


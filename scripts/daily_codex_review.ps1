param(
    [switch]$Autofix
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    $envPath = Join-Path (Get-Location) ".env"
    if (-not (Test-Path $envPath)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }

        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            continue
        }

        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if (-not [string]::IsNullOrWhiteSpace($name) -and [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Resolve-GitCommand {
    $command = Get-Command git -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files\Git\bin\git.exe",
        "$env:LOCALAPPDATA\GitHubDesktop\app-3.5.8\resources\app\git\cmd\git.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "git.exe was not found. Install Git for Windows or add it to PATH."
}

function Resolve-CodexCommand {
    $command = Get-Command codex -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "codex CLI was not found. Install and authenticate Codex CLI before enabling this job."
}

function Resolve-GhCommand {
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Get-OpenIssuesSummary {
    $gh = Resolve-GhCommand
    if ($gh) {
        $issues = & $gh issue list --state open --limit 20 --json number,title,labels,url
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($issues)) {
            return $issues
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
        $git = Resolve-GitCommand
        $remote = & $git remote get-url origin
        if ($remote -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$") {
            $uri = "https://api.github.com/repos/$($Matches.owner)/$($Matches.repo)/issues?state=open&per_page=20"
            return Invoke-RestMethod `
                -Method Get `
                -Uri $uri `
                -Headers @{
                    Authorization = "Bearer $env:GITHUB_TOKEN"
                    Accept = "application/vnd.github+json"
                    "X-GitHub-Api-Version" = "2022-11-28"
                } | ConvertTo-Json -Depth 6
        }
    }

    return "[]"
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
Import-DotEnv

$git = Resolve-GitCommand
& $git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    throw "git pull failed."
}

$issues = Get-OpenIssuesSummary
$logsDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$promptPath = Join-Path $logsDir "codex_daily_prompt.md"

$modeText = if ($Autofix) {
    "If there is a fatal automation issue, fix it without asking the user, commit the change, and push a branch named codex/autofix-YYYYMMDD-HHMM. Do not commit secrets, .env, data, logs, or .venv. If there is no fatal issue, only write a concise improvement proposal."
} else {
    "Do not edit files. Review the open issues and the current code, then write a concise proposal for improving news quality and operational reliability."
}

@"
You are maintaining the JapanTireNews automation on this PC.

Open GitHub issues:

```json
$issues
```

Task:
$modeText

Important context:
- The hourly news job is run by scripts/run_once.ps1.
- GitHub issue creation is handled by scripts/create_github_issue.ps1.
- The Teams webhook is stored in .env and must never be committed.
- Keep changes small and verify with:
  .\.venv\Scripts\python.exe -m japan_tire_news --dry-run --force
"@ | Set-Content -LiteralPath $promptPath -Encoding UTF8

$codex = Resolve-CodexCommand
& $codex --full-auto (Get-Content -LiteralPath $promptPath -Raw)

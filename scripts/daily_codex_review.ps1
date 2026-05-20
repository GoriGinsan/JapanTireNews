param(
    [switch]$Autofix
)

$ErrorActionPreference = "Stop"

function Initialize-ToolPath {
    $paths = @(
        "C:\Program Files\Git\cmd",
        "C:\Program Files\GitHub CLI",
        "C:\Program Files\nodejs",
        "$env:APPDATA\npm"
    )

    [array]::Reverse($paths)
    foreach ($path in $paths) {
        if ((Test-Path $path) -and ($env:PATH -notlike "*$path*")) {
            $env:PATH = "$path;$env:PATH"
        }
    }
}

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

function Resolve-CodexInvocation {
    $nodeCandidates = @(
        "C:\Program Files\nodejs\node.exe",
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    )
    $codexScript = "$env:APPDATA\npm\node_modules\@openai\codex\bin\codex.js"

    foreach ($node in $nodeCandidates) {
        if ((Test-Path $node) -and (Test-Path $codexScript)) {
            return @{
                File = $node
                BaseArgs = @($codexScript)
            }
        }
    }

    $command = Get-Command codex -ErrorAction SilentlyContinue
    if ($command -and ($command.Source -notlike "*\WindowsApps\*")) {
        return @{
            File = $command.Source
            BaseArgs = @()
        }
    }

    throw "codex CLI was not found in a runnable location. Install with npm install -g @openai/codex and ensure Node.js is available."
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

function Invoke-NewsQualityAudit {
    param(
        [string]$LogsDir
    )

    $reportPath = Join-Path $LogsDir ("news_quality_audit_{0}.md" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $output = & ".\.venv\Scripts\python.exe" -m japan_tire_news.quality_audit --force --limit 10 --output $reportPath 2>&1
    $exitCode = $LASTEXITCODE
    $output | Set-Content -LiteralPath (Join-Path $LogsDir "last_news_quality_audit.log") -Encoding UTF8

    if ($exitCode -eq 0) {
        return @{
            HasFindings = $false
            ReportPath = $reportPath
            Report = ($output -join "`r`n")
        }
    }

    if ($exitCode -eq 2) {
        $hashInput = $output -join "`n"
        $hashBytes = [System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($hashInput))
        $qualityHash = [Convert]::ToHexString($hashBytes)
        $lastQualityHashPath = Join-Path $LogsDir "last_quality_issue_hash.txt"
        $lastQualityHash = if (Test-Path $lastQualityHashPath) {
            Get-Content -LiteralPath $lastQualityHashPath -Raw
        } else {
            ""
        }

        $body = @(
            "The daily news-quality audit detected low-quality items that could be posted to Teams.",
            "",
            "Audit report path: $reportPath",
            "",
            "Report:",
            '```markdown',
            ($output -join "`r`n"),
            '```',
            "",
            "Expected behavior:",
            "- Category, product-list, tire/wheel listing, and motorsports index pages should not rank as news.",
            "- The collection and classification filters should reject these items before Teams posting."
        ) -join "`r`n"

        if ($lastQualityHash.Trim() -ne $qualityHash) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\create_github_issue.ps1" `
                -Title "JapanTireNews news-quality audit detected non-news pages" `
                -Body $body `
                -Labels @("bug", "automation", "news-quality")
            $qualityHash | Set-Content -LiteralPath $lastQualityHashPath -Encoding ASCII
        } else {
            Write-Warning "Skipping GitHub issue creation because this news-quality finding was already reported."
        }

        return @{
            HasFindings = $true
            ReportPath = $reportPath
            Report = ($output -join "`r`n")
        }
    }

    throw "News quality audit failed with exit code $exitCode."
}

function Send-TeamsNotification {
    param(
        [string]$Title,
        [string]$Message
    )

    if ([string]::IsNullOrWhiteSpace($env:TEAMS_WEBHOOK_URL)) {
        Write-Warning "TEAMS_WEBHOOK_URL is not configured. Skipping Teams notification."
        return
    }

    $payload = @{
        '$schema' = "http://adaptivecards.io/schemas/adaptive-card.json"
        type = "AdaptiveCard"
        version = "1.4"
        msteams = @{
            width = "Full"
        }
        body = @(
            @{
                type = "TextBlock"
                text = $Title
                weight = "Bolder"
                size = "Medium"
                wrap = $true
            },
            @{
                type = "TextBlock"
                text = $Message
                wrap = $true
            }
        )
    } | ConvertTo-Json -Depth 8

    Invoke-RestMethod -Method Post -Uri $env:TEAMS_WEBHOOK_URL -Body $payload -ContentType "application/json" | Out-Null
}

function New-CodexPullRequest {
    param(
        [string]$GitPath,
        [string]$GhPath
    )

    if (-not $GhPath) {
        Write-Warning "GitHub CLI was not found. Skipping PR creation."
        return $null
    }

    $branch = (& $GitPath branch --show-current).Trim()
    if ([string]::IsNullOrWhiteSpace($branch) -or $branch -eq "main") {
        Write-Host "No Codex autofix branch is checked out. Skipping PR creation."
        return $null
    }

    if ($branch -notlike "codex/autofix-*") {
        Write-Host "Current branch '$branch' is not a Codex autofix branch. Skipping PR creation."
        return $null
    }

    $status = & $GitPath status --porcelain
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        Write-Warning "Working tree is not clean after Codex run. Skipping PR creation."
        return $null
    }

    & $GitPath push -u origin $branch
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed for $branch."
    }

    $existingPr = & $GhPath pr list --head $branch --state open --json url --jq ".[0].url"
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($existingPr)) {
        Write-Host "Pull request already exists: $existingPr"
        return $existingPr
    }

    $title = "Autofix JapanTireNews automation issue"
    $body = @"
Created automatically by the local Codex review task.

Verification requested before merge:

```powershell
.\.venv\Scripts\python.exe -m japan_tire_news --dry-run --force
```

Secrets and runtime files such as `.env`, `.venv`, `data/`, and `logs/` should remain uncommitted.
"@

    $prOutput = & $GhPath pr create --base main --head $branch --title $title --body $body
    if ($LASTEXITCODE -ne 0) {
        throw "gh pr create failed for $branch."
    }
    return ($prOutput | Select-Object -Last 1)
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
Initialize-ToolPath
Import-DotEnv

$git = Resolve-GitCommand
& $git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    throw "git pull failed."
}
$logsDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
$qualityAudit = Invoke-NewsQualityAudit -LogsDir $logsDir
$issues = Get-OpenIssuesSummary
$promptPath = Join-Path $logsDir "codex_daily_prompt.md"

$modeText = if ($Autofix) {
    "If there is a fatal automation issue, fix it without asking the user, commit the change, and leave the repository on a branch named codex/autofix-YYYYMMDD-HHMM. Do not create a pull request yourself; this wrapper script will create it after you finish. Do not commit secrets, .env, data, logs, or .venv. If there is no fatal issue, only write a concise improvement proposal."
} else {
    "Do not edit files. Review the open issues and the current code, then write a concise proposal for improving news quality and operational reliability."
}

@"
You are maintaining the JapanTireNews automation on this PC.

Open GitHub issues:

```json
$issues
```

Latest news-quality audit:

```markdown
$($qualityAudit.Report)
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

$codex = Resolve-CodexInvocation
$prompt = Get-Content -LiteralPath $promptPath -Raw

if ($Autofix) {
    $codexArgs = @(
        "exec",
        "-C", $ProjectRoot,
        "--dangerously-bypass-approvals-and-sandbox",
        "-"
    )
} else {
    $codexArgs = @(
        "exec",
        "-C", $ProjectRoot,
        "-s", "read-only",
        "-"
    )
}

$prompt | & $codex.File @($codex.BaseArgs + $codexArgs)
if ($LASTEXITCODE -ne 0) {
    throw "Codex CLI failed with exit code $LASTEXITCODE."
}

if ($Autofix) {
    $prUrl = New-CodexPullRequest -GitPath $git -GhPath (Resolve-GhCommand)
    if (-not [string]::IsNullOrWhiteSpace($prUrl)) {
        Send-TeamsNotification `
            -Title "JapanTireNews Codex改善を実行しました" `
            -Message "Codexが自動修正ブランチをPushし、Pull Requestを作成しました。PR: $prUrl"
    }
}

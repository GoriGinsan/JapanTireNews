param(
    [Parameter(Mandatory = $true)]
    [string]$Title,

    [Parameter(Mandatory = $true)]
    [string]$Body,

    [string[]]$Labels = @("bug", "automation")
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

function Get-GitHubRepository {
    $git = Resolve-GitCommand
    $remote = & $git remote get-url origin
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remote)) {
        throw "Could not read origin remote URL."
    }

    if ($remote -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$") {
        return @{
            Owner = $Matches.owner
            Repo = $Matches.repo
        }
    }

    throw "Origin remote is not a GitHub repository: $remote"
}

function Ensure-GitHubLabels {
    param(
        [string]$GhPath,
        [string]$RepoName,
        [string[]]$LabelNames
    )

    $labelDefinitions = @{
        automation = @{
            Color = "5319e7"
            Description = "Created by local automation"
        }
        fatal = @{
            Color = "b60205"
            Description = "Blocks scheduled automation"
        }
        bug = @{
            Color = "d73a4a"
            Description = "Something is not working"
        }
        "news-quality" = @{
            Color = "fbca04"
            Description = "News selection or ranking quality issue"
        }
    }

    $existing = & $GhPath label list --repo $RepoName --limit 200 --json name | ConvertFrom-Json
    $existingNames = @($existing | ForEach-Object { $_.name })

    foreach ($label in $LabelNames) {
        if ($existingNames -contains $label) {
            continue
        }

        $definition = $labelDefinitions[$label]
        if (-not $definition) {
            $definition = @{
                Color = "ededed"
                Description = "Created by local automation"
            }
        }

        & $GhPath label create $label --repo $RepoName --color $definition.Color --description $definition.Description
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create GitHub label: $label"
        }
    }
}

function Save-PendingIssue {
    param(
        [string]$Reason
    )

    $logsDir = Join-Path (Get-Location) "logs"
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $path = Join-Path $logsDir "pending_github_issue_$stamp.md"
    @(
        "# $Title",
        "",
        "Labels: $($Labels -join ', ')",
        "",
        "Issue creation failed: $Reason",
        "",
        $Body
    ) -join "`r`n" | Set-Content -LiteralPath $path -Encoding UTF8
    Write-Warning "Saved pending GitHub issue to $path"
}

Initialize-ToolPath
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
Import-DotEnv

$repository = Get-GitHubRepository

$gh = Resolve-GhCommand
if ($gh) {
    $repoName = "$($repository.Owner)/$($repository.Repo)"
    Ensure-GitHubLabels -GhPath $gh -RepoName $repoName -LabelNames $Labels

    $labelArgs = @()
    foreach ($label in $Labels) {
        $labelArgs += @("--label", $label)
    }

    & $gh issue create --repo $repoName --title $Title --body $Body @labelArgs
    if ($LASTEXITCODE -eq 0) {
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
        Save-PendingIssue -Reason "gh issue create failed with exit code $LASTEXITCODE, and GITHUB_TOKEN is not available."
        exit $LASTEXITCODE
    }

    Write-Warning "gh issue create failed with exit code $LASTEXITCODE. Falling back to GITHUB_TOKEN."
}

if ([string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
    Save-PendingIssue -Reason "Neither GitHub CLI (gh) nor GITHUB_TOKEN is available."
    exit 2
}

$uri = "https://api.github.com/repos/$($repository.Owner)/$($repository.Repo)/issues"
$payload = @{
    title = $Title
    body = $Body
    labels = $Labels
} | ConvertTo-Json -Depth 5

try {
    $response = Invoke-RestMethod `
        -Method Post `
        -Uri $uri `
        -Headers @{
            Authorization = "Bearer $env:GITHUB_TOKEN"
            Accept = "application/vnd.github+json"
            "X-GitHub-Api-Version" = "2022-11-28"
        } `
        -Body $payload `
        -ContentType "application/json"
    Write-Host $response.html_url
} catch {
    Save-PendingIssue -Reason $_.Exception.Message
    exit 1
}

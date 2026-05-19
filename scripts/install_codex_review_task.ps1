param(
    [string]$TaskName = "JapanTireNewsCodexReview",
    [switch]$Autofix
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "scripts\daily_codex_review.ps1"
$AutofixArg = if ($Autofix) { " -Autofix" } else { "" }
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"$AutofixArg"
$Trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Ask Codex CLI to review JapanTireNews issues and propose or apply fixes." -Force

Write-Host "Registered scheduled task: $TaskName"

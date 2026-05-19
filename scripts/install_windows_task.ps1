param(
    [string]$TaskName = "JapanTireNewsHourly"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "scripts\run_once.ps1"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Trigger = 9..18 | ForEach-Object {
    New-ScheduledTaskTrigger -Daily -At ("{0:00}:00" -f $_)
}
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Collect tire market news and post relevant items to Microsoft Teams." -Force

Write-Host "Registered scheduled task: $TaskName"

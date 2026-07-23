$taskName   = "kk-TorontoStreetsLayer"
$projectDir = $PSScriptRoot
$logFile    = "$projectDir\logs\scheduler.log"

if (-not (Test-Path "$projectDir\logs")) {
    New-Item -ItemType Directory -Path "$projectDir\logs" | Out-Null
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d `"$projectDir`" && python run.py update >> `"$logFile`" 2>&1"

# Weekly, not daily: the TCL centreline changes rarely and a full rebuild is
# multi-hour ('update' now exits early when the source is unchanged anyway).
# 09:00 keeps it clear of the sibling kk-TorontoAddressLayer task (14:00) so the
# two tippecanoe/WSL builds do not contend for resources.
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "Scheduled '$taskName' to run weekly on Monday at 09:00."
Write-Host "Log: $logFile"

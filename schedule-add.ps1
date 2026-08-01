$taskName   = "kk-TorontoStreetsLayer"
$projectDir = $PSScriptRoot
$logFile    = "$projectDir\logs\scheduler.log"

if (-not (Test-Path "$projectDir\logs")) {
    New-Item -ItemType Directory -Path "$projectDir\logs" | Out-Null
}

# A git process killed mid-write (a torn-down container with Code/ mounted is the
# usual culprit) leaves a zero-byte *.lock behind, and publish then fails every run
# until someone clears it by hand -- that cost the sibling address layers six days
# of updates in July 2026. Sweep first, best-effort: joined with & so a hiccup here
# can never block the build.
$lockCheck = Join-Path (Split-Path $projectDir -Parent) "check-git-locks.ps1"
if (-not (Test-Path $lockCheck)) { Write-Warning "Lock sweeper not found: $lockCheck" }

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d `"$projectDir`" && (powershell -NoProfile -ExecutionPolicy Bypass -File `"$lockCheck`" -Clear & python run.py update) >> `"$logFile`" 2>&1"

# Weekly, not daily: the TCL centreline changes rarely and a full rebuild is
# multi-hour ('update' now exits early when the source is unchanged anyway).
# 09:00 keeps it clear of the sibling kk-TorontoAddressLayer task (14:00) so the
# two tippecanoe/WSL builds do not contend for resources.
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "09:00"
# Restart on failure. 'update' exits 75 as soon as it sees no usable link
# instead of blocking on one (the ExecutionTimeLimit would kill a long wait
# anyway), so three tries half an hour apart turn a dead link at 09:00 into a
# run at 10:30 rather than a seven-day gap -- which is what a dead resolver
# cost this task on 2026-07-27.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "Scheduled '$taskName' to run weekly on Monday at 09:00."
Write-Host "Log: $logFile"

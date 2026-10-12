$ErrorActionPreference = "Stop"

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

# Monthly, on the 1st at 09:00. The City republishes the centreline weekly, but
# a release changes a handful of streets at most (see history.html), so a
# monthly build keeps the layer current without a rebuild every week; each
# build records one row of release history. 09:00 keeps it clear of the sibling
# kk-TorontoAddressLayer task (14:00) so the two tippecanoe/WSL builds do not
# contend for resources.
#
# New-ScheduledTaskTrigger has no -Monthly, and Register-ScheduledTask answers a
# client-side MSFT_TaskMonthlyTrigger with "The parameter is incorrect" (tried
# 2026-10-11). So schtasks creates the task with the monthly trigger and a
# placeholder action -- /F replaces the task wholesale -- and Set-ScheduledTask
# then gives it the real action and settings. The real action does not go
# through /TR: it is longer than /TR's 261 characters, and its quoting would
# not survive.
# Restart on failure. 'update' exits 75 as soon as it sees no usable link
# instead of blocking on one (the ExecutionTimeLimit would kill a long wait
# anyway), so three tries half an hour apart turn a dead link at 09:00 into a
# run at 10:30 rather than a month-long gap (a dead resolver cost the weekly
# task a whole week on 2026-07-27).
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30)

schtasks /Create /F /TN $taskName /SC MONTHLY /MO 1 /D 1 /ST 09:00 /TR "cmd.exe /c exit 0" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks /Create failed (exit $LASTEXITCODE)" }
Set-ScheduledTask -TaskName $taskName -Action $action -Settings $settings | Out-Null

Write-Host "Scheduled '$taskName' to run monthly on the 1st at 09:00."
Write-Host "Log: $logFile"

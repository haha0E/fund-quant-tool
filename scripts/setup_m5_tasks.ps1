# M5 scheduled task registration (idempotent: re-run overwrites same-name tasks)
# Admin PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_m5_tasks.ps1
#
# NOTE (2026-10-31): comments in this file are ASCII-only on purpose.
# PS 5.1 reads UTF-8-without-BOM scripts as GBK; a Chinese comment byte sequence
# swallowed the next line ($weekly = ...), so FQT_Weekly_Refresh silently never
# registered while the script still printed "done". Null guards + post-checks
# below make that failure mode impossible to miss again.
#
# Registers two scheduled tasks (never touches FQT_Web_Server -- red line:
# that task is only end/run, never reconfigured):
#   1. FQT_Weekly_Refresh -- Monday 09:30 full refresh (nav/profile/holdings/metrics/benchmark)
#   2. FQT_Daily_Snapshot -- daily 10:00 snapshot dir detection & import (idempotent)
$ErrorActionPreference = "Stop"
$repo = "D:\For_Coding\MyProjects\fund-quant-tool"
$py = "$repo\.venv\Scripts\python.exe"

$refreshAction = New-ScheduledTaskAction `
    -Execute $py -Argument "$repo\scripts\cron_call.py '/api/refresh?scope=all' POST" `
    -WorkingDirectory $repo
$snapshotAction = New-ScheduledTaskAction `
    -Execute $py -Argument "$repo\scripts\cron_call.py /api/snapshot/import POST" `
    -WorkingDirectory $repo

$weekly = New-ScheduledTaskTrigger -Weekly -At "09:30" -DaysOfWeek Monday
$daily = New-ScheduledTaskTrigger -Daily -At "10:00"
if (-not $weekly) { throw "weekly trigger is null" }
if (-not $daily) { throw "daily trigger is null" }

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "FQT_Weekly_Refresh" -Action $refreshAction `
    -Trigger $weekly -Settings $settings -Force | Out-Null
Register-ScheduledTask -TaskName "FQT_Daily_Snapshot" -Action $snapshotAction `
    -Trigger $daily -Settings $settings -Force | Out-Null

# Post-check: fail loudly if either task is missing (no false "done").
foreach ($name in @("FQT_Weekly_Refresh", "FQT_Daily_Snapshot")) {
    if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
        throw "post-check failed: $name not registered"
    }
}

Write-Host "done: FQT_Weekly_Refresh (Mon 09:30) + FQT_Daily_Snapshot (daily 10:00) registered and verified"

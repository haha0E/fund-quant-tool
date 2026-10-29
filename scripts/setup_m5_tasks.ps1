# M5 定时任务注册（幂等，重复运行覆盖同名任务）
# 管理员 PowerShell：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_m5_tasks.ps1
#
# 产出两个任务计划（不触碰 FQT_Web_Server——红线：该任务只 end/run 不改配置）：
#   1. FQT_Weekly_Refresh —— 每周一 09:30 全量刷新（净值/档案/持仓/指标/基准指数）
#   2. FQT_Daily_Snapshot —— 每日 10:00 快照目录检测导入（幂等）
$ErrorActionPreference = "Stop"
$repo = "D:\For_Coding\MyProjects\fund-quant-tool"
$py = "$repo\.venv\Scripts\python.exe"

$refreshAction = New-ScheduledTaskAction `
    -Execute $py -Argument "$repo\scripts\cron_call.py '/api/refresh?scope=all' POST" `
    -WorkingDirectory $repo
$snapshotAction = New-ScheduledTaskAction `
    -Execute $py -Argument "$repo\scripts\cron_call.py /api/snapshot/import POST" `
    -WorkingDirectory $repo

# 周一 09:30（双周核查自动化外的数据保鲜）
$weekly = New-ScheduledTaskTrigger -Weekly -At "09:30" -DaysOfWeek Monday
$daily = New-ScheduledTaskTrigger -Daily -At "10:00"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "FQT_Weekly_Refresh" -Action $refreshAction `
    -Trigger $weekly -Settings $settings -Force | Out-Null
Register-ScheduledTask -TaskName "FQT_Daily_Snapshot" -Action $snapshotAction `
    -Trigger $daily -Settings $settings -Force | Out-Null

Write-Host "done: FQT_Weekly_Refresh（周一 09:30）+ FQT_Daily_Snapshot（每日 10:00）已注册"

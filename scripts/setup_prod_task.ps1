# fund-quant-tool 生产部署一次性配置（2026-10-28，实现方案 §7 落地）
# 幂等：重复运行会覆盖同名防火墙规则与任务计划。
# 管理员 PowerShell 运行：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_prod_task.ps1
#
# 产出两件：
#   1. 防火墙规则 "FQT 8000 tailnet only" —— 入站 TCP 8000 仅放行 100.64.0.0/10（tailnet）
#      （镜像 mobile-hq 的 "HQ 8100 tailnet only"；公网/局域网默认入站拒绝覆盖）
#   2. 任务计划 FQT_Web_Server —— Administrator 登录自启 backend/serve_prod.py
#      （镜像 HQ_Static_Server 托管模式：venv python + 脚本，无执行时限，失败自动重启）

$ErrorActionPreference = "Stop"
$repo = "D:\For_Coding\MyProjects\fund-quant-tool"

# ---- 防火墙 ----
# 陈年残留清理：Windows 弹窗被"取消"时会为监听端口的程序生成入站全端口 Block 规则
# （"TCP/UDP Query User"），Block 永远压过下面的端口 Allow 规则——uv 管理的 python
# 中过招就会出现"本机 curl 通、手机/局域网打不开"。禁用 uv python 的此类 Block 残留。
$uvPyRoot = "$env:APPDATA\uv\python\"
Get-NetFirewallRule -Action Block | where {
    $_.Enabled -eq "True" -and $_.Direction -eq "Inbound" -and
    (($_ | Get-NetFirewallApplicationFilter).Program -like "$uvPyRoot*")
} | Disable-NetFirewallRule

Remove-NetFirewallRule -DisplayName "FQT 8000 tailnet only" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "FQT 8000 tailnet only" -Direction Inbound `
    -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress 100.64.0.0/10 | Out-Null

# ---- 任务计划 ----
$action = New-ScheduledTaskAction `
    -Execute "$repo\.venv\Scripts\python.exe" `
    -Argument "$repo\backend\serve_prod.py" `
    -WorkingDirectory "$repo\backend"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType Interactive
# ExecutionTimeLimit 0 = 无时限（任务计划默认 72h 会杀掉常驻服务）
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "FQT_Web_Server" -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "done: 防火墙规则 FQT 8000 tailnet only + 任务计划 FQT_Web_Server 已注册"
Write-Host "手动拉起：MSYS_NO_PATHCONV=1 schtasks /run /tn FQT_Web_Server（Git Bash）"

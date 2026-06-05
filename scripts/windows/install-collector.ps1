<#
.SYNOPSIS
  一次性把这台 Windows 机器装成 Tally 浏览器采集机:
    1) 建 venv + 装依赖 + playwright chrome
    2) 关睡眠/息屏/休眠(交流电下),避免采集机离线
    3) 注册计划任务(登录时启动、交互式会话、崩溃自动重启)

  请在【目标采集账号已登录的桌面】里,用该账号打开 PowerShell(管理员)运行:
    powershell -ExecutionPolicy Bypass -File scripts\windows\install-collector.ps1

  前置:已装 Git、Python 3.12、Google Chrome;已把 finance-agents\browser-agent\.env
  从 .env.example 复制并填好(JWT_SECRET=prod 的值、COMPANY_ID、BROWSER_AGENT_ID=collector-win-1)。
#>
[CmdletBinding()]
param(
  [string]$PythonExe = 'python',
  [string]$TaskName  = 'TallyBrowserAgent'
)
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$AgentDir  = Join-Path $RepoRoot 'finance-agents\browser-agent'
$EnvFile   = Join-Path $AgentDir '.env'
$Venv      = Join-Path $RepoRoot '.venv'
$VenvPy    = Join-Path $Venv 'Scripts\python.exe'

Write-Host '== 0) 前置检查 =='
if (-not (Test-Path $EnvFile)) {
  Write-Error "缺少 $EnvFile —— 先 copy finance-agents\browser-agent\.env.example 为 .env 并填值"
  exit 1
}

Write-Host '== 1) 创建 venv + 安装依赖 =='
if (-not (Test-Path $VenvPy)) { & $PythonExe -m venv $Venv }
& $VenvPy -m pip install --upgrade pip
$reqs = Join-Path $AgentDir 'requirements.txt'
if ((Test-Path $reqs) -and ((Get-Content $reqs | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') }).Count -gt 0)) {
  & $VenvPy -m pip install -r $reqs
}
# 核心依赖(显式装,防 requirements.txt 不全):
#   oss2 = 上传原始下载文件到 OSS(STORAGE_BACKEND=oss 必需)
#   pywin32/mss/Pillow = OS 级远控接管(截屏/窗口/注入)
& $VenvPy -m pip install PyJWT websockets playwright httpx pandas openpyxl oss2 pywin32 mss Pillow
& $VenvPy -m playwright install chrome

Write-Host '== 2) 电源策略:交流电下不睡眠/不息屏/不休眠 =='
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Host '== 3) 注册计划任务(登录启动 / 交互式 / 崩溃重启) =='
$startScript = Join-Path $ScriptDir 'start-browser-agent.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`" -Run"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew
# 交互式会话运行(关键:不是 Session 0),用当前登录账号
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "已注册计划任务: $TaskName"

Write-Host ''
Write-Host '== 完成。后续 =='
Write-Host '  立即自检:  powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Check'
Write-Host "  立即启动一次(或重启电脑后自动起): Start-ScheduledTask -TaskName $TaskName"
Write-Host '  看状态:    powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Status'
Write-Host "  停止:      Stop-ScheduledTask -TaskName $TaskName ; 然后 start-browser-agent.ps1 -Stop"
Write-Host ''
Write-Host '  还需手动:① 开启自动登录(netplwiz,让交互式会话常在);② 关闭锁屏/屏保;'
Write-Host '           ③ 确保能访问 wss://www.tallyai.cn(若走代理,保证开机自启且先于 agent 就绪)。'

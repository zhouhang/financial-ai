<#
.SYNOPSIS
  Start / stop / check the Tally browser-agent on a Windows collection machine.

  采集机必须以"已登录的交互式桌面用户"身份运行(不要做成 Session 0 的服务),
  否则 OS 级远控接管(看 Chrome 窗口 / 注入点击键盘)会黑屏失效。
  本脚本不做后台 daemon —— 常驻交给 Windows 计划任务(见 install-collector.ps1,
  触发器=登录时、以交互式会话运行、崩溃自动重启)。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Check
  powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Status
  powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Stop
  powershell -ExecutionPolicy Bypass -File scripts\windows\start-browser-agent.ps1 -Run
#>
[CmdletBinding()]
param(
  [switch]$Run,
  [switch]$Check,
  [switch]$Status,
  [switch]$Stop
)
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
$AgentDir  = Join-Path $RepoRoot 'finance-agents\browser-agent'
$EnvFile   = if ($env:BROWSER_AGENT_ENV_FILE) { $env:BROWSER_AGENT_ENV_FILE } else { Join-Path $AgentDir '.env' }
$LogDir    = Join-Path $AgentDir 'logs'
$LogFile   = Join-Path $LogDir 'browser-agent.log'

function Get-AgentProcess {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -and ($_.CommandLine -match 'service\.py') }
}

if ($Status) {
  $p = Get-AgentProcess
  if ($p) { Write-Host "browser-agent running: PID $($p.ProcessId)`nlog=$LogFile"; exit 0 }
  Write-Host 'browser-agent not running'; exit 1
}

if ($Stop) {
  $p = Get-AgentProcess
  if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Host 'Stopped browser-agent' }
  else { Write-Host 'browser-agent not running' }
  exit 0
}

# ---- load .env ----
if (-not (Test-Path $EnvFile)) {
  Write-Error "Missing config file: $EnvFile`nCreate it from finance-agents\browser-agent\.env.example."
  exit 1
}
Get-Content -LiteralPath $EnvFile | ForEach-Object {
  $line = $_.Trim()
  if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
    $idx = $line.IndexOf('=')
    $k = $line.Substring(0, $idx).Trim()
    $v = $line.Substring($idx + 1).Trim()
    [Environment]::SetEnvironmentVariable($k, $v, 'Process')
  }
}

foreach ($req in 'DATA_AGENT_WS_URL', 'JWT_SECRET', 'BROWSER_AGENT_COMPANY_ID') {
  if (-not [Environment]::GetEnvironmentVariable($req)) { Write-Error "Missing required env: $req"; exit 1 }
}

function Set-Default([string]$k, [string]$d) {
  if (-not [Environment]::GetEnvironmentVariable($k)) { [Environment]::SetEnvironmentVariable($k, $d, 'Process') }
}
Set-Default 'BROWSER_AGENT_ID'                       "collector-$($env:COMPUTERNAME)"
Set-Default 'BROWSER_AGENT_RUNNER_MODE'              'playwright'
Set-Default 'BROWSER_AGENT_BROWSER_CHANNEL'          'chrome'
Set-Default 'BROWSER_AGENT_HEADLESS'                 '0'
Set-Default 'BROWSER_AGENT_MAX_CONCURRENCY'          '1'
Set-Default 'BROWSER_AGENT_POLL_INTERVAL_SECONDS'    '2'
Set-Default 'BROWSER_AGENT_HEARTBEAT_INTERVAL_SECONDS' '30'
Set-Default 'BROWSER_AGENT_TIMEZONE'                 'Asia/Shanghai'
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$AgentDir;$($env:PYTHONPATH)" } else { $AgentDir }

# ---- locate python (repo venv first) ----
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }

if ($Check) { & $Python (Join-Path $AgentDir 'scripts\check_environment.py'); exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $AgentDir
Write-Host "Starting browser-agent: id=$($env:BROWSER_AGENT_ID) ws=$($env:DATA_AGENT_WS_URL) headless=$($env:BROWSER_AGENT_HEADLESS)"

# Foreground run; the Scheduled Task owns lifecycle/restart. All output appended to log.
& $Python 'service.py' *>> $LogFile

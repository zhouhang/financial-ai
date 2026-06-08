<#
.SYNOPSIS
  collector-win browser-agent process manager: single instance + scheduled task + clean restart.

.DESCRIPTION
  browser-agent drives non-headless Chrome and does screen handoff, so it MUST run inside the
  user's interactive desktop session (a SYSTEM service cannot drive the GUI). We host it with a
  scheduled task (AtLogon trigger + restart-on-failure) so it can be safely Stop/Start-ed over
  SSH from the mac dev box, and so duplicate service.py instances never pile up.

  NOTE: ASCII-only on purpose. Windows PowerShell 5.1 parses .ps1 as the system ANSI codepage
  (GBK on zh-CN), which corrupts UTF-8 string literals. Keep this file ASCII.

  Actions:
    Register  one-time: register scheduled task TallyBrowserAgent (AtLogon + on-demand + restart)
    Start     start (skip if already running); auto-registers the task if missing
    Stop      stop the task and kill every leftover service.py python process (fix duplicates)
    Restart   Stop then Start -- call this after deploy
    Status    print current service.py processes and task state

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File manage-browser-agent.ps1 -Action Restart
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("Register", "Start", "Stop", "Restart", "Status")]
  [string]$Action
)

$ErrorActionPreference = "Stop"
$Root = "C:\tally\browser-agent"
$StartScript = Join-Path $Root "start-browser-agent.ps1"
$TaskName = "TallyBrowserAgent"

function Get-AgentProcesses {
  # every python process whose command line contains service.py (.venv and global both count)
  Get-CimInstance Win32_Process -Filter "name like '%python%'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "service\.py" }
}

function Register-Agent {
  # AtLogon trigger, runs in the current interactive user session (desktop/Chrome), auto-restart.
  $action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
  $trigger = New-ScheduledTaskTrigger -AtLogOn
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
  Write-Output "Registered scheduled task $TaskName (AtLogon + 1-min restart, interactive session)."
}

function Stop-Agent {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  }
  foreach ($p in Get-AgentProcesses) {
    Write-Output ("Killing service.py PID=" + $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 2
  $remaining = Get-AgentProcesses
  if ($remaining) { throw ("service.py still running: " + ($remaining.ProcessId -join ",")) }
  Write-Output "browser-agent stopped, no leftover instance."
}

function Start-Agent {
  $existing = Get-AgentProcesses
  if ($existing) {
    Write-Output ("browser-agent already running PID=" + ($existing.ProcessId -join ",") + ", skip.")
    return
  }
  if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    Write-Output "Scheduled task $TaskName missing, auto-registering..."
    Register-Agent
  }
  Start-ScheduledTask -TaskName $TaskName
  Write-Output "Started browser-agent via scheduled task $TaskName."
  Start-Sleep -Seconds 4
  $now = Get-AgentProcesses
  if (-not $now) { throw "No service.py process after start; check logs\browser-agent.log." }
  Write-Output ("browser-agent running PID=" + ($now.ProcessId -join ","))
}

function Status-Agent {
  $procs = Get-AgentProcesses
  if ($procs) {
    Write-Output "Running service.py processes:"
    $procs | ForEach-Object { Write-Output ("  PID=" + $_.ProcessId + "  " + $_.CommandLine) }
  } else {
    Write-Output "No service.py process running."
  }
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($task) { Write-Output ("Scheduled task $TaskName state: " + $task.State) }
  else { Write-Output "Scheduled task $TaskName not registered." }
}

switch ($Action) {
  "Register" { Register-Agent }
  "Start"    { Start-Agent }
  "Stop"     { Stop-Agent }
  "Restart"  { Stop-Agent; Start-Agent }
  "Status"   { Status-Agent }
}

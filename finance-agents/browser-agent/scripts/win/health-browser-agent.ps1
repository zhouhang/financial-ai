<#
  browser-agent health check (run on the Windows collector).
  ASCII-only source (Windows PowerShell 5.1 parses .ps1 as the system ANSI codepage).
#>
$ErrorActionPreference = "SilentlyContinue"
$Root = "C:\tally\browser-agent"
$TaskName = "TallyBrowserAgent"
$LogFile = Join-Path $Root "logs\browser-agent.log"

$procs = @(Get-CimInstance Win32_Process -Filter "name like '%python%'" |
  Where-Object { $_.CommandLine -and $_.CommandLine -match "service\.py" })
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==== browser-agent health @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===="

if ($procs.Count -ge 1) {
  Write-Host ("STATUS : ALIVE  (" + $procs.Count + " process; venv stub + child interpreter = normal, ONE agent)") -ForegroundColor Green
  foreach ($p in $procs) {
    Write-Host ("  PID=" + $p.ProcessId + "  Session=" + $p.SessionId + "  " + $p.ExecutablePath)
  }
} else {
  Write-Host "STATUS : DOWN   (no service.py process)" -ForegroundColor Red
  Write-Host "  Restart: powershell -ExecutionPolicy Bypass -File `"$Root\scripts\win\manage-browser-agent.ps1`" -Action Restart"
}

if ($task) { Write-Host ("TASK   : " + $task.State) }
else { Write-Host "TASK   : NOT REGISTERED (run manage-browser-agent.ps1 -Action Register)" }

if (Test-Path $LogFile) {
  $age = [int]((Get-Date) - (Get-Item $LogFile).LastWriteTime).TotalSeconds
  Write-Host ("LOG    : last write " + $age + "s ago")
  Write-Host "---- last 8 log lines ----"
  Get-Content $LogFile -Tail 8
} else {
  Write-Host "LOG    : not found at $LogFile"
}

# Task-match self-check: confirm tally actually dispatches collection tasks to THIS agent_id.
# (agent can be alive + WS-connected but receive zero tasks if BROWSER_AGENT_ID != the
#  agent_id tally's bindings are assigned to. This catches that silent failure.)
Write-Host ""
Write-Host "---- task-match self-check (agent_id vs tally bindings) ----"
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Checker = Join-Path $Root "scripts\win\selfcheck-agent-match.py"
if ((Test-Path $Py) -and (Test-Path $Checker)) {
  $env:PYTHONIOENCODING = "utf-8"
  & $Py $Checker
} else {
  Write-Host "TASK-MATCH : SKIP   (python venv or checker not found)"
}
Write-Host ""

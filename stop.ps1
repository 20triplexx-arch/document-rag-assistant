param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$ragEntry = Join-Path $PSScriptRoot 'serve.py'
$ragListeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($ragListeners.Count -eq 0) { Write-Host 'No server is listening on this port.'; return }
foreach ($ragListener in $ragListeners) {
    $ragProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($ragListener.OwningProcess)"
    if ($ragListener.LocalAddress -ne '127.0.0.1' -or -not $ragProcessInfo.CommandLine -or $ragProcessInfo.CommandLine.IndexOf($ragEntry, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw 'The port belongs to an unrecognized process. Nothing was stopped.'
    }
}
$ragCheck = @'
import sqlite3, sys, time
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True) as db:
    print(db.execute("SELECT COUNT(*) FROM jobs WHERE state='active' AND lease_until>?", (time.time(),)).fetchone()[0])
'@
$ragActiveJobs = & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -c $ragCheck (Join-Path $PSScriptRoot 'output/users.sqlite3')
if ($LASTEXITCODE -ne 0) { throw 'Could not verify active requests. Nothing was stopped.' }
if ([int]$ragActiveJobs -gt 0) { throw 'A generation request is active. Wait for it to complete before stopping.' }
foreach ($ragProcessId in ($ragListeners.OwningProcess | Select-Object -Unique)) {
    $ragProcess = Get-Process -Id $ragProcessId
    Stop-Process -Id $ragProcessId
    $ragProcess.WaitForExit(5000) | Out-Null
}
Write-Host 'This project server has stopped. No database or source files were deleted.'

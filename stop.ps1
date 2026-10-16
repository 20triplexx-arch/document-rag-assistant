param([int]$Port = 0)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows-common.ps1')
$ragPython = Get-RagPython $PSScriptRoot
$Port = Resolve-RagPort $Port
$ragListeners = @(Get-RagListeners $Port)
if ($ragListeners.Count -eq 0) { Write-Host 'No server is listening on this port.'; return }
foreach ($ragListener in $ragListeners) {
    $ragProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($ragListener.OwningProcess)"
    if ($ragListener.LocalAddress -ne '127.0.0.1' -or -not (Test-RagProcess $ragProcessInfo $PSScriptRoot)) {
        throw 'The port belongs to an unrecognized process. Nothing was stopped.'
    }
}
$ragCheck = @'
import sqlite3, sys, time
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True) as db:
    print(db.execute('SELECT COUNT(*) FROM jobs WHERE state=? AND lease_until>?', ('active', time.time())).fetchone()[0])
'@
$ragActiveJobs = & $ragPython -c $ragCheck (Join-Path $PSScriptRoot 'output/users.sqlite3')
if ($LASTEXITCODE -ne 0) { throw 'Could not verify active requests. Nothing was stopped.' }
if ([int]$ragActiveJobs -gt 0) { throw 'A generation request is active. Wait for it to complete before stopping.' }
foreach ($ragProcessId in ($ragListeners.OwningProcess | Select-Object -Unique)) {
    $ragProcess = Get-Process -Id $ragProcessId
    Stop-Process -Id $ragProcessId
    if (-not $ragProcess.WaitForExit(5000)) { throw 'Process exit was not confirmed. Check the process before restarting.' }
}
Write-Host 'This project server has stopped. No database or source files were deleted.'

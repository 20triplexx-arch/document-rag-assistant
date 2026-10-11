param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be 1-65535.' }
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) { throw 'Run .\setup.ps1 first.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port is already in use. Stop the existing app before starting another.'
}
$ragLogDir = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Path $ragLogDir -Force | Out-Null
$ragLogName = 'server-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff')
$ragPreviousPort = $env:RAG_PORT
try {
    $env:RAG_PORT = [string]$Port
    $ragProcess = Start-Process -FilePath $ragPython -ArgumentList (Join-Path $PSScriptRoot 'serve.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $ragLogDir "$ragLogName.stdout.log") -RedirectStandardError (Join-Path $ragLogDir "$ragLogName.stderr.log") -PassThru
    if ($ragProcess.WaitForExit(2000)) { throw 'Server exited during startup. Check output/server-*.stderr.log.' }
    Write-Host "Background server started. Open http://127.0.0.1:$Port/"
    Write-Host "To stop this project server, run .\stop.ps1 -Port $Port"
} finally { $env:RAG_PORT = $ragPreviousPort }

param([int]$Port = 0)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows-common.ps1')
$ragPython = Get-RagPython $PSScriptRoot
$Port = Resolve-RagPort $Port
Assert-RagPortFree $Port
Invoke-RagDoctor $ragPython $PSScriptRoot
$ragLogDir = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Path $ragLogDir -Force | Out-Null
$ragLogName = 'server-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff')
$ragPreviousPort = $env:RAG_PORT
try {
    $env:RAG_PORT = [string]$Port
    $ragEntryArgument = '"' + (Join-Path $PSScriptRoot 'serve.py') + '"'
    $ragProcess = Start-Process -FilePath $ragPython -ArgumentList $ragEntryArgument -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $ragLogDir "$ragLogName.stdout.log") -RedirectStandardError (Join-Path $ragLogDir "$ragLogName.stderr.log") -PassThru
    Wait-RagReady $ragProcess $PSScriptRoot $Port
    Write-Host "Background server started. Open http://127.0.0.1:$Port/"
    Write-Host "To stop this project server, run .\stop.ps1 -Port $Port"
} finally { $env:RAG_PORT = $ragPreviousPort }

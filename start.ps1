param([int]$Port = 0)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows-common.ps1')
$ragPython = Get-RagPython $PSScriptRoot
$Port = Resolve-RagPort $Port
Assert-RagPortFree $Port
Invoke-RagDoctor $ragPython $PSScriptRoot
$ragPreviousPort = $env:RAG_PORT
try {
    $env:RAG_PORT = [string]$Port
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $ragPython (Join-Path $PSScriptRoot 'serve.py')
        if ($LASTEXITCODE -ne 0) { throw 'The local server exited with an error.' }
    } finally { Pop-Location }
} finally { $env:RAG_PORT = $ragPreviousPort }

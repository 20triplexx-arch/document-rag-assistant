param([int]$Port = 0)
$ErrorActionPreference = 'Stop'
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) {
    throw 'Project environment is missing. Run .\setup.ps1 first.'
}
if ($Port -lt 0 -or $Port -gt 65535) { throw 'Port must be 1-65535, or 0 to use RAG_PORT/default.' }
$ragPreviousPort = $env:RAG_PORT
try {
    if ($Port -gt 0) { $env:RAG_PORT = [string]$Port }
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $ragPython (Join-Path $PSScriptRoot 'serve.py')
        if ($LASTEXITCODE -ne 0) { throw 'The local server exited with an error.' }
    } finally { Pop-Location }
} finally { $env:RAG_PORT = $ragPreviousPort }

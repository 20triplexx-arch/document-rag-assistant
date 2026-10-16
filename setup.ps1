param([string]$PythonPath = "", [switch]$SkipCorpus)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows-common.ps1')
Assert-RagWindows
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv')) {
    if (-not (Test-Path -LiteralPath $ragPython -PathType Leaf)) { throw 'Existing .venv is incomplete. It was not replaced; keep it in a separate location before reinstalling.' }
    Assert-RagPython $ragPython -ExpectedEnvironment (Join-Path $PSScriptRoot '.venv')
} else {
    if ($PythonPath) {
        Assert-RagPython $PythonPath
        & $PythonPath -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        Assert-RagPython 'py' @('-3.12')
        & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Assert-RagPython 'python'
        & python -m venv (Join-Path $PSScriptRoot '.venv')
    } else {
        throw 'Python 3.12 is required. Run setup.ps1 -PythonPath <python.exe path>.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    Assert-RagPython $ragPython -ExpectedEnvironment (Join-Path $PSScriptRoot '.venv')
}

& $ragPython -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --no-cache-dir --disable-pip-version-check --no-input --retries 0 --timeout 30 -r (Join-Path $PSScriptRoot 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; do not start until resolved.' }
& $ragPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed dependencies are inconsistent.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($SkipCorpus) {
        & $ragPython starter.py doctor --skip-corpus --json
        if ($LASTEXITCODE -ne 0) { throw 'Environment checks failed.' }
        Write-Host 'Environment prepared; corpus NOT checked. Run .\setup.ps1 to complete installation.'
    } else {
        & $ragPython -u -m study_rag.installation
        if ($LASTEXITCODE -ne 0) { throw 'Textbook preparation failed. Checked downloads are retained; rerun setup.ps1 to resume.' }
        Invoke-RagDoctor $ragPython $PSScriptRoot
        Write-Host 'Setup complete: environment and default corpus verified. Run .\start.ps1. No model was called.'
    }
} finally { Pop-Location }

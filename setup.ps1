param([string]$PythonPath = "")
$ErrorActionPreference = 'Stop'
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $ragPython)) {
    if ($PythonPath) {
        & $PythonPath -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $PSScriptRoot '.venv')
    } else {
        throw 'Python 3.12 is required. Run setup.ps1 -PythonPath <python.exe path>.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}

& $ragPython -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: --disable-pip-version-check --no-input -r (Join-Path $PSScriptRoot 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; do not start until resolved.' }
& $ragPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Installed dependencies are inconsistent.' }
Write-Host 'Setup complete. Run .\start.ps1 to start the local app.'

$ErrorActionPreference = 'Stop'
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) { throw 'Run .\setup.ps1 first.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ragPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
    & $ragPython -m unittest discover -s . -p 'test*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js is required to run the offline frontend tests (not to serve the app).'
    }
    & node --check static/app.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend syntax check failed.' }
    & node test_ui.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & $ragPython starter.py verify
    if ($LASTEXITCODE -ne 0) { throw 'Textbook or index verification failed.' }
    & $ragPython starter.py evaluate --check-only
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation dataset validation failed.' }
} finally { Pop-Location }

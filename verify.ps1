$ErrorActionPreference = 'Stop'
$ragPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ragPython)) { throw 'Run .\setup.ps1 first.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ragPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
    & $ragPython scripts/compile_qa_repair_clauses.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Derived clause warmup index differs from fixed code rules.' }
    & $ragPython -m unittest discover -s . -p 'test*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'Node.js is required to run the offline frontend tests (not to serve the app).'
    }
    & node --check static/app.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend syntax check failed.' }
    & node --check static/answer.js
    if ($LASTEXITCODE -ne 0) { throw 'Answer renderer syntax check failed.' }
    & node --check static/stream.js
    if ($LASTEXITCODE -ne 0) { throw 'Stream reader syntax check failed.' }
    & node --check static/diagnostics.js
    if ($LASTEXITCODE -ne 0) { throw 'Diagnostics frontend syntax check failed.' }
    & node test_ui.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & $ragPython starter.py verify
    if ($LASTEXITCODE -ne 0) { throw 'Textbook or index verification failed.' }
    & $ragPython starter.py evaluate --check-only
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation dataset validation failed.' }
    & $ragPython starter.py qa-evaluate --check-only
    if ($LASTEXITCODE -ne 0) { throw 'QA dataset validation failed.' }
    & $ragPython -B scripts/qa_depth_check.py
    if ($LASTEXITCODE -ne 0) { throw 'Source-first QA holdouts failed offline validation.' }
    if (Test-Path -LiteralPath 'data/qa-overhaul-20261015-v2/corpus.json') {
        & $ragPython -B scripts/qa_overhaul_check.py
        if ($LASTEXITCODE -ne 0) { throw 'Expanded corpus or frozen source positions failed offline validation.' }
        & $ragPython -B scripts/qa_repair_check.py
        if ($LASTEXITCODE -ne 0) { throw 'Repair holdout source positions failed offline validation.' }
    }
} finally { Pop-Location }

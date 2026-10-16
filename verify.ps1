param([Alias('Profile')][ValidateSet('App','Code','Research')][string]$VerificationProfile = 'App')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows-common.ps1')
$ragPython = Get-RagPython $PSScriptRoot
Push-Location -LiteralPath $PSScriptRoot
try {
    & $ragPython starter.py doctor --skip-corpus --json
    if ($LASTEXITCODE -ne 0) { throw 'Environment verification failed.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js 24 is required for developer verification; installation and serving do not require Node.js.' }
    $ragNodeVersion = & node -p "process.versions.node.split('.')[0]"
    if ($LASTEXITCODE -ne 0 -or $ragNodeVersion -ne '24') { throw 'Use Node.js 24 for developer verification.' }
    if ($VerificationProfile -eq 'Research') {
        foreach ($ragSnapshot in @('data/qa-20261014-v1','data/qa-overhaul-20261015-v2')) {
            foreach ($ragFile in @('corpus.json','index.sqlite3')) {
                if (-not (Test-Path -LiteralPath (Join-Path $ragSnapshot $ragFile))) { throw "Research snapshot is missing: $ragSnapshot/$ragFile. Research was NOT validated." }
            }
        }
    }
    & $ragPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
    & $ragPython scripts/compile_qa_repair_clauses.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Derived clause warmup index differs from fixed code rules.' }
    & $ragPython -m unittest discover -s . -p 'test*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed. Optional skips, if any, are listed explicitly above.' }
    foreach ($ragScript in @('static/app.js','static/answer.js','static/stream.js','static/diagnostics.js')) {
        & node --check $ragScript
        if ($LASTEXITCODE -ne 0) { throw "Frontend syntax check failed: $ragScript" }
    }
    & node test_ui.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/test_windows.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Windows entry-point tests failed.' }
    if ($VerificationProfile -ne 'Code') {
        & $ragPython starter.py doctor --json
        if ($LASTEXITCODE -ne 0) { throw 'Default corpus verification failed.' }
        & $ragPython starter.py evaluate --check-only
        if ($LASTEXITCODE -ne 0) { throw 'Default evaluation dataset validation failed.' }
    }
    if ($VerificationProfile -eq 'Research') {
        & $ragPython starter.py qa-evaluate --check-only
        if ($LASTEXITCODE -ne 0) { throw 'QA dataset validation failed.' }
        foreach ($ragCheck in @('scripts/qa_depth_check.py','scripts/qa_overhaul_check.py','scripts/qa_repair_check.py')) {
            & $ragPython -B $ragCheck
            if ($LASTEXITCODE -ne 0) { throw "Research source validation failed: $ragCheck" }
        }
    } else { Write-Host 'Research snapshots were NOT checked. Use -Profile Research explicitly.' }
    Write-Host "Verification passed: $VerificationProfile. No live model calls."
} finally { Pop-Location }

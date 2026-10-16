# Offline assertions, including mocked readiness failures. No external processes stopped.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-common.ps1')
$ragCount = 0
function Assert-RagTest($Condition, $Message) {
    if (-not $Condition) { throw "Test failed: $Message" }
    $script:ragCount++
}
function Assert-RagThrows([scriptblock]$Action, [string]$Pattern) {
    $ragCaught = $null
    try { & $Action } catch { $ragCaught = $_.Exception.Message }
    Assert-RagTest ($ragCaught -and $ragCaught -match $Pattern) $Pattern
}
$ragOriginalPort = $env:RAG_PORT
try {
    $env:RAG_PORT = $null
    Assert-RagTest ((Resolve-RagPort) -eq 8765) 'default port'
    $env:RAG_PORT = '18876'
    Assert-RagTest ((Resolve-RagPort) -eq 18876) 'environment port'
    Assert-RagTest ((Resolve-RagPort 18877) -eq 18877) 'explicit port'
    $env:RAG_PORT = 'invalid'
    Assert-RagThrows { Resolve-RagPort } 'RAG_PORT'
    Assert-RagThrows { Resolve-RagPort -1 } 'Port must'
    function Mock-RagPython { $global:LASTEXITCODE = 0; Write-Output $script:ragFakeRuntime }
    $script:ragFakeRuntime = '[[3,11],8,"AMD64"]'
    Assert-RagThrows { Assert-RagPython 'Mock-RagPython' } 'Python 3.12 x64'
    $script:ragFakeRuntime = '[[3,12],4,"AMD64"]'
    Assert-RagThrows { Assert-RagPython 'Mock-RagPython' } 'Python 3.12 x64'
    $script:ragFakeRuntime = '[[3,12],8,"AMD64","C:/Python312","C:/Python312"]'
    Assert-RagThrows { Assert-RagPython 'Mock-RagPython' -ExpectedEnvironment 'C:\sample\.venv' } 'not an isolated environment'
    $ragRoot = 'C:\sample space\project'
    Assert-RagTest (Test-RagProcess ([pscustomobject]@{CommandLine='python.exe "C:\sample space\project\serve.py"'}) $ragRoot) 'quoted entry'
    Assert-RagTest (-not (Test-RagProcess ([pscustomobject]@{CommandLine='python.exe "C:\sample space\project\serve.py.other"'}) $ragRoot)) 'entry suffix rejected'
    Assert-RagTest (-not (Test-RagProcess ([pscustomobject]@{CommandLine='python.exe C:\other\serve.py'}) $ragRoot)) 'other checkout rejected'
    Assert-RagThrows { Wait-RagReady ([pscustomobject]@{HasExited=$true;Id=123}) $ragRoot 18876 1 } 'exited before readiness'
    function Get-RagListeners { return @() }
    Assert-RagThrows { Wait-RagReady ([pscustomobject]@{HasExited=$false;Id=123}) $ragRoot 18876 1 } 'did not become ready'
    function Get-RagListeners { return @([pscustomobject]@{OwningProcess=777;LocalAddress='127.0.0.1'}) }
    function Get-CimInstance { return [pscustomobject]@{CommandLine='python.exe C:\other\serve.py';ProcessId=777;ParentProcessId=0} }
    Assert-RagThrows { Wait-RagReady ([pscustomobject]@{HasExited=$false;Id=123}) $ragRoot 18876 1 } 'unrecognized process'
    foreach ($ragFile in @('setup.ps1','start.ps1','background.ps1','stop.ps1','verify.ps1','scripts/windows-common.ps1')) {
        $ragParseTokens = $null; $ragParseErrors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Split-Path $PSScriptRoot) $ragFile),[ref]$ragParseTokens,[ref]$ragParseErrors)
        Assert-RagTest ($ragParseErrors.Count -eq 0) "syntax $ragFile"
    }
    Write-Host "Windows checks passed: $ragCount (PowerShell $($PSVersionTable.PSVersion))."
} finally { $env:RAG_PORT = $ragOriginalPort }

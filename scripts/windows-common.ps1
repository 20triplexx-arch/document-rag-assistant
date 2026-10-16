# Shared Windows entry-point checks. Compatible with Windows PowerShell 5.1.
function Assert-RagWindows {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'Windows x64 is required. No environment or data was replaced.'
    }
}

function Assert-RagPython {
    param([string]$Executable, [string[]]$PrefixArguments = @(), [string]$ExpectedEnvironment = '')
    $ragProbeCode = "import sys,struct,platform,json; print(json.dumps([list(sys.version_info[:2]),struct.calcsize('P'),platform.machine(),sys.prefix,sys.base_prefix]))"
    $ragProbe = & $Executable @PrefixArguments -c $ragProbeCode
    if ($LASTEXITCODE -ne 0) { throw 'Python could not run. Use .\setup.ps1 -PythonPath C:\path\to\Python312\python.exe.' }
    try { $ragRuntime = $ragProbe | ConvertFrom-Json } catch { throw 'The selected executable is not a supported Python interpreter.' }
    if ($ragRuntime[0][0] -ne 3 -or $ragRuntime[0][1] -ne 12 -or $ragRuntime[1] -ne 8 -or $ragRuntime[2] -notin @('AMD64','x86_64')) {
        throw 'Python 3.12 x64 is required. Existing .venv was not replaced. Use -PythonPath for a new install; keep incompatible environments in a separate checkout.'
    }
    if ($ExpectedEnvironment) {
        if ($ragRuntime.Count -lt 5 -or $ragRuntime[3] -eq $ragRuntime[4] -or
            -not [string]::Equals([IO.Path]::GetFullPath($ragRuntime[3]),[IO.Path]::GetFullPath($ExpectedEnvironment),[StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath (Join-Path $ExpectedEnvironment 'pyvenv.cfg') -PathType Leaf)) {
            throw 'Existing .venv is not an isolated environment for this checkout. Nothing was replaced; use a separate clean checkout.'
        }
    }
}

function Get-RagPython {
    param([string]$Root)
    Assert-RagWindows
    $ragExecutable = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $ragExecutable -PathType Leaf)) { throw 'Project environment is missing. Run .\setup.ps1 first.' }
    Assert-RagPython $ragExecutable -ExpectedEnvironment (Join-Path $Root '.venv')
    return $ragExecutable
}

function Resolve-RagPort {
    param([int]$Port = 0)
    if ($Port -eq 0) {
        if ([string]::IsNullOrWhiteSpace($env:RAG_PORT)) { $Port = 8765 }
        elseif (-not [int]::TryParse($env:RAG_PORT, [ref]$Port)) { throw 'RAG_PORT must be an integer from 1 to 65535.' }
    }
    if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be 1-65535; 0 selects RAG_PORT or 8765.' }
    return $Port
}

function Assert-RagPortFree {
    param([int]$Port)
    if (@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq $Port }).Count -gt 0) {
        throw "Port $Port is already in use. No process was stopped. Choose .\start.ps1 -Port <free-port>."
    }
}

function Get-RagListeners {
    param([int]$Port)
    # Get-NetTCPConnection's CIM provider may deny access even for a local user.
    # netstat's PID table is available without administrator rights on Windows.
    $ragSocketRows = & (Join-Path $env:WINDIR 'System32\netstat.exe') -ano -p TCP
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect listening ports. No process was stopped.' }
    foreach ($ragRow in $ragSocketRows) {
        if ($ragRow -match '^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$' -and [int]$Matches[2] -eq $Port) {
            [pscustomobject]@{LocalAddress=$Matches[1].Trim('[',']');LocalPort=[int]$Matches[2];OwningProcess=[int]$Matches[3]}
        }
    }
}

function Invoke-RagDoctor {
    param([string]$Python, [string]$Root)
    & $Python (Join-Path $Root 'starter.py') doctor --json
    if ($LASTEXITCODE -ne 0) { throw 'Local preflight failed. Follow the diagnostic above; existing data was not overwritten.' }
}

function Test-RagProcess {
    param($ProcessInfo, [string]$Root)
    $ragEntryPattern = [regex]::Escape((Join-Path $Root 'serve.py'))
    return ($ProcessInfo -and $ProcessInfo.CommandLine -and
        $ProcessInfo.CommandLine -match ('(?i)(?:^|\s)(?:"' + $ragEntryPattern + '"|' + $ragEntryPattern + ')(?:\s|$)'))
}

function Wait-RagReady {
    param($Process, [string]$Root, [int]$Port, [int]$TimeoutSeconds = 90)
    $ragDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $ragDeadline) {
        if ($Process.HasExited) { throw 'Server exited before readiness. Check its output/server-*.stderr.log.' }
        $ragListeners = @(Get-RagListeners $Port)
        foreach ($ragListener in $ragListeners) {
            $ragInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($ragListener.OwningProcess)"
            if ($ragListener.LocalAddress -ne '127.0.0.1' -or -not (Test-RagProcess $ragInfo $Root)) {
                throw 'The port belongs to an unrecognized process. It was not stopped.'
            }
            # Windows venv redirectors may own a child interpreter process.
            $ragAncestor = $ragInfo
            $ragOwnProcess = $false
            for ($ragDepth = 0; $ragDepth -lt 8 -and $ragAncestor; $ragDepth++) {
                if ($ragAncestor.ProcessId -eq $Process.Id) { $ragOwnProcess = $true; break }
                $ragAncestor = Get-CimInstance Win32_Process -Filter "ProcessId=$($ragAncestor.ParentProcessId)"
            }
            if (-not $ragOwnProcess) { throw 'Listener is not the process started by this command. Nothing was stopped.' }
            try {
                $ragReply = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/library" -TimeoutSec 2 -UseBasicParsing
                if ($ragReply.source_files -eq 216 -and $ragReply.answer_schema_version -eq 1 -and $ragReply.corpus_version -eq '14830ef070b791490d7b73b177d94101931ed372d3f0eb58f38907f15947bcb2') { return }
            } catch { }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Server did not become ready within $TimeoutSeconds seconds. It was not reported as ready; use .\stop.ps1 -Port $Port after checking its logs."
}

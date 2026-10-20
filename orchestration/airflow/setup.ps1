$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot 'runtime'
if (Test-Path -LiteralPath $runtimePath) {
    throw 'Runtime already exists; credentials will not be overwritten.'
}
New-Item -ItemType Directory -Path $runtimePath | Out-Null
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $runtimePath /inheritance:r /grant:r "${identity}:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict runtime directory ACL.' }
$pythonPath = Join-Path $PSScriptRoot '..\..\.venv\Scripts\python.exe'
& $pythonPath (Join-Path $PSScriptRoot 'init_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Runtime initialization failed.' }

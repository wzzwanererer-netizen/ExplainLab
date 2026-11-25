param([switch]$Managed, [switch]$IncludeRegression)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$env:EXPLAINLAB_T01_OTHER_VOLUME = 'C:\Users\wzz\AppData\Local\Temp'
$env:PYTHONIOENCODING = 'utf-8'
$python = Join-Path $root '.venv\Scripts\python.exe'
$kind = if ($Managed) { 'managed' } else { 'normal' }
$id = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$out = Join-Path $PSScriptRoot "windows-$kind-$id"
$null = New-Item -ItemType Directory -Path $out
Set-Location -LiteralPath $root

function Invoke-RoundEvidence($label, $executable, [string[]]$cli) {
    $log = Join-Path $out "$label.log"
    "START UTC $([DateTime]::UtcNow.ToString('o'))" | Set-Content -LiteralPath $log -Encoding utf8
    "Command: $executable $($cli -join ' ')" | Add-Content -LiteralPath $log -Encoding utf8
    $ErrorActionPreference = 'Continue'
    & $executable @cli 2>&1 | ForEach-Object { "$_" } | Add-Content -LiteralPath $log -Encoding utf8
    $rc = $LASTEXITCODE
    "END UTC $([DateTime]::UtcNow.ToString('o')) exit=$rc" | Add-Content -LiteralPath $log -Encoding utf8
    Get-Content -LiteralPath $log -Tail 15 | Write-Host
    return $rc
}

$launcher = @('-u', '-m', 'pytest')
if ($Managed) {
    $launcher = @('-B', '-u', 'docs/acceptance/V2-A1-04-Batch-B-B1-remediation-round3/evidence/pytest-windows-event-loop.py.txt')
}
$pytestArgs = @('-o', 'addopts=--import-mode=importlib', '-o', 'faulthandler_timeout=40', '-o', 'junit_logging=all', '-ra', '-p', 'no:cacheprovider')
$rc = Invoke-RoundEvidence 't01-windows' $python ($launcher + $pytestArgs + @(
    '-s', "--basetemp=$root\.tmp\b1-t01-$id", "--junitxml=$out\t01-windows.xml",
    'backend/tests/test_attachment_windows.py', '-k', 'test_t01_'
))
if ($Managed -or $IncludeRegression) {
    $regression = Invoke-RoundEvidence 'b1-windows-regression' $python ($launcher + $pytestArgs + @(
        "--junitxml=$out\b1-windows-regression.xml",
        'backend/tests/test_attachment_storage.py', 'backend/tests/test_attachment_windows.py',
        'backend/tests/test_attachment_gc.py', 'backend/tests/test_storage_lock_sqlite.py',
        'backend/tests/test_storage_lock_pg_faults.py', '-k', 'not test_t01_'
    ))
    $ruff = Invoke-RoundEvidence 'ruff-backend-core' (Join-Path $root '.venv\Scripts\ruff.exe') @(
        'check', 'backend', 'knowledge-core'
    )
    if ($regression -ne 0 -or $ruff -ne 0) { $rc = 1 }
}
Write-Host "Evidence: $out"
exit $rc

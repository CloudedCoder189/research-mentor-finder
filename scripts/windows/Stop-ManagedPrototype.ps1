$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$saved = Get-Content -LiteralPath (Join-Path $projectRoot 'test-runtime/prototype-logs/services.json') | ConvertFrom-Json
$validated = @()
foreach ($entry in @(@{port=18501; id=$saved.api_pid; pattern='run_managed_api.py'}, @{port=13310; id=$saved.frontend_pid; pattern='run_managed_frontend.mjs'; child='next.*start.*13310'})) {
    $listener = @(Get-NetTCPConnection -LocalPort $entry.port -State Listen -ErrorAction SilentlyContinue)
    if ($listener.Count -ne 1) { throw 'Expected one managed prototype listener per port.' }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    $launcher = Get-CimInstance Win32_Process -Filter "ProcessId=$($entry.id)"
    if (!$owner -or !$launcher -or $launcher.CommandLine -notmatch $entry.pattern -or
        ($owner.ProcessId -ne $launcher.ProcessId -and $owner.ParentProcessId -ne $launcher.ProcessId) -or
        ($owner.CommandLine -notmatch $entry.pattern -and (!$entry.child -or $owner.CommandLine -notmatch $entry.child))) {
        throw 'Process identity mismatch; nothing stopped.'
    }
    $validated += $owner.ProcessId, $launcher.ProcessId
}
foreach ($processId in ($validated | Select-Object -Unique)) { Stop-Process -Id $processId -ErrorAction SilentlyContinue }
Write-Output 'Validated managed prototype stopped; all data and builds retained.'

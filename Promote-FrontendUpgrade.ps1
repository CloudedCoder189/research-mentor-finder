$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$saved = Get-Content -LiteralPath (Join-Path $projectRoot 'test-runtime/prototype-logs/services.json') | ConvertFrom-Json
$listener = Get-NetTCPConnection -LocalPort 13310 -State Listen
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
if (!$process -or $process.ProcessId -ne $saved.frontend_pid -or $process.CommandLine -notmatch 'next.*start.*13310') { throw 'Frontend identity mismatch.' }
$active = [IO.Path]::GetFullPath((Join-Path $projectRoot 'frontend'))
$stage = [IO.Path]::GetFullPath((Join-Path $projectRoot 'test-runtime/frontend-upgrade-20261005'))
$backup = [IO.Path]::GetFullPath((Join-Path $projectRoot 'test-runtime/frontend-before-next16-20261005'))
$rootPrefix = $projectRoot + [IO.Path]::DirectorySeparatorChar
foreach ($target in @($active,$stage,$backup)) {
    if (!$target.StartsWith($rootPrefix)) { throw 'Frontend path escapes the writable working project.' }
}
if (Test-Path -LiteralPath $backup) { throw 'Existing frontend checkpoint must not be overwritten.' }
$dependencies = Get-Item -LiteralPath (Join-Path $stage 'node_modules')
if ($dependencies.LinkType) { throw 'New dependencies must be independently installed, not linked.' }
if (!(Test-Path -LiteralPath (Join-Path $active '.next/BUILD_ID')) -or !(Test-Path -LiteralPath (Join-Path $stage '.next/BUILD_ID'))) { throw 'Completed frontend builds required.' }
$results = Get-Content -LiteralPath (Join-Path $projectRoot 'evidence/frontend-upgrade-2026-10-05/browser/browser-results.json') | ConvertFrom-Json
if ($results.automatedAssertions.Count -ne 23 -or @($results.automatedAssertions | Where-Object {!$_.passed}).Count) { throw 'Browser acceptance did not pass.' }
$audit = Get-Content -LiteralPath (Join-Path $projectRoot 'evidence/frontend-upgrade-2026-10-05/audit-runtime.json') | ConvertFrom-Json
if ($audit.metadata.vulnerabilities.total -ne 0) { throw 'Runtime dependency advisories remain.' }
Stop-Process -Id $process.ProcessId
if (Get-NetTCPConnection -LocalPort 13310 -State Listen -ErrorAction SilentlyContinue) { throw 'Frontend listener did not stop.' }
# Same-volume directory moves retain the old junction as a junction; they do not
# enumerate or modify the original project's dependency target.
Move-Item -LiteralPath $active -Destination $backup
Move-Item -LiteralPath $stage -Destination $active
Write-Output 'Tested frontend promoted; complete old frontend retained; backend left running.'

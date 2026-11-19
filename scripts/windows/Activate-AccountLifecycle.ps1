$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$frontRoot = Join-Path $projectRoot 'frontend'
$buildPath = Join-Path $frontRoot '.next'
$backupPath = Join-Path $projectRoot 'test-runtime/account-lifecycle-checkpoint-20261005/frontend-build'
$failedPath = Join-Path $projectRoot 'test-runtime/account-lifecycle-failed-build-20261005'
foreach ($path in @($buildPath,$backupPath,$failedPath)) {
    $resolved = [IO.Path]::GetFullPath($path)
    if (!$resolved.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build path leaves the working project.' }
}
if (Test-Path -LiteralPath $backupPath) { throw 'Existing build checkpoint must not be overwritten.' }
if (Test-Path -LiteralPath $failedPath) { throw 'Failed-build checkpoint already exists.' }
[xml]$suite = Get-Content -LiteralPath (Join-Path $projectRoot 'evidence/account-lifecycle-2026-10-05/backend-full.xml')
if ($suite.testsuites.testsuite.failures -ne '0' -or $suite.testsuites.testsuite.errors -ne '0' -or [int]$suite.testsuites.testsuite.tests -lt 639) { throw 'Passing complete backend suite is required.' }
$saved = Get-Content -LiteralPath (Join-Path $projectRoot 'test-runtime/prototype-logs/services.json') | ConvertFrom-Json
$listener = @(Get-NetTCPConnection -LocalPort 13310 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count -ne 1) { throw 'Expected one prototype frontend listener.' }
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
if (!$process -or $process.ProcessId -ne $saved.frontend_pid -or $process.CommandLine -notmatch 'next.*start.*13310') { throw 'Frontend process does not match the saved prototype.' }
& (Join-Path $PSScriptRoot 'Restart-HardenedApi.ps1')
Stop-Process -Id $process.ProcessId
Move-Item -LiteralPath $buildPath -Destination $backupPath
$env:NEXT_PUBLIC_API_BASE_URL = 'http://localhost:18501'
$env:NEXT_TELEMETRY_DISABLED = '1'
Push-Location $frontRoot
try {
    & 'C:\Program Files\nodejs\node.exe' 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' run build 2>&1 | Tee-Object -FilePath (Join-Path $projectRoot 'evidence/account-lifecycle-2026-10-05/activated-build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} catch {
    if (Test-Path -LiteralPath $buildPath) { Move-Item -LiteralPath $buildPath -Destination $failedPath }
    Move-Item -LiteralPath $backupPath -Destination $buildPath
    & (Join-Path $PSScriptRoot 'Start-UpgradedFrontend.ps1')
    throw
} finally { Pop-Location }
& (Join-Path $PSScriptRoot 'Start-UpgradedFrontend.ps1')
Write-Output 'Account lifecycle activated locally; old frontend build preserved. No account deleted.'

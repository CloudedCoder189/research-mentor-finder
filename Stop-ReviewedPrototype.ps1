$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$saved = Get-Content -LiteralPath (Join-Path $projectRoot 'test-runtime/prototype-logs/services.json') | ConvertFrom-Json
$apiListener = Get-NetTCPConnection -LocalPort 18501 -State Listen
$frontListener = Get-NetTCPConnection -LocalPort 13310 -State Listen
$apiProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($apiListener.OwningProcess)"
$apiLauncher = Get-CimInstance Win32_Process -Filter "ProcessId=$($saved.api_pid)"
$frontProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($frontListener.OwningProcess)"
if (!$apiProcess -or !$apiLauncher -or !$frontProcess) { throw 'Expected prototype process is missing.' }
if ($apiProcess.CommandLine -notmatch 'uvicorn.*api.main:app.*18501' -or $apiLauncher.CommandLine -notmatch 'uvicorn.*api.main:app.*18501') { throw 'API command identity mismatch.' }
if ($apiProcess.ProcessId -ne $saved.api_pid -and $apiProcess.ParentProcessId -ne $saved.api_pid) { throw 'API process lineage mismatch.' }
if ($frontProcess.ProcessId -ne $saved.frontend_pid -or $frontProcess.CommandLine -notmatch 'next.*start.*13310') { throw 'Frontend command identity mismatch.' }
$source = [IO.Path]::GetFullPath((Join-Path $projectRoot 'frontend/.next'))
$destination = [IO.Path]::GetFullPath((Join-Path $projectRoot 'test-runtime/frontend-before-release-readiness-20261005'))
$rootPrefix = [IO.Path]::GetFullPath($projectRoot) + [IO.Path]::DirectorySeparatorChar
if (!$source.StartsWith($rootPrefix) -or !$destination.StartsWith($rootPrefix)) { throw 'Build checkpoint escapes the working project.' }
if (Test-Path -LiteralPath $destination) { throw 'Build checkpoint already exists; refusing to replace it.' }
if (!(Test-Path -LiteralPath (Join-Path $source 'BUILD_ID'))) { throw 'Current frontend has no completed build checkpoint.' }
Stop-Process -Id $frontProcess.ProcessId
Stop-Process -Id $apiProcess.ProcessId
if ($apiLauncher.ProcessId -ne $apiProcess.ProcessId) { Stop-Process -Id $apiLauncher.ProcessId -ErrorAction SilentlyContinue }
if (Get-NetTCPConnection -LocalPort 13310,18501 -State Listen -ErrorAction SilentlyContinue) { throw 'Prototype listeners did not stop.' }
Move-Item -LiteralPath $source -Destination $destination
Write-Output 'Validated prototype stopped; completed frontend build retained.'

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$env:RETENTION_ROOT = Join-Path $projectRoot 'test-runtime/managed-retention'
$env:RETENTION_KEY_FILE = Join-Path $projectRoot 'test-runtime/retention-key.txt'
if (!(Test-Path -LiteralPath (Join-Path $env:RETENTION_ROOT 'store.json'))) { throw 'Initialize managed retention before starting services.' }
$frontRoot = Join-Path $projectRoot 'frontend'
if (Get-NetTCPConnection -LocalPort 13310 -State Listen -ErrorAction SilentlyContinue) { throw 'Frontend port is occupied.' }
if (!(Test-Path -LiteralPath (Join-Path $frontRoot '.next/BUILD_ID'))) { throw 'Completed production build is required.' }
$logRoot = Join-Path $projectRoot 'test-runtime/prototype-logs'
$saved = Get-Content -LiteralPath (Join-Path $logRoot 'services.json') | ConvertFrom-Json
$env:NEXT_TELEMETRY_DISABLED = '1'
$front = Start-Process -FilePath 'C:\Program Files\nodejs\node.exe' -ArgumentList 'scripts/run_managed_frontend.mjs' -WorkingDirectory $frontRoot -WindowStyle Hidden -PassThru
$saved.frontend_pid = $front.Id
$saved | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot 'services.json')
Write-Output 'Upgraded frontend started at http://localhost:13310; existing backend retained.'

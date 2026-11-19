param([Parameter(Mandatory=$true)][string]$BackupName, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$env:PROFESSOR_DB_PATH = Join-Path $projectRoot 'test-runtime/real-acceptance-20261004.db'
$env:RETENTION_ROOT = Join-Path $projectRoot 'test-runtime/managed-retention'
$env:RETENTION_KEY_FILE = Join-Path $projectRoot 'test-runtime/retention-key.txt'
Push-Location $projectRoot
try {
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') scripts/managed_retention.py restore --backup $BackupName --destination $Destination
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed; services were not switched.' }
} finally { Pop-Location }

param([Parameter(Mandatory=$true)][string]$BackupName, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$env:PROFESSOR_DB_PATH = Join-Path $PSScriptRoot 'test-runtime/real-acceptance-20261004.db'
$env:RETENTION_ROOT = Join-Path $PSScriptRoot 'test-runtime/managed-retention'
$env:RETENTION_KEY_FILE = Join-Path $PSScriptRoot 'test-runtime/retention-key.txt'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') scripts/managed_retention.py restore --backup $BackupName --destination $Destination
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed; services were not switched.' }
} finally { Pop-Location }

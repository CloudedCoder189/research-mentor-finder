$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$env:RETENTION_ROOT = Join-Path $projectRoot 'test-runtime/managed-retention'
$env:RETENTION_KEY_FILE = Join-Path $projectRoot 'test-runtime/retention-key.txt'
if (!(Test-Path -LiteralPath (Join-Path $env:RETENTION_ROOT 'store.json'))) { throw 'Initialize managed retention before starting services.' }
$logRoot = Join-Path $projectRoot 'test-runtime/prototype-logs'
$metadataPath = Join-Path $logRoot 'services.json'
$saved = Get-Content -LiteralPath $metadataPath | ConvertFrom-Json
$expectedDb = [IO.Path]::GetFullPath((Join-Path $projectRoot 'test-runtime/real-acceptance-20261004.db'))
if ([IO.Path]::GetFullPath($saved.database) -ne $expectedDb) { throw 'Unexpected database; refusing restart.' }
if (!(Test-Path -LiteralPath $expectedDb)) { throw 'Isolated database is missing.' }
$listener = @(Get-NetTCPConnection -LocalPort 18501 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count -ne 1) { throw 'Expected one prototype backend listener.' }
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
$launcher = Get-CimInstance Win32_Process -Filter "ProcessId=$($saved.api_pid)"
if (!$process -or !$launcher -or $process.CommandLine -notmatch '(uvicorn.*api.main:app.*18501|run_managed_api.py)' -or
    $launcher.CommandLine -notmatch '(uvicorn.*api.main:app.*18501|run_managed_api.py)' -or
    ($process.ProcessId -ne $saved.api_pid -and $process.ParentProcessId -ne $saved.api_pid)) {
    throw 'Backend process identity does not match the saved prototype.'
}
$env:PROFESSOR_DB_PATH = $expectedDb
$env:APP_MODE = 'local'
$env:OPENAI_API_KEY = ''
$env:AI_EXPLANATIONS = '0'
$env:AUTH_ALLOW_DEV_LOGIN = 'true'
$env:AUTH_DEV_EMAIL = 'prototype-review@localhost'
foreach ($name in @('AUTH_CLIENT_ID','AUTH_CLIENT_SECRET','GMAIL_CLIENT_ID','GMAIL_CLIENT_SECRET')) {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
$env:AUTH_REDIRECT_URI = 'http://localhost:18501/api/auth/callback'
$env:AUTH_LOGIN_SUCCESS_URL = 'http://localhost:13310/account'
$env:AUTH_COOKIE_SECURE = 'false'
$env:CORS_ORIGINS = 'http://localhost:13310'
$env:GMAIL_TOKEN_DIR = Join-Path $projectRoot 'test-runtime/gmail-isolated'
$env:GMAIL_REDIRECT_URI = 'http://localhost:18501/api/gmail/callback'
$env:GMAIL_REDIRECT_SUCCESS_URL = 'http://localhost:13310/outreach'
Push-Location $projectRoot
try {
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') -c "import runtime_config; from api.auth import config; from api.gmail import config as gmail; import google.auth, cachecontrol; config.client_id(); config.client_secret(); gmail.client_id(); gmail.client_secret(); print('Private configuration and verifier dependencies available.')"
    if ($LASTEXITCODE -ne 0) { throw 'Configuration preflight failed; existing service retained.' }
} finally { Pop-Location }
Stop-Process -Id $process.ProcessId
if ($launcher.ProcessId -ne $process.ProcessId) {
    Stop-Process -Id $launcher.ProcessId -ErrorAction SilentlyContinue
}
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (!(Get-NetTCPConnection -LocalPort 18501 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}
if (Get-NetTCPConnection -LocalPort 18501 -State Listen -ErrorAction SilentlyContinue) { throw 'Backend port did not clear.' }
$api = Start-Process -FilePath (Join-Path $projectRoot '.venv/Scripts/python.exe') -ArgumentList 'scripts/run_managed_api.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
$saved.api_pid = $api.Id
$saved | ConvertTo-Json | Set-Content -LiteralPath $metadataPath
Write-Output 'Hardened backend started; frontend retained. No sign-in, Gmail request, or paid AI call made.'

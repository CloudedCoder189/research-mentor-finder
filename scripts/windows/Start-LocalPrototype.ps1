param([switch]$EnableGoogleSignIn, [switch]$EnableGmail)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$env:RETENTION_ROOT = Join-Path $projectRoot 'test-runtime/managed-retention'
$env:RETENTION_KEY_FILE = Join-Path $projectRoot 'test-runtime/retention-key.txt'
if (!(Test-Path -LiteralPath (Join-Path $env:RETENTION_ROOT 'store.json'))) { throw 'Initialize managed retention before starting services.' }
$isolatedDb = Join-Path $projectRoot 'test-runtime\real-acceptance-20261004.db'
if (!(Test-Path -LiteralPath $isolatedDb)) { throw 'Acceptance database is missing. Do not substitute the live database.' }
foreach ($port in @(13310,18501)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use." }
}
$env:PROFESSOR_DB_PATH = $isolatedDb
$env:APP_MODE = 'local'
$env:OPENAI_API_KEY = ''
$env:AI_EXPLANATIONS = '0'
$env:AUTH_ALLOW_DEV_LOGIN = 'true'
$env:AUTH_DEV_EMAIL = 'prototype-review@localhost'
if ($EnableGoogleSignIn) {
    # Let the private project .env supply credentials; never print values.
    Remove-Item Env:AUTH_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:AUTH_CLIENT_SECRET -ErrorAction SilentlyContinue
    Push-Location $projectRoot
    try {
        & (Join-Path $projectRoot '.venv\Scripts\python.exe') -c "import runtime_config; from api.auth import config; config.client_id(); config.client_secret(); print('Google sign-in credentials present.')"
        if ($LASTEXITCODE -ne 0) { throw 'Configure AUTH_CLIENT_ID and AUTH_CLIENT_SECRET in the private working .env first.' }
    } finally { Pop-Location }
} else {
    $env:AUTH_CLIENT_ID = ''
    $env:AUTH_CLIENT_SECRET = ''
}
$env:AUTH_REDIRECT_URI = 'http://localhost:18501/api/auth/callback'
$env:AUTH_LOGIN_SUCCESS_URL = 'http://localhost:13310/account'
$env:AUTH_COOKIE_SECURE = 'false'
$env:CORS_ORIGINS = 'http://localhost:13310'
if ($EnableGmail) {
    Remove-Item Env:GMAIL_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:GMAIL_CLIENT_SECRET -ErrorAction SilentlyContinue
    Push-Location $projectRoot
    try {
        & (Join-Path $projectRoot '.venv\Scripts\python.exe') -c "import runtime_config; from api.gmail import config; config.client_id(); config.client_secret(); print('Gmail client credentials present.')"
        if ($LASTEXITCODE -ne 0) { throw 'Configure the separate Gmail client in the private working .env first.' }
    } finally { Pop-Location }
    $env:GMAIL_TOKEN_DIR = Join-Path $projectRoot 'test-runtime\gmail-isolated'
} else {
    $env:GMAIL_CLIENT_ID = ''
    $env:GMAIL_CLIENT_SECRET = ''
    $env:GMAIL_TOKEN_DIR = Join-Path $projectRoot 'test-runtime\gmail-disabled'
}
$env:GMAIL_REDIRECT_URI = 'http://localhost:18501/api/gmail/callback'
$env:GMAIL_REDIRECT_SUCCESS_URL = 'http://localhost:13310/outreach'
$env:NEXT_TELEMETRY_DISABLED = '1'
$logRoot = Join-Path $projectRoot 'test-runtime\prototype-logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$api = Start-Process -FilePath (Join-Path $projectRoot '.venv\Scripts\python.exe') -ArgumentList 'scripts/run_managed_api.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
try {
    $front = Start-Process -FilePath 'C:\Program Files\nodejs\node.exe' -ArgumentList 'scripts/run_managed_frontend.mjs' -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru
} catch { Stop-Process -Id $api.Id; throw }
@{ api_pid = $api.Id; frontend_pid = $front.Id; database = $isolatedDb; url = 'http://localhost:13310' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot 'services.json')
Write-Output 'Prototype: http://localhost:13310 — isolated database; paid AI disabled.'

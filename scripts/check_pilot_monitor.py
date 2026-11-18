"""Read-only pilot checks; credentials remain local and output is redacted."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://professor-finder-production.up.railway.app'
STATE = ROOT/'test-runtime/pilot-monitor-state.json'
ACCESS_MODE = ROOT/'test-runtime/pilot-monitor-access-mode.json'
UTC = timezone.utc


def stale(value, now, hours):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.tzinfo is None or not -timedelta(minutes=5) <= now-stamp <= timedelta(hours=hours)
    except (ValueError, TypeError, AttributeError):
        return True


def evaluate_health(data, now):
    problems = []
    for component in ('retention', 'offsite'):
        status = data.get(component) or {}
        if status.get('status') != 'ok':
            problems.append(component+'_failed')
        elif stale(status.get('last_success'), now, 3):
            problems.append(component+'_stale')
    if not (data.get('offsite') or {}).get('covered_backups', 0):
        problems.append('no_synchronized_backups')
    return problems


def transition(previous, problems):
    before = sorted(previous.get('problems', []))
    after = sorted(set(problems))
    return {'problems':after, 'notify':after != before,
            'event':'failure' if after else ('recovery' if before else 'healthy')}


def unprotect(path):
    script = "Add-Type -AssemblyName System.Security; $raw=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes('"+str(path)+"'),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); [Console]::Write([Text.Encoding]::UTF8.GetString($raw))"
    result = subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,encoding='utf-8',timeout=15)
    if result.returncode:
        raise RuntimeError('Credential escrow unavailable.')
    return result.stdout


def evaluate_public_signal(status, text):
    # The public proxy hides detailed /api/health diagnostics. This endpoint
    # checks retention, offsite freshness and daily backup age server-side.
    return [] if status == 200 and text == 'ready' else ['public_backup_signal_unavailable']


def check_once(now):
    import requests
    problems = []
    observations = {}
    try:
        response = requests.get(ORIGIN+'/__pilot_health',timeout=15)
        observations['readiness_http'] = response.status_code
        if response.status_code != 200 or response.text != 'ready':
            problems.append('app_unavailable')
    except requests.RequestException:
        problems.append('app_unreachable')
    try:
        password = (ROOT/'test-runtime/hosted-pilot-private/owner-password.txt').read_text().strip()
        frontend = requests.get(ORIGIN+'/account',auth=('owner',password),timeout=15)
        observations['frontend_http'] = frontend.status_code
        if frontend.status_code != 200 or 'Research' not in frontend.text:
            problems.append('frontend_unavailable')
        response = requests.get(ORIGIN+'/api/health',auth=('owner',password),timeout=15)
        observations['protected_health_http'] = response.status_code
        public_mode = ACCESS_MODE.exists() and json.loads(ACCESS_MODE.read_text(encoding='utf-8')).get('mode') == 'public'
        if response.status_code == 404 and public_mode:
            signal = requests.get(ORIGIN+'/__pilot_monitor',timeout=15)
            observations['public_backup_signal_http'] = signal.status_code
            problems.extend(evaluate_public_signal(signal.status_code,signal.text))
            observations['offsite_status'] = 'redacted_signal_ok' if signal.status_code == 200 and signal.text == 'ready' else 'signal_failed'
        elif response.status_code != 200:
            problems.append('protected_health_unavailable')
        else:
            data = response.json()
            problems.extend(evaluate_health(data,now))
            observations['offsite_status'] = (data.get('offsite') or {}).get('status')
    except (OSError, requests.RequestException, ValueError, TypeError, AttributeError):
        problems.append('protected_health_check_failed')
    try:
        credentials = json.loads(unprotect(ROOT/'test-runtime/hosted-pilot-private/offsite-storage-credentials.dpapi'))
        os.environ.update({'OFFSITE_BUCKET':credentials['bucketName'],'OFFSITE_ENDPOINT':credentials['endpoint'],
            'OFFSITE_ACCESS_KEY_ID':credentials['accessKeyId'],'OFFSITE_SECRET_ACCESS_KEY':credentials['secretAccessKey'],
            'OFFSITE_REGION':credentials['region'],'OFFSITE_PREFIX':'professor-finder-v1'})
        sys.path.insert(0,str(ROOT))
        from api.offsite import Archive, BACKUP_NAME, MARKER
        archive = Archive(SimpleNamespace(cipher=None))  # Monitoring never requests the decryption key.
        head = archive.client.head_object(Bucket=archive.bucket,Key=archive.key('current-ledger.fernet'))
        if stale(head.get('LastModified'),now,3):
            problems.append('remote_ledger_stale')
        latest = None
        count = 0
        for page in archive.client.get_paginator('list_objects_v2').paginate(Bucket=archive.bucket,Prefix=archive.key('backups/')):
            for item in page.get('Contents', []):
                if not BACKUP_NAME.fullmatch(item['Key'].rsplit('/',1)[-1]):
                    continue
                metadata = archive.client.head_object(Bucket=archive.bucket,Key=item['Key']).get('Metadata',{})
                if metadata.get('managed-by') != MARKER:
                    continue
                count += 1
                stamp = datetime.fromisoformat(metadata['created-at'])
                latest = max(latest,stamp) if latest else stamp
        observations['remote_registered_backup_count'] = count
        if stale(latest,now,27):
            problems.append('remote_daily_backup_stale')
    except Exception:
        problems.append('backup_storage_check_failed')
    return sorted(set(problems)), observations


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-state',action='store_true',help='Do not update incident state.')
    args=parser.parse_args()
    problems,observations=check_once(datetime.now(UTC))
    if problems:
        time.sleep(5)
        problems,observations=check_once(datetime.now(UTC))
    try:
        previous=json.loads(STATE.read_text()) if STATE.exists() else {}
    except (OSError,ValueError):
        previous={'problems':['monitor_state_unavailable']}
    result=transition(previous,problems)
    result.update({'checked_at':datetime.now(UTC).isoformat(),'observations':observations,
        'scope':'local-computer hourly pilot monitoring; not always-on external monitoring'})
    if not args.no_state:
        temporary=STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(result,indent=2),encoding='utf-8')
        os.replace(temporary,STATE)
    print(json.dumps(result))
    return 1 if problems else 0


if __name__=='__main__':
    raise SystemExit(main())

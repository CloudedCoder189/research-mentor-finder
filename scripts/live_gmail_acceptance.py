"""Opt-in live draft integration check. Never sends or searches the mailbox."""
import base64
import json
import os
import sqlite3
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
os.environ['PROFESSOR_DB_PATH'] = str(ROOT / 'test-runtime/real-acceptance-20261004.db')
os.environ['GMAIL_TOKEN_DIR'] = str(ROOT / 'test-runtime/gmail-isolated')
os.environ['OPENAI_API_KEY'] = ''
os.environ['AI_EXPLANATIONS'] = '0'

import requests
import runtime_config
from api.gmail import oauth, service, token_store
from api.schemas.gmail import GmailDraftRequest
from database import get_professor_outreach
from scripts.real_acceptance_snapshot import SOURCE, DEST, EVIDENCE, fingerprint, professors

OUTPUT = ROOT / 'evidence/gmail-2026-10-04/live-draft-results.json'
SUBJECT = '[PROTOTYPE TEST - DO NOT SEND] Gmail draft verification'
UPDATED = SUBJECT + ' - updated'
audit = []
known_drafts = set()
original_request = requests.Session.request


def draft_only_request(session, method, url, *args, **kwargs):
    parsed = urlsplit(url)
    method = method.upper()
    operation = None
    if parsed.scheme == 'https' and parsed.netloc == 'oauth2.googleapis.com' and parsed.path == '/token' and method == 'POST':
        operation = 'refresh_token'
    if parsed.scheme == 'https' and parsed.netloc == 'gmail.googleapis.com':
        if parsed.path == '/gmail/v1/users/me/profile' and method == 'GET':
            operation = 'account_profile'
        if parsed.path == '/gmail/v1/users/me/drafts' and method == 'POST':
            operation = 'create_test_draft'
        if parsed.path in {f'/gmail/v1/users/me/drafts/{draft_id}' for draft_id in known_drafts} and method in ('PUT', 'GET'):
            operation = 'update_test_draft' if method == 'PUT' else 'read_test_draft'
    if operation is None:
        raise RuntimeError('Operation outside the draft-only test allowlist blocked.')
    audit.append(operation)
    return original_request(session, method, url, *args, **kwargs)


def run():
    with sqlite3.connect(DEST.as_uri() + '?mode=ro', uri=True) as db:
        users = [row[0] for row in db.execute("SELECT DISTINCT user_id FROM sessions WHERE user_id LIKE 'google:%' AND expires_at > datetime('now')")]
    connected = [(user, token_store.load_credentials(user)) for user in users]
    connected = [(user, cred) for user, cred in connected if cred.get('token', {}).get('access_token')]
    if len(connected) != 1:
        raise RuntimeError('Exactly one connected Google test account is required.')
    user_id, credentials = connected[0]
    recipient = credentials.get('account_email', '')
    if not recipient:
        raise RuntimeError('Connected account address is missing.')
    professor_id = 1126
    current = get_professor_outreach([professor_id], user_id=user_id).get(professor_id, {})
    if current.get('email_subject') and not current['email_subject'].startswith(SUBJECT):
        raise RuntimeError('Existing user draft content preserved; test will not overwrite it.')
    existing = current.get('gmail_draft_id', '')
    requests.Session.request = draft_only_request
    checks = {}
    try:
        request = GmailDraftRequest(to=recipient, subject=SUBJECT, body='Synthetic prototype acceptance draft. Addressed to the connected account only. Do not send.', notes='Prototype Gmail integration test only; no professor was contacted.')
        if existing:
            if str(current.get('email_to', '')).casefold() != recipient.casefold():
                raise RuntimeError('Existing draft recipient does not match the connected account.')
            known_drafts.add(existing)
            result = service.update_gmail_draft(professor_id, request, user_id)
        else:
            result = service.create_gmail_draft(professor_id, request, user_id)
        draft_id = result.gmail_draft_id
        if not draft_id:
            raise RuntimeError('Gmail did not return a draft identifier.')
        known_drafts.add(draft_id)
        checks['gmail_draft_exists'] = True
        updated_body = 'Synthetic prototype acceptance draft, updated successfully. Do not send. No professor was contacted.'
        updated_request = GmailDraftRequest(to=recipient, subject=UPDATED, body=updated_body, notes=request.notes)
        updated = service.update_gmail_draft(professor_id, updated_request, user_id)
        checks['update_preserves_draft_id'] = updated.gmail_draft_id == draft_id
        repeated = service.update_gmail_draft(professor_id, updated_request, user_id)
        checks['repeated_update_preserves_draft_id'] = repeated.gmail_draft_id == draft_id
        response = requests.get(f'https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}', headers={'Authorization': f'Bearer {oauth.access_token(user_id)}'}, params={'format': 'raw'}, timeout=25)
        if response.status_code != 200:
            raise oauth.GmailApiError('Test draft readback failed.', status=response.status_code)
        raw = response.json()['message']['raw']
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        checks['recipient_is_connected_account_only'] = str(message['To']).casefold() == recipient.casefold()
        checks['updated_subject_read_back'] = str(message['Subject']) == UPDATED
        checks['updated_body_read_back'] = message.get_body(preferencelist=('plain',)).get_content().strip() == updated_body
        saved = get_professor_outreach([professor_id], user_id=user_id)[professor_id]
        checks['local_draft_metadata_persisted'] = saved['gmail_draft_id'] == draft_id and saved['email_subject'] == UPDATED
        baseline = json.loads((EVIDENCE / 'snapshot.json').read_text())
        checks['original_database_unchanged'] = fingerprint(SOURCE) == baseline['source_before']
        with sqlite3.connect(DEST.as_uri() + '?mode=ro', uri=True) as db:
            checks['researcher_rows_unchanged'] = professors(db) == baseline['professors']
        result = {'passed': all(checks.values()), 'checks': checks, 'operations': audit, 'email_sent': False, 'mailbox_search_performed': False, 'test_draft_retained': True, 'test_recipient': 'connected account only', 'note': 'Service-level live Gmail integration. HTTP authentication was tested separately. No account addresses, IDs, credentials or tokens retained in this report.'}
        OUTPUT.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        if not result['passed']:
            raise SystemExit(1)
    finally:
        requests.Session.request = original_request


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        result = {'passed': False, 'error_type': type(exc).__name__, 'provider_http_status': getattr(exc, 'status', None), 'operations': audit, 'email_sent': False, 'note': 'Error details omitted to protect credentials and account data. A local test draft may have been saved before the provider error.'}
        OUTPUT.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        raise SystemExit(1)

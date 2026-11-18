"""One-shot live explanation acceptance: synthetic profile, two calls, $0.01 cap.

No Gmail/Google requests, embeddings, retries, key persistence or personal data.
The ledger reserves worst-case cost before dispatch and prevents accidental reruns.
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

from dotenv import dotenv_values
from scripts.real_acceptance_snapshot import ROOT, SOURCE, DEST, EVIDENCE, fingerprint, professors

OUTPUT = ROOT / 'evidence/ai-live-2026-10-04'
CAP = 0.01
MAX_CALLS = 2
INPUT_RATE = 0.25 / 1_000_000
OUTPUT_RATE = 2.0 / 1_000_000
private = dotenv_values(SOURCE.parents[1] / '.env')
model = private.get('OPENAI_TEXT_MODEL') or private.get('OPENAI_MODEL') or 'gpt-5-mini'
if model != 'gpt-5-mini' or not private.get('OPENAI_API_KEY'):
    raise SystemExit('Configured gpt-5-mini key required; no provider call made.')
os.environ.update(PROFESSOR_DB_PATH=str(DEST), APP_MODE='local',
                  AUTH_ALLOW_DEV_LOGIN='true', AUTH_DEV_EMAIL='ai-budget-test@localhost',
                  OPENAI_API_KEY=private['OPENAI_API_KEY'], OPENAI_TEXT_MODEL=model,
                  AI_EXPLANATIONS='1', AUTH_COOKIE_SECURE='false')

import httpx
from openai import OpenAI
from fastapi.testclient import TestClient
from api.main import app
from database import fetch_professors
import services.ai_explanation as ai
from services.recommendations import recommend_from_profile, score_for_profile


class ResponsesOnly(httpx.HTTPTransport):
    def handle_request(self, request):
        if (request.method, request.url.scheme, request.url.host, request.url.path) != (
                'POST', 'https', 'api.openai.com', '/v1/responses'):
            raise RuntimeError('Provider operation outside explanation allowlist blocked.')
        return super().handle_request(request)


def run():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ledger_path = OUTPUT / 'spending-ledger.json'
    ledger = {'cap_usd': CAP, 'max_provider_calls': MAX_CALLS, 'model': model,
              'pricing_source': 'https://developers.openai.com/api/docs/models/gpt-5-mini',
              'calls': []}
    # Fail closed: an existing ledger means this budget has already been opened.
    with ledger_path.open('x', encoding='utf-8') as handle:
        json.dump(ledger, handle, indent=2)

    def save():
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding='utf-8')

    provider = OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url='https://api.openai.com/v1',
                      max_retries=0, timeout=ai.REQUEST_TIMEOUT_SECONDS,
                      http_client=httpx.Client(transport=ResponsesOnly(retries=0), timeout=20))

    def bounded_create(**kwargs):
        assert kwargs['model'] == model and kwargs['store'] is False
        assert kwargs['max_output_tokens'] == 1024 and 'tools' not in kwargs
        # UTF-8 byte count is a conservative token bound for these text inputs;
        # an extra 4096 tokens reserves protocol/formatting overhead.
        upper_input = sum(len(kwargs[key].encode('utf-8')) for key in ('instructions', 'input')) + 4096
        reserved = upper_input * INPUT_RATE + kwargs['max_output_tokens'] * OUTPUT_RATE
        if len(ledger['calls']) >= MAX_CALLS or sum(c['reserved_usd'] for c in ledger['calls']) + reserved > CAP:
            raise RuntimeError('Hard test spending/call limit reached before dispatch.')
        entry = {'reserved_usd': round(reserved, 9), 'state': 'reserved_before_dispatch'}
        ledger['calls'].append(entry)
        save()
        start = time.monotonic()
        try:
            response = provider.responses.create(**kwargs)
            usage = response.usage
            # Charge all input at the uncached rate, which overstates cached input.
            entry.update(state='completed', input_tokens=usage.input_tokens,
                         output_tokens=usage.output_tokens,
                         cost_upper_usd=round(usage.input_tokens * INPUT_RATE + usage.output_tokens * OUTPUT_RATE, 9),
                         latency_seconds=round(time.monotonic() - start, 3),
                         response_status=response.status)
            assert entry['cost_upper_usd'] <= reserved
            return response
        except Exception as error:
            entry.update(state='failed_or_unknown', error_type=type(error).__name__,
                         cost_upper_usd=reserved, latency_seconds=round(time.monotonic() - start, 3))
            raise
        finally:
            save()

    ai._new_client = lambda: SimpleNamespace(responses=SimpleNamespace(create=bounded_create))
    ai.clear_cache()
    checks = {}
    statuses = []
    profile = {'interests': ['Machine learning'], 'skills': ['Python'],
               'interest_text': 'Synthetic test: computer vision and robotics interests.',
               'coursework': ['Machine Learning'], 'experience': ['Synthetic image classification project'],
               'preferences': {'locations': [], 'remote_ok': True}}
    records = fetch_professors(omit_embeddings=True)

    def payload(student):
        ranked = recommend_from_profile(records, student, limit=20)[0]
        assert ranked and ranked[0]['match']['research_fit_score'] >= 30
        return {'profile': student, 'researcher_id': ranked[0]['record']['id'], 'include_ai': True}

    def explanation(client, request, headers):
        result = client.post('/api/recommendations/explain', json=request, headers=headers)
        assert result.status_code == 200
        match = result.json()['results'][0]['match']
        status = match['ai_explanation']['status']
        statuses.append(status)
        return match

    try:
        request = payload(profile)
        with TestClient(app) as client:
            checks['anonymous_ai_rejected'] = client.post('/api/recommendations/explain', json=request).status_code == 401
            login = client.post('/api/auth/dev-login')
            assert login.status_code == 200
            headers = {'X-CSRF-Token': login.json()['csrf_token']}
            checks['missing_csrf_rejected'] = client.post('/api/recommendations/explain', json=request).status_code == 403
            plain = client.post('/api/recommendations/explain', json={**request, 'include_ai': False}).json()['results'][0]['match']
            checks['deterministic_requires_no_paid_call'] = len(ledger['calls']) == 0 and plain['ai_explanation'] is None
            first = explanation(client, request, headers)
            checks['live_ai_validated'] = first['ai_explanation']['status'] == 'ai'
            if not checks['live_ai_validated']:
                raise RuntimeError('Live explanation used fallback; cache test would cause an extra call.')
            repeated = explanation(client, request, headers)
            checks['repeat_is_cached_without_provider_call'] = repeated['ai_explanation']['status'] == 'cached' and len(ledger['calls']) == 1
            checks['score_and_deterministic_reasons_unchanged'] = first['research_fit_score'] == plain['research_fit_score'] and first['reasons'] == plain['reasons']
            checks['ai_uses_only_allowed_reasons'] = all(r in plain['reasons'] for r in first['ai_explanation']['reasons'])
            changed = {**profile, 'interest_text': 'Synthetic revised test: machine learning for computer vision.'}
            newer = explanation(client, payload(changed), headers)
            checks['profile_change_misses_cache'] = newer['ai_explanation']['status'] == 'ai' and len(ledger['calls']) == 2
            again = explanation(client, payload(changed), headers)
            checks['changed_profile_repeat_cached'] = again['ai_explanation']['status'] == 'cached' and len(ledger['calls']) == 2
    except Exception as error:
        checks['execution_completed'] = False
        statuses.append(type(error).__name__)
    finally:
        provider.close()
        baseline = json.loads((EVIDENCE / 'snapshot.json').read_text())
        checks['original_database_unchanged'] = fingerprint(SOURCE) == baseline['source_before']
        with sqlite3.connect(DEST.as_uri() + '?mode=ro', uri=True) as db:
            checks['researcher_rows_unchanged'] = professors(db) == baseline['professors']
        cost = sum(c.get('cost_upper_usd', c['reserved_usd']) for c in ledger['calls'])
        checks['within_authorized_budget'] = cost <= CAP
        result = {'passed': bool(checks) and all(checks.values()), 'checks': checks,
                  'statuses': statuses, 'provider_calls': len(ledger['calls']),
                  'cost_upper_usd': round(cost, 9), 'cap_usd': CAP,
                  'coverage': 'FastAPI TestClient routes with live provider; synthetic profile only',
                  'main_prototype_paid_ai_enabled': False}
        (OUTPUT / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    run()

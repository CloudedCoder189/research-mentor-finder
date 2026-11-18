from datetime import datetime, timedelta, timezone
import sqlite3
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import usage
from api.routes.usage import router
from api.auth.dependencies import require_user


def setup_store(monkeypatch,tmp_path):
    monkeypatch.setenv('AGGREGATE_USAGE_ENABLED','true')
    path=tmp_path/'aggregates.sqlite'
    monkeypatch.setattr(usage,'store_path',lambda:path)
    return path


def test_aggregate_schema_contains_no_payloads_or_identities(monkeypatch,tmp_path):
    path=setup_store(monkeypatch,tmp_path)
    usage.increment('searches');usage.increment('searches');usage.increment('secret search text')
    with sqlite3.connect(path) as c:
        assert [r[1] for r in c.execute('PRAGMA table_info(daily_counts)')]==['day','metric','total']
        assert c.execute('SELECT metric,total FROM daily_counts').fetchall()==[('searches',2)]
    assert usage.report(7)['rows'][0]['count']==2


def test_disabled_and_unavailable_counters_cannot_break_requests(monkeypatch,tmp_path):
    path=setup_store(monkeypatch,tmp_path)
    monkeypatch.setenv('AGGREGATE_USAGE_ENABLED','false');usage.increment('searches');assert not path.exists()
    monkeypatch.setenv('AGGREGATE_USAGE_ENABLED','true')
    monkeypatch.setattr(usage,'store_path',lambda:tmp_path/'missing'/'file.db')
    usage.increment('searches')


def test_retention_and_aggregate_bounds(monkeypatch,tmp_path):
    path=setup_store(monkeypatch,tmp_path);usage.increment('searches')
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO daily_counts VALUES(?,?,?)',((datetime.now(timezone.utc)-timedelta(days=95)).date().isoformat(),'searches',99))
        c.execute('UPDATE daily_counts SET total=1000000 WHERE day=?',(datetime.now(timezone.utc).date().isoformat(),))
    usage.increment('searches')
    with sqlite3.connect(path) as c:assert c.execute('SELECT total FROM daily_counts').fetchall()==[(1000000,)]


def test_pageview_origin_privacy_and_payload_guards(monkeypatch,tmp_path):
    path=setup_store(monkeypatch,tmp_path)
    monkeypatch.setenv('CORS_ORIGINS','https://example.org')
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.post('/api/usage/pageview',json={'page':'home'}).status_code==403
        assert client.post('/api/usage/pageview',json={'page':'home'},headers={'Origin':'https://evil.example'}).status_code==403
        assert client.post('/api/usage/pageview',json={'page':'home'},headers={'Origin':'https://example.org','DNT':'1'}).status_code==204
        assert client.post('/api/usage/pageview',json={'page':'home'},headers={'Origin':'https://example.org','Sec-GPC':'1'}).status_code==204
        assert not path.exists()
        assert client.post('/api/usage/pageview',json={'page':'home','query':'private'},headers={'Origin':'https://example.org'}).status_code==422
        assert client.post('/api/usage/pageview',json={'page':'/researchers/746'},headers={'Origin':'https://example.org'}).status_code==422
        assert client.post('/api/usage/pageview',json={'page':'researcher'},headers={'Origin':'https://example.org'}).status_code==204
    assert usage.report()['rows'][0]['metric']=='page:researcher'


def test_summary_requires_google_owner_and_never_returns_accounts(monkeypatch,tmp_path):
    setup_store(monkeypatch,tmp_path);monkeypatch.setenv('USAGE_ADMIN_EMAILS','owner@example.org')
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/usage/summary').status_code==401
        app.dependency_overrides[require_user]=lambda:SimpleNamespace(email='other@example.org',user_id='google:other')
        assert client.get('/api/usage/access').json()=={'allowed':False}
        assert client.get('/api/usage/summary').status_code==403
        app.dependency_overrides[require_user]=lambda:SimpleNamespace(email='owner@example.org',user_id='dev:owner')
        assert client.get('/api/usage/summary').status_code==403
        app.dependency_overrides[require_user]=lambda:SimpleNamespace(email='OWNER@example.org',user_id='google:owner')
        assert client.get('/api/usage/access').json()=={'allowed':True}
        r=client.get('/api/usage/summary');assert r.status_code==200
        assert set(r.json())=={'days','started_at','enabled','registered_accounts','rows','limitations'}
        assert 'owner@example.org' not in r.text
        assert client.get('/api/usage/summary?days=500').status_code==422


def test_action_classification_does_not_save_paths_or_researcher_ids():
    assert usage.action_metric('POST','/api/saved/746')=='researchers_saved'
    assert usage.action_metric('PATCH','/api/outreach/746')=='outreach_updates'
    assert usage.action_metric('GET','/api/saved/746') is None
    assert usage.action_metric('POST','/api/recommendations/explain') is None
    assert usage.action_metric('POST','/api/usage/pageview') is None

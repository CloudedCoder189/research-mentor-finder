"""Fault/partial-consent tests with synthetic secrets, never provider traffic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time

import pytest
import requests

from api.gmail import drafts, oauth, service, threads, token_store
from api.gmail.config import GMAIL_SCOPES


@pytest.fixture
def tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "tokens"))
    monkeypatch.setenv("GMAIL_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.delenv("GMAIL_TOKEN_ENCRYPTION_KEY", raising=False)
    return "google:synthetic"


@pytest.mark.parametrize("scope", [None, "", GMAIL_SCOPES[0], GMAIL_SCOPES[1], [*GMAIL_SCOPES]])
def test_incomplete_grants_are_not_stored(tokens, scope):
    with pytest.raises(oauth.GmailAuthError, match="both"):
        oauth._store_tokens(tokens, {"access_token": "synthetic-sensitive", "scope": scope})
    assert token_store.load_credentials(tokens) == {}


def test_granted_scopes_are_preserved_and_refresh_can_omit_them(tokens, monkeypatch):
    granted = " ".join(reversed(GMAIL_SCOPES)) + " openid"
    oauth._store_tokens(tokens, {"access_token": "synthetic-old", "refresh_token": "synthetic-refresh", "scope": granted})
    class Response:
        status_code = 200
        def json(self):
            return {"access_token": "synthetic-new", "expires_in": 3600}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())
    assert oauth.refresh_access_token_now(tokens) == "synthetic-new"
    saved = token_store.load_credentials(tokens)["token"]
    assert set(saved["scope"].split()) == set(GMAIL_SCOPES) | {"openid"}
    assert saved["refresh_token"] == "synthetic-refresh" and saved["scope_verified"]


def test_legacy_connection_requires_reconfirmation(tokens):
    token_store.save_credentials(tokens, {"client_id": "synthetic-client", "account_email": "synthetic@example.test", "token": {"access_token": "synthetic-old", "issued_at": int(time.time()), "expires_in": 3600, "scope": " ".join(GMAIL_SCOPES)}})
    assert not service.status(tokens).connected
    with pytest.raises(oauth.GmailAuthError, match="Reconnect"):
        oauth.access_token(tokens)


def test_partial_refresh_grant_clears_connection(tokens, monkeypatch):
    oauth._store_tokens(tokens, {"access_token": "synthetic-old", "refresh_token": "synthetic-refresh", "scope": " ".join(GMAIL_SCOPES)})
    response = type("Response", (), {"status_code": 200, "json": lambda self: {"access_token": "synthetic-new", "scope": GMAIL_SCOPES[0]}})()
    monkeypatch.setattr(requests, "post", lambda *a, **k: response)
    with pytest.raises(oauth.GmailAuthError):
        oauth.refresh_access_token_now(tokens)
    assert token_store.load_credentials(tokens) == {}


def test_refresh_token_rotation_is_preserved(tokens, monkeypatch):
    oauth._store_tokens(tokens, {"access_token": "synthetic-old", "refresh_token": "synthetic-refresh", "scope": " ".join(GMAIL_SCOPES)})
    response = type("Response", (), {"status_code": 200, "json": lambda self: {"access_token": "synthetic-new", "refresh_token": "synthetic-rotated"}})()
    monkeypatch.setattr(requests, "post", lambda *a, **k: response)
    oauth.refresh_access_token_now(tokens)
    assert token_store.load_credentials(tokens)["token"]["refresh_token"] == "synthetic-rotated"


def test_corrupt_credentials_can_be_disconnected(tokens):
    path = token_store.credentials_path(tokens)
    path.parent.mkdir(parents=True)
    path.write_text("invalid JSON", encoding="utf-8")
    token_store.save_pending_state(tokens, "synthetic-state")
    assert oauth.revoke(tokens) == "unconfirmed"
    assert not path.exists() and not token_store.pending_path(tokens).exists()


@pytest.mark.parametrize("timestamp", ["stale", "future", "malformed", "2026-01-01T00:00:00", ""])
def test_stale_invalid_pending_state_is_consumed(tokens, timestamp):
    # Compute relative times when the test runs, not at suite collection.
    if timestamp in {"stale", "future"}:
        timestamp = (datetime.now(timezone.utc) + timedelta(minutes=-11 if timestamp == "stale" else 1)).isoformat()
    token_store._write_json(token_store.pending_path(tokens), {"state": "synthetic-state", "created_at": timestamp})
    assert token_store.pop_pending_state(tokens) == ""
    assert not token_store.pending_path(tokens).exists()


def test_pending_state_single_consumer_under_concurrency(tokens):
    for _ in range(10):
        token_store.save_pending_state(tokens, "synthetic-state")
        with ThreadPoolExecutor(max_workers=8) as pool:
            states = list(pool.map(lambda _: token_store.pop_pending_state(tokens), range(16)))
        assert states.count("synthetic-state") == 1 and states.count("") == 15
        assert [p.name for p in token_store.pending_path(tokens).parent.iterdir()] == ["state.lock"]


@pytest.mark.parametrize("status", [200, 400, 503, None])
def test_disconnect_reports_revocation_truthfully_and_clears_pending(tokens, monkeypatch, status):
    token_store.save_credentials(tokens, {"client_id": "synthetic-client", "account_email": "synthetic@example.test", "token": {"access_token": "synthetic-access"}})
    token_store.save_pending_state(tokens, "synthetic-state")
    def post(*args, **kwargs):
        assert kwargs["data"]["token"] == "synthetic-access"
        if status is None:
            raise requests.RequestException("synthetic-sensitive detail")
        return type("Response", (), {"status_code": status})()
    monkeypatch.setattr(requests, "post", post)
    assert oauth.revoke(tokens) == ("revoked" if status == 200 else "unconfirmed")
    assert token_store.load_credentials(tokens) == {}
    assert token_store.pop_pending_state(tokens) == ""


@pytest.mark.parametrize("operation", ["draft", "thread"])
def test_provider_transport_errors_do_not_reflect_sensitive_details(tokens, monkeypatch, operation):
    def fail(*args, **kwargs):
        raise requests.RequestException("synthetic-credential cookie=private header=secret")
    monkeypatch.setattr(requests, "request" if operation == "draft" else "get", fail)
    with pytest.raises(oauth.GmailApiError) as error:
        if operation == "draft":
            drafts._call("synthetic-token", "POST", "https://example.test", {})
        else:
            threads.fetch_thread_state("synthetic-token", "synthetic-thread")
    assert str(error.value) == "Could not reach Gmail. Try again later."


@pytest.mark.parametrize("identity", ["google:ali/ce", "google_ali_ce", "dev_owner@example.test", "..", ".", "user:alias", "", "../outside"])
def test_ambiguous_or_unsafe_identities_cannot_access_storage(tokens, identity):
    with pytest.raises(token_store.TokenStoreError):
        token_store.credentials_path(identity)


def test_existing_canonical_paths_remain_compatible(tokens):
    assert token_store.credentials_path("google:123456789").parent.name == "google_123456789"
    assert token_store.credentials_path("dev:synthetic@example.test").parent.name == "dev_synthetic@example.test"

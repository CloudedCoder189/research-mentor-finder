"""End-to-end API tests for Gmail draft creation, plus write-boundary checks.

These tests exercise the FastAPI routes through ``TestClient`` with all Google
and Gmail traffic mocked. They prove the Gmail integration only ever writes to
per-user OAuth token files and to ``gmail_*`` metadata on the caller's own
``professor_outreach`` row, never to the ``professors`` table.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import database
from api.gmail import token_store
from api.main import create_app
from tests._auth_helpers import DEV_USER_ID, signed_client

BASE = {
    "name": "Gmail Boundary Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and robotics",
    "email": "gmail-boundary@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/gmail-boundary",
    "categories": "Machine Learning, Robotics",
    "source_type": "Test",
}


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = payload or {}
        self.text = text

    def json(self):
        return self._json


class _FakeGmail:
    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.exc: Exception | None = None

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.exc is not None:
            raise self.exc
        return _Response(201 if method == "POST" else 200, {"id": "draft-1", "message": {"threadId": "thread-1"}})


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    monkeypatch.setenv("GMAIL_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "test-secret")
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor_id = int(database.fetch_professors()[0]["id"])
    yield {"tmp_path": tmp_path, "professor_id": professor_id, "monkeypatch": monkeypatch}
    database.DB_PATH = original


def _client() -> TestClient:
    # Redirects are disabled so OAuth redirects are asserted on the Location
    # header instead of httpx following them to http://localhost:3000.
    return signed_client()


def _seed_credentials() -> None:
    token_store.save_credentials(
        DEV_USER_ID,
        {
            "client_id": "test-client.apps.googleusercontent.com",
            "account_email": "me@example.com",
            "token": {"access_token": "at", "refresh_token": "rt", "issued_at": int(time.time()), "expires_in": 3600, "scope": "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.metadata", "scope_verified": True},
        },
    )


def _professors_snapshot() -> list[dict]:
    return database.fetch_professors()


# --- status -----------------------------------------------------------------


def test_status_is_disconnected_by_default(env) -> None:
    body = _client().get("/api/gmail/status").json()
    assert body["connected"] is False
    assert body["account_email"] == ""
    assert body["expires_in_seconds"] is None
    assert body["scope"] == "https://www.googleapis.com/auth/gmail.compose"
    assert body["draft_url"] == "https://mail.google.com/mail/u/0/#drafts"


# --- connect ----------------------------------------------------------------


def test_connect_requires_env_config(env) -> None:
    env["monkeypatch"].delenv("GMAIL_CLIENT_ID")
    env["monkeypatch"].delenv("GMAIL_CLIENT_SECRET")
    response = _client().get("/api/gmail/connect")
    assert response.status_code == 503
    assert "GMAIL_CLIENT_ID" in response.json()["detail"]


def test_connect_returns_consent_url(env) -> None:
    body = _client().get("/api/gmail/connect").json()
    assert body["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "access_type=offline" in body["auth_url"]
    assert "scope=" in body["auth_url"]


# --- callback ---------------------------------------------------------------


def test_callback_success_redirects_and_connects(env) -> None:
    token_store.save_pending_state(DEV_USER_ID, "expected-state")

    def fake_post(url, **kwargs):
        assert kwargs["data"]["grant_type"] == "authorization_code"
        return _Response(200, {"access_token": "at", "expires_in": 3600, "refresh_token": "rt", "scope": "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.metadata"})

    def fake_get(url, **kwargs):
        return _Response(200, {"emailAddress": "me@example.com"})

    monkeypatch = env["monkeypatch"]
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    response = _client().get("/api/gmail/callback?state=expected-state&code=the-code")
    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/outreach?gmail=connected"

    body = _client().get("/api/gmail/status").json()
    assert body["connected"] is True
    assert body["account_email"] == "me@example.com"
    assert token_store.load_credentials(DEV_USER_ID)["token"]["refresh_token"] == "rt"
    # Pending state was consumed exactly once.
    assert token_store.pop_pending_state(DEV_USER_ID) == ""


def test_callback_state_mismatch_redirects_to_failure(env) -> None:
    token_store.save_pending_state(DEV_USER_ID, "expected-state")
    response = _client().get("/api/gmail/callback?state=wrong&code=the-code")
    assert response.status_code == 302
    assert "auth_error" in response.headers["location"]
    assert token_store.load_credentials(DEV_USER_ID) == {}


def test_callback_error_redirects_to_failure(env) -> None:
    response = _client().get("/api/gmail/callback?error=access_denied")
    assert response.status_code == 302
    assert "auth_error" in response.headers["location"]


# --- draft create/update ----------------------------------------------------


def test_gmail_draft_lifecycle_keeps_professor_table_untouched(env, monkeypatch) -> None:
    _seed_credentials()
    fake = _FakeGmail()
    monkeypatch.setattr(requests, "request", fake)
    client = _client()
    before = _professors_snapshot()

    created = client.post(
        f"/api/outreach/{env['professor_id']}/gmail-draft",
        json={"to": "ok@example.com", "subject": "Subject", "body": "Body", "notes": "Note"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["gmail_draft_id"] == "draft-1"
    assert payload["gmail_thread_id"] == "thread-1"
    assert payload["gmail_account_email"] == "me@example.com"
    assert payload["gmail_draft_created_at"]
    assert payload["outreach"]["outreach"]["status"] == "Drafted"
    assert payload["outreach"]["outreach"]["notes"] == "Note"
    assert fake.calls[0][0] == "POST"
    assert fake.calls[0][1].endswith("/users/me/drafts")

    row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    assert row["gmail_draft_id"] == "draft-1"
    assert row["gmail_account_email"] == "me@example.com"
    assert row["outreach_status"] == "Email drafted"

    updated = client.patch(
        f"/api/outreach/{env['professor_id']}/gmail-draft",
        json={"subject": "Revised subject", "body": "Revised body"},
    )
    assert updated.status_code == 200
    assert updated.json()["outreach"]["outreach"]["email_subject"] == "Revised subject"
    put_call = fake.calls[1]
    assert put_call[0] == "PUT"
    assert put_call[1].endswith("/drafts/draft-1")

    assert _professors_snapshot() == before


def test_patch_without_existing_draft_returns_409(env, monkeypatch) -> None:
    _seed_credentials()
    monkeypatch.setattr(requests, "request", _FakeGmail())
    response = _client().patch(
        f"/api/outreach/{env['professor_id']}/gmail-draft",
        json={"subject": "Subject"},
    )
    assert response.status_code == 409
    assert "Create one first" in response.json()["detail"]


# --- failure behavior -------------------------------------------------------


def test_invalid_recipient_422_persists_locally_never_calls_gmail(env, monkeypatch) -> None:
    _seed_credentials()
    fake = _FakeGmail()
    monkeypatch.setattr(requests, "request", fake)
    before = _professors_snapshot()

    response = _client().post(
        f"/api/outreach/{env['professor_id']}/gmail-draft",
        json={"to": "not an email", "subject": "Subject", "body": "Body"},
    )
    assert response.status_code == 422
    assert fake.calls == []
    row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    assert row["email_subject"] == "Subject"
    assert row["gmail_draft_id"] == ""
    assert _professors_snapshot() == before


def test_gmail_failure_returns_502_and_preserves_local_draft(env, monkeypatch) -> None:
    _seed_credentials()
    fake = _FakeGmail()
    fake.exc = requests.RequestException("upstream timeout")
    monkeypatch.setattr(requests, "request", fake)
    before = _professors_snapshot()

    response = _client().post(
        f"/api/outreach/{env['professor_id']}/gmail-draft",
        json={"to": "ok@example.com", "subject": "Subject", "body": "Body", "notes": "Keep"},
    )
    assert response.status_code == 502
    row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    assert row["email_subject"] == "Subject"
    assert row["email_body"] == "Body"
    assert row["outreach_status"] == "Email drafted"
    assert row["gmail_draft_id"] == ""
    assert _professors_snapshot() == before


def test_unknown_researcher_is_404(env, monkeypatch) -> None:
    _seed_credentials()
    monkeypatch.setattr(requests, "request", _FakeGmail())
    response = _client().post(
        "/api/outreach/424242/gmail-draft",
        json={"to": "ok@example.com", "subject": "Subject", "body": "Body"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
    assert _professors_snapshot()


# --- disconnect -------------------------------------------------------------


def test_disconnect_revokes_and_clears_credentials(env, monkeypatch) -> None:
    _seed_credentials()
    revoked = {}

    def fake_post(url, **kwargs):
        revoked["token"] = kwargs["data"]["token"]
        return _Response(200)

    monkeypatch.setattr(requests, "post", fake_post)
    response = _client().post("/api/gmail/disconnect")
    assert response.status_code == 200
    assert response.json() == {"disconnected": True, "revocation": "revoked"}
    assert revoked["token"] == "rt"
    assert token_store.load_credentials(DEV_USER_ID) == {}
    assert _client().get("/api/gmail/status").json()["connected"] is False

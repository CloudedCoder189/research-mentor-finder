"""API tests for the opt-in one-time local-owner data import (Phase 6).

The pre-auth single-owner app stored saved/outreach rows under ``local-owner``
and Gmail credentials under ``data/gmail_tokens/local-owner/``. ``import-local``
copies the outreach rows to the signed-in account and moves the credentials
exactly once, then binds the import to that user forever.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from api.gmail import token_store
from api.main import create_app
from api.services import set_saved as api_set_saved
from database import DEFAULT_USER_ID
from tests._auth_helpers import client_for_user, dev_user_id, signed_client

BASE = {
    "name": "Import Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Import testing",
    "email": "import@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/import",
    "categories": "Machine Learning",
    "source_type": "Test",
}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor_id = int(database.fetch_professors()[0]["id"])
    yield {
        "tmp_path": tmp_path,
        "monkeypatch": monkeypatch,
        "professor_id": professor_id,
    }
    database.DB_PATH = original


def _seed_legacy_data(env: dict) -> None:
    """Create the pre-auth single-owner data shape: outreach rows + credentials."""
    pid = env["professor_id"]
    database.update_professor_outreach(
        pid,
        user_id=DEFAULT_USER_ID,
        notes="legacy note",
        email_subject="legacy subject",
        outreach_status="Email sent",
        email_sent_at="2026-07-01",
    )
    api_set_saved(pid, True, user_id=DEFAULT_USER_ID)
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {
            "client_id": "test-client.apps.googleusercontent.com",
            "account_email": "me@example.com",
            "token": {
                "access_token": "at",
                "refresh_token": "rt",
                "issued_at": int(time.time()),
                "expires_in": 3600,
            },
        },
    )


def test_import_copies_outreach_once_and_moves_tokens(env) -> None:
    _seed_legacy_data(env)
    pid = env["professor_id"]
    client = signed_client()
    before = database.fetch_professors()

    response = client.post("/api/auth/import-local")
    assert response.status_code == 200
    body = response.json()
    assert body["already_imported"] is False
    assert body["imported_outreach_rows"] == 1
    assert body["imported_gmail_tokens"] is True

    # Account now has a copy; legacy row is unchanged.
    saved = client.get("/api/saved").json()
    assert saved["total"] == 1
    assert saved["results"][0]["researcher"]["id"] == pid
    assert saved["results"][0]["outreach"]["status"] == "Sent"
    assert database.local_owner_outreach_exists() == 1
    assert database.fetch_professors() == before

    # Credentials were moved from local-owner to the account.
    assert token_store.credentials_path(DEFAULT_USER_ID).is_file() is False
    assert token_store.load_credentials(dev_user_id())["token"]["refresh_token"] == "rt"

    # Second call: idempotent, nothing more copied.
    again = client.post("/api/auth/import-local")
    assert again.status_code == 200
    assert again.json()["already_imported"] is True
    assert again.json()["imported_outreach_rows"] == 0
    assert again.json()["imported_gmail_tokens"] is False


def test_import_bound_to_first_user_only(env) -> None:
    _seed_legacy_data(env)
    signed_client().post("/api/auth/import-local")

    other = client_for_user("google:other", "other@example.com")
    response = other.post("/api/auth/import-local")
    assert response.status_code == 403
    assert "local owner" in response.json()["detail"]
    assert other.get("/api/saved").json()["total"] == 0


def test_import_with_nothing_to_import_is_ok(env) -> None:
    response = signed_client().post("/api/auth/import-local")
    assert response.status_code == 200
    assert response.json()["already_imported"] is True
    assert response.json()["imported_outreach_rows"] == 0
    assert response.json()["imported_gmail_tokens"] is False


def test_import_requires_authentication_and_csrf(env) -> None:
    assert TestClient(create_app(), follow_redirects=False).post("/api/auth/import-local").status_code == 401
    no_csrf = signed_client(with_csrf=False)
    assert no_csrf.post("/api/auth/import-local").status_code == 403
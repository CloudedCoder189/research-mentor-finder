"""Unit tests for the Gmail OAuth flow and per-user, protectable token store.

No live network or real Google credentials are used; the Gmail and Google
endpoints are mocked with ``requests`` stubs and all state lives under
``tmp_path``.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from api.gmail import oauth, token_store
from api.gmail.config import GMAIL_SCOPES, TOKEN_URL
from api.gmail.oauth import GmailAuthError
from database import DEFAULT_USER_ID


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = payload
        self.text = text

    def json(self):
        return self._json or {}


class _FakeFernet:
    """Stand-in for cryptography.Fernet so encryption paths run hermetic."""

    def encrypt(self, value: bytes) -> bytes:
        return b"enc:" + base64.b64encode(value)

    def decrypt(self, value: bytes) -> bytes:
        return base64.b64decode(value.replace(b"enc:", b""))


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, pytest.MonkeyPatch]:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    monkeypatch.setenv("GMAIL_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "test-secret")
    return tmp_path, monkeypatch


def test_token_store_round_trip_per_user(isolated) -> None:
    tmp_path = isolated[0]
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {"client_id": "x", "account_email": "me@example.com", "token": {"access_token": "at-1"}},
    )
    token_store.save_credentials(
        "someone-else",
        {"client_id": "x", "account_email": "them@example.com", "token": {"access_token": "at-2"}},
    )
    loaded = token_store.load_credentials(DEFAULT_USER_ID)
    assert loaded["account_email"] == "me@example.com"
    assert loaded["token"]["access_token"] == "at-1"
    assert token_store.load_credentials("someone-else")["token"]["access_token"] == "at-2"

    token_store.clear_credentials(DEFAULT_USER_ID)
    assert token_store.load_credentials(DEFAULT_USER_ID) == {}
    assert token_store.has_credentials(DEFAULT_USER_ID) is False
    # Clearing the local owner never touches another user's store.
    assert token_store.load_credentials("someone-else")["account_email"] == "them@example.com"
    # Token files live outside the database directory (never in professor DB files).
    assert not (tmp_path / "professors.db").exists()


def test_token_store_encrypts_with_fernet(isolated, monkeypatch) -> None:
    monkeypatch.setattr(token_store, "_fernet", lambda: _FakeFernet())
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {"client_id": "x", "account_email": "me@example.com", "token": {"access_token": "secret-at"}},
    )
    blob = json.loads(token_store.credentials_path(DEFAULT_USER_ID).read_text(encoding="utf-8"))
    assert blob["protected"] == "fernet"
    assert "secret-at" not in blob["ciphertext"]
    assert "access_token" not in json.dumps(blob)

    loaded = token_store.load_credentials(DEFAULT_USER_ID)
    assert loaded["token"]["access_token"] == "secret-at"


def test_pending_state_saved_and_popped(isolated) -> None:
    token_store.save_pending_state(DEFAULT_USER_ID, "abc123")
    assert token_store.pop_pending_state(DEFAULT_USER_ID) == "abc123"
    assert token_store.pop_pending_state(DEFAULT_USER_ID) == ""


def test_exchange_code_validates_state(isolated, monkeypatch) -> None:
    token_store.save_pending_state(DEFAULT_USER_ID, "expected")
    with pytest.raises(GmailAuthError, match="state"):
        oauth.exchange_code(DEFAULT_USER_ID, "code", "expected", "wrong")


@pytest.mark.parametrize("encrypted", [False, True])
def test_authorize_url_has_narrow_scope_and_state(isolated, monkeypatch, encrypted) -> None:
    monkeypatch.setattr(token_store, "_fernet", lambda: _FakeFernet() if encrypted else None)
    url = oauth.authorize_url(DEFAULT_USER_ID)
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["test-client.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://localhost:8000/api/gmail/callback"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == [" ".join(GMAIL_SCOPES)]
    assert "gmail.compose" in query["scope"][0]
    assert "gmail.metadata" in query["scope"][0]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["state"]

    assert token_store.pop_pending_state(DEFAULT_USER_ID) == query["state"][0]
    assert token_store.pop_pending_state(DEFAULT_USER_ID) == ""


def test_exchange_code_stores_tokens_and_profile(isolated, monkeypatch) -> None:
    calls = {}

    def fake_post(url, **kwargs):
        calls["post"] = (url, kwargs)
        return _Response(200, {"access_token": "at", "expires_in": 3600, "refresh_token": "rt", "scope": " ".join(GMAIL_SCOPES)})

    def fake_get(url, **kwargs):
        calls["get"] = (url, kwargs)
        assert kwargs["headers"]["Authorization"] == "Bearer at"
        return _Response(200, {"emailAddress": "me@example.com"})

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    oauth.exchange_code(DEFAULT_USER_ID, "auth-code", "expected-state", "expected-state")

    assert calls["post"][0] == TOKEN_URL
    assert calls["post"][1]["data"]["grant_type"] == "authorization_code"
    assert calls["post"][1]["data"]["code"] == "auth-code"
    assert calls["post"][1]["data"]["client_secret"] == "test-secret"

    credentials = token_store.load_credentials(DEFAULT_USER_ID)
    assert credentials["account_email"] == "me@example.com"
    assert credentials["token"]["access_token"] == "at"
    assert credentials["token"]["refresh_token"] == "rt"


def test_access_token_refreshes_near_expiry(isolated, monkeypatch) -> None:
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {
            "client_id": "x",
            "account_email": "me@example.com",
            "token": {
                "access_token": "stale",
                "refresh_token": "rt",
                "issued_at": 0,
                "expires_in": 3600,
                "scope": " ".join(GMAIL_SCOPES), "scope_verified": True,
            },
        },
    )

    def fake_post(url, **kwargs):
        assert "refresh_token" in kwargs["data"]
        return _Response(200, {"access_token": "fresh", "expires_in": 3600})

    monkeypatch.setattr(requests, "post", fake_post)
    assert oauth.access_token(DEFAULT_USER_ID) == "fresh"
    refreshed = token_store.load_credentials(DEFAULT_USER_ID)["token"]
    assert refreshed["access_token"] == "fresh"
    assert refreshed["refresh_token"] == "rt"


def test_revoked_refresh_clears_credentials(isolated, monkeypatch) -> None:
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {
            "client_id": "x",
            "account_email": "me@example.com",
            "token": {"access_token": "stale", "refresh_token": "rt", "issued_at": 0, "expires_in": 3600, "scope": " ".join(GMAIL_SCOPES), "scope_verified": True},
        },
    )

    def fake_post(url, **kwargs):
        return _Response(400, text="invalid_grant")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(GmailAuthError, match="revoked"):
        oauth.access_token(DEFAULT_USER_ID)
    assert token_store.load_credentials(DEFAULT_USER_ID) == {}


def test_disconnect_revokes_and_clears(isolated, monkeypatch) -> None:
    revoked = {}

    def fake_post(url, **kwargs):
        revoked["token"] = kwargs["data"]["token"]
        return _Response(200)

    token_store.save_credentials(
        DEFAULT_USER_ID,
        {"client_id": "x", "account_email": "me@example.com", "token": {"refresh_token": "rt"}},
    )
    monkeypatch.setattr(requests, "post", fake_post)
    oauth.revoke(DEFAULT_USER_ID)
    assert revoked["token"] == "rt"
    assert token_store.load_credentials(DEFAULT_USER_ID) == {}


def test_disconnect_survives_network_failure(isolated, monkeypatch) -> None:
    def failing_post(url, **kwargs):
        raise requests.RequestException("network down")

    token_store.save_credentials(
        DEFAULT_USER_ID,
        {"client_id": "x", "account_email": "me@example.com", "token": {"refresh_token": "rt"}},
    )
    monkeypatch.setattr(requests, "post", failing_post)
    oauth.revoke(DEFAULT_USER_ID)
    assert token_store.load_credentials(DEFAULT_USER_ID) == {}


def test_gmail_status_is_disconnected_by_default(isolated) -> None:
    assert token_store.load_credentials(DEFAULT_USER_ID) == {}
    assert oauth.expires_in_seconds(DEFAULT_USER_ID) is None
    assert oauth.account_email(DEFAULT_USER_ID) == ""

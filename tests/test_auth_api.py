"""API tests for Phase 6 app authentication (Google sign-in + dev sign-in).

Covers the session lifecycle: unauthenticated ``/api/auth/me``, developer
login, the Google authorize/callback flow (with mocked token exchange),
logout, CSRF enforcement, expired/invalid sessions, and the
single-session-per-user property.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from api.auth import config, google_oauth
from api.main import create_app
from tests._auth_helpers import DEV_USER_ID, client_for_user, signed_client

_BASE = {
    "name": "Auth API Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Authentication testing",
    "email": "auth-api@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/auth-api",
    "categories": "Machine Learning",
    "source_type": "Test",
}


@pytest.fixture()
def env(tmp_path: Path) -> dict:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([_BASE])
    yield {"tmp_path": tmp_path}
    database.DB_PATH = original


@pytest.fixture()
def anonymous() -> TestClient:
    return TestClient(create_app(), follow_redirects=False)


# --- /api/auth/me ------------------------------------------------------------


def test_me_unauthenticated(anonymous: TestClient) -> None:
    body = anonymous.get("/api/auth/me").json()
    assert body == {
        "authenticated": False,
        "user": None,
        "csrf_token": None,
        "dev_login_available": False,
        "local_import_available": False,
    }


def test_me_reflects_session(env, anonymous: TestClient) -> None:
    signed = signed_client()
    me = signed.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["local_import_available"] is True
    assert me["user"]["user_id"] == DEV_USER_ID
    assert me["user"]["email"] == "dev@localhost"
    assert isinstance(me["csrf_token"], str) and len(me["csrf_token"]) >= 16


# --- dev login ---------------------------------------------------------------


def test_dev_login_grants_access_to_protected_endpoints(env) -> None:
    client = signed_client()
    assert client.get("/api/saved").status_code == 200
    assert client.get("/api/profile").status_code == 200
    assert client.get("/api/gmail/status").status_code == 200


def test_dev_login_disabled_returns_404(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ALLOW_DEV_LOGIN", "false")
    response = TestClient(create_app(), follow_redirects=False).post("/api/auth/dev-login")
    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_single_session_per_user(env) -> None:
    first = signed_client()
    second = signed_client()  # logging in again supersedes the first session
    assert first.get("/api/saved").status_code == 401
    assert second.get("/api/saved").status_code == 200


def test_anonymous_requests_rejected_on_private_endpoints(env, anonymous: TestClient) -> None:
    assert anonymous.get("/api/saved").status_code == 401
    assert anonymous.get("/api/outreach").status_code == 401
    assert anonymous.get("/api/profile").status_code == 401
    assert anonymous.get("/api/gmail/status").status_code == 401


# --- Google sign-in redirects ------------------------------------------------


def test_login_redirects_to_google(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_CLIENT_ID", "auth-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "auth-secret")
    response = TestClient(create_app(), follow_redirects=False).get("/api/auth/login")
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith(config.AUTHORIZE_URL)
    assert "openid" in location and "email" in location and "profile" in location
    assert response.cookies.get("rmf_oauth_state")


def test_login_without_client_config_redirects_to_failure(
    env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("AUTH_CLIENT_SECRET", raising=False)
    response = TestClient(create_app(), follow_redirects=False).get("/api/auth/login")
    assert response.status_code == 307
    assert response.headers["location"].startswith("http://localhost:3000/account?auth=error")
    assert "reason=config" in response.headers["location"]


def test_callback_completes_google_sign_in(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_CLIENT_ID", "auth-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "auth-secret")
    monkeypatch.setattr(
        google_oauth,
        "exchange_code",
        lambda code, **kwargs: {
            "user_id": "google:10000000000001",
            "email": "student@example.com",
            "display_name": "Student Person",
            "avatar_url": "https://example.com/avatar.png",
        },
    )
    client = TestClient(create_app(), follow_redirects=False)
    assert client.get("/api/auth/login").status_code == 307
    state = client.cookies.get("rmf_oauth_state")
    assert state

    callback = client.get(f"/api/auth/callback?state={state}&code=the-code")
    assert callback.status_code == 307
    assert callback.headers["location"] == "http://localhost:3000/account?auth=success"
    assert client.cookies.get(config.session_cookie_name())

    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True
    assert me["user"]["user_id"] == "google:10000000000001"
    assert me["user"]["email"] == "student@example.com"
    assert me["user"]["display_name"] == "Student Person"
    assert me["user"]["avatar_url"] == "https://example.com/avatar.png"
    assert me["csrf_token"]

    row = database.get_user("google:10000000000001")
    assert row is not None and row["email"] == "student@example.com"


def test_callback_state_mismatch_rejected(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_CLIENT_ID", "auth-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "auth-secret")
    client = TestClient(create_app(), follow_redirects=False)
    client.get("/api/auth/login")
    response = client.get("/api/auth/callback?state=wrong-state&code=the-code")
    assert response.status_code == 307
    assert "reason=state" in response.headers["location"]
    assert client.cookies.get(config.session_cookie_name()) is None


def test_callback_denied_by_user(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_CLIENT_ID", "auth-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "auth-secret")
    client = TestClient(create_app(), follow_redirects=False)
    response = client.get("/api/auth/callback?error=access_denied")
    assert response.status_code == 307
    assert "reason=denied" in response.headers["location"]


def test_callback_token_verification_failure(env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_CLIENT_ID", "auth-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "auth-secret")

    def boom(code, **kwargs):
        raise google_oauth.GoogleAuthError("id token could not be verified")

    monkeypatch.setattr(google_oauth, "exchange_code", boom)
    client = TestClient(create_app(), follow_redirects=False)
    state = client.get("/api/auth/login") and client.cookies.get("rmf_oauth_state")
    response = client.get(f"/api/auth/callback?state={state}&code=bad")
    assert response.status_code == 307
    assert "reason=verification" in response.headers["location"]
    assert client.cookies.get(config.session_cookie_name()) is None


# --- logout & CSRF -----------------------------------------------------------


def test_logout_requires_csrf(env) -> None:
    client = signed_client(with_csrf=False)
    assert client.post("/api/auth/logout").status_code == 403


def test_logout_clears_session_and_cookie(env) -> None:
    client = signed_client()
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    # The server instructs the browser to wipe the cookie (empty value).
    assert response.headers["set-cookie"].startswith("rmf_session=")
    assert "Max-Age=0" in response.headers["set-cookie"]
    # Cookie was cleared server-side too: the old token must not resolve.
    assert client.get("/api/auth/me").json()["authenticated"] is False
    assert client.get("/api/saved").status_code == 401


def test_mutation_with_wrong_csrf_rejected(env) -> None:
    client = signed_client()
    client.headers.update({"X-CSRF-Token": "not-the-right-token"})
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post(f"/api/saved/{database.fetch_professors()[0]['id']}").status_code == 403


def test_expired_session_rejected(env) -> None:
    client = client_for_user("google:expired", "expired@example.com")
    assert client.get("/api/saved").status_code == 200
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01 00:00:00'")
    assert client.get("/api/saved").status_code == 401
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_unknown_session_token_rejected(env) -> None:
    client = TestClient(create_app(), follow_redirects=False)
    client.cookies.set(config.session_cookie_name(), "definitely-not-a-real-token", path="/")
    assert client.get("/api/saved").status_code == 401

def test_local_import_capability_is_not_offered_to_another_account(env):
    client = client_for_user("google:other-local-account", "other@example.test")
    assert client.get("/api/auth/me").json()["local_import_available"] is False
    assert client.post("/api/auth/import-local").status_code == 403


@pytest.mark.parametrize(
    "mode, setting, expected",
    [
        ("local", None, False),
        ("local", "true", True),
        ("production", "true", False),
        ("public", "true", False),
    ],
)
def test_dev_login_requires_explicit_local_opt_in(
    monkeypatch, mode, setting, expected
):
    monkeypatch.setenv("APP_MODE", mode)

    if setting is None:
        monkeypatch.delenv("AUTH_ALLOW_DEV_LOGIN", raising=False)
    else:
        monkeypatch.setenv("AUTH_ALLOW_DEV_LOGIN", setting)

    assert config.dev_login_allowed() is expected


def test_dev_login_disabled_by_default(env, monkeypatch):
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.delenv("AUTH_ALLOW_DEV_LOGIN", raising=False)

    client = TestClient(create_app(), follow_redirects=False)
    response = client.post("/api/auth/dev-login")

    assert response.status_code == 404

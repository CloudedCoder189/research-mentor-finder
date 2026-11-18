"""Shared helpers for tests that need authenticated API clients.

Phase 6 makes the private saved/outreach/profile/Gmail endpoints user-scoped,
so almost every API test must first sign in. These helpers reduce the churn:

* ``signed_client()`` returns a TestClient that has already completed
  ``POST /api/auth/dev-login`` and attaches the session cookie plus a valid
  ``X-CSRF-Token`` header on every request (mutations are CSRF-protected).
* ``dev_user_id()`` returns the user id the dev-login account maps to, which
  is also what Gmail token storage under these tests should use.

Callers keep using the client exactly as before; the extra auth headers are
transparent.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def dev_user_id() -> str:
    from api.auth.config import dev_user_id as _dev_user_id

    return _dev_user_id()


DEV_USER_ID = dev_user_id()


def client_for_user(
    user_id: str, email: str, *, display_name: str = "", with_csrf: bool = True
) -> TestClient:
    """Return a TestClient logged in as an arbitrary user.

    Used by isolation tests that need two distinct accounts. Sessions are
    issued directly from the database layer (no Google/dev-login required), so
    ``database.DB_PATH`` must already point at the throwaway DB.
    """
    import database
    from api.auth import config, sessions as session_service

    database.upsert_user(user_id=user_id, email=email, display_name=display_name)
    token, csrf = session_service.create_login_session(user_id)
    client = TestClient(create_app(), follow_redirects=False)
    client.cookies.set(config.session_cookie_name(), token, path="/")
    if with_csrf:
        client.headers.update({"X-CSRF-Token": csrf})
    return client



def dev_login(client: TestClient) -> None:
    from unittest.mock import patch

    # Explicitly enable developer login only for this test request.
    with patch.dict("os.environ", {"AUTH_ALLOW_DEV_LOGIN": "true"}):
        response = client.post("/api/auth/dev-login")

    assert response.status_code == 200, response.text


def signed_client(*, with_csrf: bool = True) -> TestClient:
    """Return a TestClient already signed in as the local developer.

    The returned client replays the session cookie and (optionally) a valid
    CSRF header, so endpoints that require auth work without per-call setup.
    """
    app = create_app()
    login = TestClient(app, follow_redirects=False)
    dev_login(login)
    headers = {}
    if with_csrf:
        body = login.get("/api/auth/me").json()
        headers["X-CSRF-Token"] = body["csrf_token"]
    client = TestClient(app, follow_redirects=False, headers=headers)
    client.cookies.update(dict(login.cookies))
    return client
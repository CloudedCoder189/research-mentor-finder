"""Google OAuth 2.0 (authorization code + offline refresh) for local Gmail.

Uses the ``requests`` library already present in the project; no Google SDKs.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from api.gmail import token_store
from api.gmail.config import (
    AUTHORIZE_URL,
    GMAIL_API_URL,
    GMAIL_SCOPES,
    REVOKE_URL,
    TOKEN_URL,
    client_id,
    client_secret,
    redirect_uri,
)


class GmailAuthError(RuntimeError):
    """Not connected, revoked, or consent denied."""


class GmailApiError(RuntimeError):
    """The Gmail API rejected the request."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def authorize_url(user_id: str) -> str:
    """Build the Google consent URL for the local-owner app."""
    state = token_store.new_state()
    token_store.save_pending_state(user_id, state)
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _validated_scope(response: dict, previous: dict | None = None) -> str:
    granted = response.get("scope")
    if granted is None and previous and previous.get("scope_verified") is True:
        granted = previous.get("scope")
    if not isinstance(granted, str) or not set(GMAIL_SCOPES).issubset(granted.split()):
        raise GmailAuthError("Gmail needs both draft and message-status permissions. Reconnect and approve both permissions.")
    return " ".join(sorted(set(granted.split())))


def _token_payload(access_token: str, expires_in: int, refresh_token: str | None, scope: str) -> dict[str, object]:
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(expires_in),
        "scope": scope,
        "scope_verified": True,
        "issued_at": int(time.time()),
        **({"refresh_token": refresh_token} if refresh_token else {}),
    }


def _store_tokens(user_id: str, token_response: dict) -> dict[str, object]:
    try:
        scope = _validated_scope(token_response)
    except GmailAuthError:
        token_store.clear_credentials(user_id)
        raise
    payload = _token_payload(
        str(token_response["access_token"]),
        int(token_response.get("expires_in", 3600)),
        (token_response.get("refresh_token") or None),  # type: ignore[arg-type]
        scope,
    )
    token_store.save_credentials(
        user_id,
        {
            "client_id": client_id(),
            "token": payload,
            "account_email": "",
            "connected_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return payload


def exchange_code(user_id: str, code: str, expected_state: str, provided_state: str) -> None:
    """Validate the CSRF state, then exchange the code for tokens."""
    if not expected_state or provided_state != expected_state:
        raise GmailAuthError("OAuth state did not match; the connection was not completed.")
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id(),
            "client_secret": client_secret(),
            "code": code,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise GmailAuthError("Google rejected the authorization code; try connecting again.")
    body = response.json()
    _store_tokens(user_id, body)
    account_email = _fetch_profile_email(_access_token(token_store.load_credentials(user_id)))
    if account_email:
        stored = token_store.load_credentials(user_id)
        stored["account_email"] = account_email
        token_store.save_credentials(user_id, stored)


def _access_token(credentials: dict) -> str:
    if not credentials.get("token"):
        raise GmailAuthError("Gmail is not connected.")
    return str(credentials["token"]["access_token"])


def _needs_refresh(token: dict) -> bool:
    issued = int(token.get("issued_at", 0))
    expires = int(token.get("expires_in", 3600))
    return time.time() > (issued + expires - 60)


def _refresh_access_token(user_id: str) -> dict[str, object]:
    credentials = token_store.load_credentials(user_id)
    refresh = str(credentials.get("token", {}).get("refresh_token", "") or "")
    if not refresh:
        raise GmailAuthError("Gmail is not connected (no refresh token).")
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id(),
            "client_secret": client_secret(),
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if response.status_code == 400 and "invalid_grant" in response.text:
        token_store.clear_credentials(user_id)
        raise GmailAuthError("The Gmail connection was revoked; reconnect to continue.")
    if response.status_code != 200:
        raise GmailAuthError("Gmail token refresh failed; try reconnecting.")
    body = response.json()
    previous = token_store.load_credentials(user_id)
    previous_token = dict(previous.get("token", {}))
    try:
        scope = _validated_scope(body, previous_token)
    except GmailAuthError:
        token_store.clear_credentials(user_id)
        raise
    payload = _token_payload(
        str(body["access_token"]),
        int(body.get("expires_in", 3600)),
        str(body.get("refresh_token") or previous_token.get("refresh_token") or "") or None,
        scope,
    )
    token_store.save_credentials(
        user_id,
        {
            "client_id": client_id(),
            "token": payload,
            "account_email": str(previous.get("account_email", "") or ""),
            "connected_at": str(previous.get("connected_at", "") or ""),
        },
    )
    return payload


def access_token(user_id: str) -> str:
    """Return a usable access token, refreshing first if near expiry."""
    credentials = token_store.load_credentials(user_id)
    token = dict(credentials.get("token", {}))
    if not token.get("access_token"):
        raise GmailAuthError("Gmail is not connected. Connect Gmail to continue.")
    if token.get("scope_verified") is not True:
        raise GmailAuthError("Reconnect Gmail to confirm its granted permissions.")
    _validated_scope(token)
    if _needs_refresh(token):
        token = _refresh_access_token(user_id)
    return str(token.get("access_token", ""))


def refresh_access_token_now(user_id: str) -> str:
    """Force a refresh (used when Gmail returns HTTP 401 despite caching)."""
    return str(_refresh_access_token(user_id).get("access_token", ""))


def _fetch_profile_email(access_token_value: str) -> str:
    response = requests.get(
        f"{GMAIL_API_URL}/users/me/profile",
        headers={"Authorization": f"Bearer {access_token_value}"},
        timeout=20,
    )
    if response.status_code != 200:
        return ""
    try:
        return str(response.json().get("emailAddress", "") or "")
    except ValueError:
        return ""


def revoke(user_id: str) -> str:
    """Remove local credentials and report upstream revocation separately."""
    try:
        credentials = token_store.load_credentials(user_id)
    except token_store.TokenStoreError:
        token_store.clear_credentials(user_id)
        token_store.pending_path(user_id).unlink(missing_ok=True)
        return "unconfirmed"
    token = credentials.get("token", {})
    value = str(token.get("refresh_token") or token.get("access_token") or "")
    result = "unconfirmed" if value else "not_connected"
    if value:
        try:
            response = requests.post(REVOKE_URL, data={"token": value}, timeout=20)
            if response.status_code == 200:
                result = "revoked"
        except requests.RequestException:
            pass
    token_store.clear_credentials(user_id)
    token_store.pending_path(user_id).unlink(missing_ok=True)
    return result


def account_email(user_id: str) -> str:
    return str(token_store.load_credentials(user_id).get("account_email", "") or "")


def expires_in_seconds(user_id: str) -> int | None:
    token = token_store.load_credentials(user_id).get("token", {})
    if not token:
        return None
    issued = int(token.get("issued_at", 0))
    expires = int(token.get("expires_in", 3600))
    return max(0, int((issued + expires) - time.time()))

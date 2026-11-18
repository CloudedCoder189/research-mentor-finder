"""Google Sign-In for the app-login flow.

Separate OAuth client and identity-only scopes (``openid email profile``), kept
deliberately apart from the Gmail compose client used for draft creation.
Google's verifier checks signatures using rotating public certificates.
"""

from __future__ import annotations

import time
import secrets
from urllib.parse import urlencode

import requests
from cachecontrol import CacheControl
from cachecontrol.cache import DictCache
from google.auth import exceptions as google_errors
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token

from api.auth.config import (
    AUTH_SCOPES,
    AUTHORIZE_URL,
    TOKEN_URL,
    client_id,
    client_secret,
    redirect_uri,
)


class GoogleAuthError(RuntimeError):
    """The Google consent flow did not produce a verified identity."""


def authorize_url(state: str, *, code_challenge: str, nonce: str) -> str:
    # Fail before consent if the server cannot complete the code exchange.
    client_secret()
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(AUTH_SCOPES),
        "prompt": "select_account",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


_CERT_CACHE = DictCache()


class BoundedCertificateRequest(GoogleRequest):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 10
        return super().__call__(*args, **kwargs)


def _verify_id_token(token: str) -> dict:
    # Only the verifier's public-certificate GETs use this in-memory cache.
    # Each call owns its session; cached keys honor Google's HTTP expiry policy.
    try:
        with requests.Session() as session:
            transport = BoundedCertificateRequest(CacheControl(session, cache=_CERT_CACHE))
            return google_id_token.verify_oauth2_token(token, transport, audience=client_id())
    except (google_errors.GoogleAuthError, requests.RequestException, ValueError, TypeError, KeyError):
        raise GoogleAuthError("Google could not verify this sign-in; try again.") from None


def exchange_code(code: str, *, code_verifier: str, expected_nonce: str) -> dict[str, str]:
    """Exchange the authorization code and verify the returned identity.

    Verify the JWT signature, claims, and nonce before using any identity fields.
    """
    data: dict[str, str] = {
        "client_id": client_id(),
        "client_secret": client_secret(),
        "code": code,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    }
    data["code_verifier"] = code_verifier
    token_payload = _google_payload(TOKEN_URL, data)
    id_token = str(token_payload.get("id_token", "") or "")
    if not id_token:
        raise GoogleAuthError("Google did not return an identity token.")
    claims = _verify_id_token(id_token)
    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not expected_nonce or not secrets.compare_digest(nonce.encode("utf-8"), expected_nonce.encode("utf-8")):
        raise GoogleAuthError("The Google identity does not match this sign-in attempt.")
    if claims.get("aud") != client_id():
        raise GoogleAuthError("Google returned an identity for another application.")
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleAuthError("Google returned an unexpected identity issuer.")
    try:
        expires_at = int(claims.get("exp", ""))
    except (TypeError, ValueError, OverflowError):
        raise GoogleAuthError("Google returned an invalid identity expiry.") from None
    if expires_at <= time.time():
        raise GoogleAuthError("The Google identity has expired; sign in again.")
    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str) or not sub.strip() or len(sub) > 255:
        raise GoogleAuthError("Google did not return a stable account id.")
    email_verified = claims.get("email_verified")
    if not isinstance(email, str) or not email.strip() or not (email_verified is True or email_verified == "true"):
        raise GoogleAuthError("Google did not return a verified email address.")
    return {
        "sub": sub,
        "user_id": f"google:{sub}",
        "email": email,
        "display_name": str(claims.get("name", "") or "").strip(),
        "avatar_url": str(claims.get("picture", "") or "").strip(),
    }


def _google_payload(url: str, data: dict[str, str]) -> dict:
    """Normalize provider outages and malformed responses into a safe failure."""
    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code != 200:
            raise GoogleAuthError("Google could not complete sign-in; try again.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise GoogleAuthError("Google returned an invalid sign-in response.")
        return payload
    except (requests.RequestException, ValueError):
        raise GoogleAuthError("Google sign-in is temporarily unavailable; try again.") from None


__all__ = [
    "GoogleAuthError",
    "authorize_url",
    "exchange_code",
]

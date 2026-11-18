"""FastAPI dependencies that turn the session cookie into an authenticated user."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, Request

from api.auth import config, sessions
from database import get_user


class AuthenticatedUser:
    """Resolved session identity. Never trusts a client-supplied user id."""

    __slots__ = ("user_id", "csrf_token", "email", "display_name", "avatar_url")

    def __init__(self, session_row: dict[str, str]) -> None:
        self.user_id = str(session_row["user_id"])
        self.csrf_token = str(session_row.get("csrf_token", "") or "")
        account = get_user(self.user_id) or {}
        self.email = str(account.get("email", "") or "")
        self.display_name = str(account.get("display_name", "") or "")
        self.avatar_url = str(account.get("avatar_url", "") or "")


def _cookie_token(request: Request) -> str:
    return str(request.cookies.get(config.session_cookie_name(), "") or "")


def optional_user(request: Request) -> AuthenticatedUser | None:
    """Resolve the session when a valid cookie is present, else ``None``."""
    row = sessions.resolve_session(_cookie_token(request))
    return AuthenticatedUser(row) if row is not None else None


def require_user(request: Request) -> AuthenticatedUser:
    user = optional_user(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Sign in to continue.",
        )
    return user


def require_user_and_csrf(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthenticatedUser:
    """Require a valid session AND a matching CSRF token for mutating calls."""
    user = require_user(request)
    expected = user.csrf_token
    if not expected or not x_csrf_token:
        raise HTTPException(status_code=403, detail="CSRF token is missing.")
    import hashlib

    provided = hashlib.sha256(str(x_csrf_token).encode("utf-8")).hexdigest()
    expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()
    import secrets
    if not secrets.compare_digest(provided, expected_hash):
        raise HTTPException(status_code=403, detail="CSRF token is invalid.")
    return user


def public_user_payload(user: AuthenticatedUser | None, csrf: str | None = None) -> dict[str, Any]:
    if user is None:
        return {"authenticated": False, "user": None, "csrf_token": None}
    return {
        "authenticated": True,
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        },
        "csrf_token": csrf if csrf is not None else user.csrf_token,
    }


__all__ = [
    "AuthenticatedUser",
    "optional_user",
    "public_user_payload",
    "require_user",
    "require_user_and_csrf",
]

"""Server-side session helpers for the auth flow.

Sessions are opaque bearer tokens. The database only stores a SHA-256 hash of
each token, so a database leak never exposes live sessions; the session row also
carries a per-session CSRF token used to protect state-changing requests.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from api.auth import config
from database import (
    create_session as _create_session,
    delete_session as _delete_session,
    get_session as _get_session,
    touch_session as _touch_session,
)

CSRF_HEADER = "X-CSRF-Token"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def create_login_session(user_id: str) -> tuple[str, str]:
    """Create a session and return ``(bearer_token, csrf_token)``."""
    from database import upsert_user  # deferred import keeps startup light

    upsert_user(user_id=user_id)
    token = new_token()
    csrf = new_csrf_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=config.session_days())
    _create_session(
        user_id=user_id,
        token_hash=hash_token(token),
        csrf_token=csrf,
        expires_at=expires_at,
    )
    return token, csrf


def resolve_session(token: str) -> dict[str, str] | None:
    if not token:
        return None
    row = _get_session(hash_token(token))
    if row is None:
        return None
    _touch_session(hash_token(token))
    return row


def delete_session(token: str) -> None:
    if token:
        _delete_session(hash_token(token))


__all__ = [
    "CSRF_HEADER",
    "create_login_session",
    "delete_session",
    "hash_token",
    "new_csrf_token",
    "new_token",
    "resolve_session",
]
"""App-login authentication settings (env-driven; never secrets in code).

Phase 6 uses a backend-run Google Sign-In that is completely separate from the
Gmail compose OAuth client: different OAuth client id/secret and only identity
scopes (``openid`` ``email`` ``profile``). Session tokens are opaque, hashed at
rest, delivered via an HTTP-only cookie, and valid for a fixed number of days.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlencode

AUTH_SCOPES = ("openid", "email", "profile")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

DEFAULT_DEV_EMAIL = "dev@localhost"


def _value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def app_mode() -> str:
    return os.getenv("APP_MODE", "local").strip().lower()


def client_id() -> str:
    value = _value("AUTH_CLIENT_ID")
    if not value:
        raise ConfigError(
            "AUTH_CLIENT_ID is not set. Add it to .env (see README Phase 6), "
            "or use the local developer sign-in for single-user development."
        )
    return value


def client_secret() -> str:
    value = _value("AUTH_CLIENT_SECRET")
    if not value:
        raise ConfigError(
            "AUTH_CLIENT_SECRET is not set. Add it to .env (see README Phase 6)."
        )
    return value


def redirect_uri() -> str:
    return _value("AUTH_REDIRECT_URI", "http://localhost:8000/api/auth/callback")


def login_success_url() -> str:
    return _value("AUTH_LOGIN_SUCCESS_URL", "http://localhost:3000/account")


def append_query(url: str, **params) -> str:
    """Attach query params to ``url``, replacing any existing same-name values."""
    base, _, query = url.partition("?")
    kept = [
        (key, value)
        for key, values in parse_qs(query, keep_blank_values=True).items()
        if key not in params
        for value in values
    ]
    kept.extend(params.items())
    return f"{base}?{urlencode(kept)}"


def login_success_redirect() -> str:
    return append_query(login_success_url(), auth="success")


def login_failure_url(reason: str) -> str:
    return append_query(login_success_url(), auth="error", reason=reason)


def session_cookie_name() -> str:
    return _value("AUTH_SESSION_COOKIE_NAME", "rmf_session")


def session_days() -> int:
    try:
        return max(1, int(os.getenv("AUTH_SESSION_DAYS", "14")))
    except ValueError:
        return 14


def cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "").strip().lower() == "true"


def dev_login_allowed() -> bool:
    """Permit developer login only when explicitly enabled in local mode."""
    return (
        app_mode() == "local"
        and os.getenv("AUTH_ALLOW_DEV_LOGIN", "").strip().lower() == "true"
    )


def dev_email() -> str:
    return _value("AUTH_DEV_EMAIL", DEFAULT_DEV_EMAIL)


def dev_user_id() -> str:
    return f"dev:{dev_email().casefold()}"


class ConfigError(RuntimeError):
    """Raised when app authentication is not configured (or misconfigured)."""


__all__ = [
    "AUTH_SCOPES",
    "AUTHORIZE_URL",
    "ConfigError",
    "TOKEN_URL",
    "TOKENINFO_URL",
    "client_id",
    "client_secret",
    "cookie_secure",
    "dev_email",
    "dev_login_allowed",
    "dev_user_id",
    "login_failure_url",
    "login_success_redirect",
    "login_success_url",
    "redirect_uri",
    "session_cookie_name",
    "session_days",
]

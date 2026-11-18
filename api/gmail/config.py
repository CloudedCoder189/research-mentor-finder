"""Gmail draft integration settings (env-driven; no secrets in code)."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from database import BASE_DIR

#: Narrowest Gmail OAuth scopes for draft creation plus reply detection.
#: ``gmail.compose`` manages drafts (and can send), but grants no mailbox read.
#: ``gmail.metadata`` reads only message metadata (labels, headers, timestamps)
#: — never bodies — which is exactly what sent/reply detection needs. Together
#: they stay far narrower than ``gmail.readonly``/``gmail.modify``.
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.metadata",
)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GMAIL_API_URL = "https://gmail.googleapis.com/gmail/v1"
GMAIL_DRAFTS_URL = "https://mail.google.com/mail/u/0/#drafts"


def client_id() -> str:
    value = os.getenv("GMAIL_CLIENT_ID", "").strip()
    if not value:
        raise ConfigError(
            "GMAIL_CLIENT_ID is not set. Add it to .env (see README Phase 5)."
        )
    return value


def client_secret() -> str:
    value = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
    if not value:
        raise ConfigError(
            "GMAIL_CLIENT_SECRET is not set. Add it to .env (see README Phase 5)."
        )
    return value


def redirect_uri() -> str:
    return os.getenv(
        "GMAIL_REDIRECT_URI", "http://localhost:8000/api/gmail/callback"
    ).strip()


def success_url() -> str:
    return os.getenv("GMAIL_REDIRECT_SUCCESS_URL", "http://localhost:3000/outreach").strip()


def append_query(url: str, **params) -> str:
    """Attach query params to ``url``, replacing any existing same-name values."""
    base, _, query = url.partition("?")
    kept = [
        (key, value)
        for key, value in parse_qs(query, keep_blank_values=True).items()
        if key not in params
    ]
    flattened = [(key, value) for key, values in kept for value in values]
    flattened.extend(params.items())
    return f"{base}?{urlencode(flattened)}"


def failure_url(reason: str) -> str:
    return append_query(success_url(), gmail="auth_error", reason=reason)


def token_dir() -> Path:
    return Path(os.getenv("GMAIL_TOKEN_DIR", BASE_DIR / "data" / "gmail_tokens"))


class ConfigError(RuntimeError):
    """Raised when Google OAuth is not configured (or misconfigured)."""


__all__ = [
    "AUTHORIZE_URL",
    "ConfigError",
    "GMAIL_API_URL",
    "GMAIL_DRAFTS_URL",
    "GMAIL_SCOPES",
    "REVOKE_URL",
    "TOKEN_URL",
    "client_id",
    "client_secret",
    "failure_url",
    "redirect_uri",
    "success_url",
    "token_dir",
]
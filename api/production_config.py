"""Reject unsafe non-local configuration without opening stores or logging secrets."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

from api.auth.config import ConfigError, app_mode, cookie_secure


def _public_https(value: str, *, origin_only: bool = False) -> bool:
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        port = url.port
    except ValueError:
        return False
    if (url.scheme != "https" or not host or url.username or url.password
            or url.query or url.fragment or "*" in host):
        return False
    if host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        return False
    try:
        if not ipaddress.ip_address(host).is_global:
            return False
    except ValueError:
        pass
    return not origin_only or (url.path in ("", "/") and port in (None, 443))


def validate_production_config() -> None:
    if app_mode() == "local":
        return
    errors = []
    if app_mode() not in {"public", "production", "staging"}:
        errors.append("APP_MODE must be local, public, production, or staging")
    if os.getenv("AUTH_ALLOW_DEV_LOGIN", "").strip().lower() == "true":
        errors.append("AUTH_ALLOW_DEV_LOGIN must not be true outside local mode")
    if not cookie_secure():
        errors.append("AUTH_COOKIE_SECURE must be true")
    for key in ("AUTH_CLIENT_ID", "AUTH_CLIENT_SECRET"):
        if not os.getenv(key, "").strip():
            errors.append(f"{key} must be configured")
    for key, path in (("AUTH_REDIRECT_URI", "/api/auth/callback"),
                      ("AUTH_LOGIN_SUCCESS_URL", "/account")):
        value = os.getenv(key, "").strip()
        if not _public_https(value) or urlsplit(value).path != path:
            errors.append(f"{key} must be a public HTTPS URL ending in {path}")
    origins = [v.strip() for v in os.getenv("CORS_ORIGINS", "").split(",") if v.strip()]
    if not origins or not all(_public_https(v, origin_only=True) for v in origins):
        errors.append("CORS_ORIGINS must contain explicit public HTTPS origins")
    if not Path(os.getenv("PROFESSOR_DB_PATH", "")).is_absolute():
        errors.append("PROFESSOR_DB_PATH must be an explicit absolute persistent path")
    # Request/token quotas are not dollar budgets. Keep paid work disabled until
    # deployment-wide spending enforcement exists.
    if os.getenv("AI_EXPLANATIONS", "").strip().lower() not in {"0", "false", "off", "no"}:
        errors.append("AI_EXPLANATIONS must be explicitly disabled for public deployment")
    if os.getenv("GMAIL_CLIENT_ID", "").strip() or os.getenv("GMAIL_CLIENT_SECRET", "").strip():
        for key in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_TOKEN_ENCRYPTION_KEY"):
            if not os.getenv(key, "").strip():
                errors.append(f"{key} is required when Gmail is configured")
        if not Path(os.getenv("GMAIL_TOKEN_DIR", "")).is_absolute():
            errors.append("GMAIL_TOKEN_DIR must be an explicit absolute persistent path")
        for key, path in (("GMAIL_REDIRECT_URI", "/api/gmail/callback"),
                          ("GMAIL_REDIRECT_SUCCESS_URL", "/outreach")):
            value = os.getenv(key, "").strip()
            if not _public_https(value) or urlsplit(value).path != path:
                errors.append(f"{key} must be a public HTTPS URL ending in {path}")
        if os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip():
            try:
                from cryptography.fernet import Fernet
                Fernet(os.environ["GMAIL_TOKEN_ENCRYPTION_KEY"].strip().encode("ascii"))
            except (ImportError, ValueError, UnicodeError):
                errors.append("Gmail encryption requires cryptography and a valid Fernet key")
    if errors:
        raise ConfigError("Unsafe deployment configuration: " + "; ".join(errors))

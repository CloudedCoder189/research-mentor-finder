"""Models for the Phase 6 authentication endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class AuthUser(BaseModel):
    user_id: str
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""


class AuthStatus(BaseModel):
    authenticated: bool
    user: AuthUser | None = None
    csrf_token: str | None = None
    dev_login_available: bool = False
    local_import_available: bool = False


class LogoutResponse(BaseModel):
    ok: bool = True


class ImportLocalResponse(BaseModel):
    imported_outreach_rows: int = 0
    imported_gmail_tokens: bool = False
    already_imported: bool = False


__all__ = [
    "AuthStatus",
    "AuthUser",
    "ImportLocalResponse",
    "LogoutResponse",
]
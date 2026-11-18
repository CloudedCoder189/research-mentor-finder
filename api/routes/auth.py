"""HTTP surface for Phase 6 authentication and local-data import."""

from __future__ import annotations

import shutil
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from api.auth import config, google_oauth, login_attempts, sessions as session_service
from api.auth.dependencies import (
    AuthenticatedUser,
    optional_user,
    require_user_and_csrf,
)
from api.gmail import token_store
from api.auth import account_deletion
from pydantic import BaseModel, ConfigDict
from typing import Literal
from api.schemas.auth import AuthStatus, ImportLocalResponse, LogoutResponse
from database import (
    DEFAULT_USER_ID,
    import_local_owner_outreach,
    local_owner_import_marker,
    local_owner_outreach_exists,
    upsert_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "rmf_oauth_state"


def _set_session_cookie(response, token: str, *, clear: bool = False) -> None:
    kwargs = {
        "key": config.session_cookie_name(),
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": config.cookie_secure(),
    }
    if clear:
        response.delete_cookie(**kwargs)
    else:
        response.set_cookie(value=token, max_age=config.session_days() * 86400, **kwargs)


def _set_oauth_state_cookie(response, state: str, *, clear: bool = False) -> None:
    kwargs = {
        "key": OAUTH_STATE_COOKIE,
        "path": "/api/auth/callback",
        "httponly": True,
        "samesite": "lax",
        "secure": config.cookie_secure(),
    }
    if clear:
        response.delete_cookie(**kwargs)
    else:
        response.set_cookie(value=state, max_age=600, **kwargs)


def _status_payload(request: Request) -> AuthStatus:
    user = optional_user(request)
    return AuthStatus(
        authenticated=user is not None,
        user={
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
        }
        if user is not None
        else None,
        csrf_token=user.csrf_token if user is not None else None,
        dev_login_available=config.dev_login_allowed(),
        local_import_available=bool(user and config.app_mode() == "local" and user.user_id == config.dev_user_id()),
    )


@router.get("/me", response_model=AuthStatus)
def auth_status(request: Request) -> AuthStatus:
    return _status_payload(request)


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    """Redirect to Google's consent screen (identity scopes only)."""
    try:
        config.client_id()
        config.client_secret()
        user = optional_user(request)
        state, challenge, nonce = login_attempts.begin(user.user_id if user else None)
        url = google_oauth.authorize_url(state, code_challenge=challenge, nonce=nonce)
    except config.ConfigError:
        return RedirectResponse(config.login_failure_url("config"), status_code=307)
    except login_attempts.LoginBusyError:
        return RedirectResponse(config.login_failure_url("unavailable"), status_code=307)
    response = RedirectResponse(url, status_code=307)
    _set_oauth_state_cookie(response, state)
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    def failure(reason):
        response = RedirectResponse(config.login_failure_url(reason), status_code=307)
        _set_oauth_state_cookie(response, "", clear=True)
        return response

    expected = str(request.cookies.get(OAUTH_STATE_COOKIE, "") or "")
    if not state or not expected or not secrets.compare_digest(state.encode("utf-8"), expected.encode("utf-8")):
        return failure("denied" if error else "state")
    attempt = login_attempts.consume(state)
    if not attempt:
        return failure("state")
    if error:
        return failure("denied")
    if not code:
        return failure("state")
    try:
        identity = google_oauth.exchange_code(code, code_verifier=attempt["verifier"], expected_nonce=attempt["nonce"])
        upsert_user(
            user_id=identity["user_id"],
            email=identity["email"],
            display_name=identity["display_name"],
            avatar_url=identity["avatar_url"],
        )
        token, _ = session_service.create_login_session(identity["user_id"])
        previous_token = str(request.cookies.get(config.session_cookie_name(), "") or "")
        if previous_token:
            session_service.delete_session(previous_token)
    except google_oauth.GoogleAuthError:
        return failure("verification")
    except config.ConfigError:
        return failure("config")
    response = RedirectResponse(
        config.login_success_redirect(), status_code=307
    )
    _set_session_cookie(response, token)
    _set_oauth_state_cookie(response, "", clear=True)
    return response


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request, _user: AuthenticatedUser = Depends(require_user_and_csrf)):
    from fastapi.responses import JSONResponse

    token = str(request.cookies.get(config.session_cookie_name(), "") or "")
    session_service.delete_session(token)
    response = JSONResponse(content={"ok": True})
    _set_session_cookie(response, "", clear=True)
    return response


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["DELETE"]
    expected_user_id: str


@router.delete("/account")
def delete_account(payload: DeleteAccountRequest, user: AuthenticatedUser = Depends(require_user_and_csrf)):
    from fastapi.responses import JSONResponse

    if payload.expected_user_id != user.user_id:
        raise HTTPException(status_code=409, detail="The signed-in account changed. Reload before deleting.")
    try:
        result = account_deletion.delete_account(user.user_id)
    except account_deletion.DeletionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    response = JSONResponse(result)
    _set_session_cookie(response, "", clear=True)
    _set_oauth_state_cookie(response, "", clear=True)
    return response


@router.post("/dev-login", response_model=AuthStatus)
def dev_login() -> AuthStatus:
    """Local developer sign-in; identity comes from server env, never the client."""
    if not config.dev_login_allowed():
        raise HTTPException(status_code=404, detail="Developer sign-in is disabled.")
    from fastapi.responses import JSONResponse

    user_id = config.dev_user_id()
    upsert_user(user_id=user_id, email=config.dev_email(), display_name="Local developer")
    token, csrf = session_service.create_login_session(user_id)
    response = JSONResponse(
        content={
            "authenticated": True,
            "user": {
                "user_id": user_id,
                "email": config.dev_email(),
                "display_name": "Local developer",
                "avatar_url": "",
            },
            "csrf_token": csrf,
            "dev_login_available": True,
            "local_import_available": True,
        }
    )
    _set_session_cookie(response, token)
    return response


def _import_gmail_tokens(user_id: str) -> bool:
    """Move local-owner credentials to an account exactly once (opt-in)."""
    source = token_store.credentials_path(DEFAULT_USER_ID)
    destination = token_store.credentials_path(user_id)
    if not source.is_file():
        return False
    if token_store.has_credentials(user_id):
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, destination)
        source.unlink()
        pending_source = token_store.pending_path(DEFAULT_USER_ID)
        if pending_source.is_file():
            shutil.copy2(pending_source, token_store.pending_path(user_id))
            pending_source.unlink()
        return True
    except OSError:
        return False


@router.post("/import-local", response_model=ImportLocalResponse)
def import_local(user: AuthenticatedUser = Depends(require_user_and_csrf)) -> ImportLocalResponse:
    """Opt-in one-time import of pre-auth local-owner data to this account."""
    # Legacy data has no account ownership. Never let a remote first caller claim
    # it; only the configured local developer account may perform this migration.
    if config.app_mode() != "local" or user.user_id != config.dev_user_id():
        raise HTTPException(status_code=403, detail="Local data import is restricted to the local owner account.")
    marker = local_owner_import_marker()
    already = bool(marker)
    if already and marker != user.user_id:
        raise HTTPException(
            status_code=409,
            detail="Local data was already imported by a different account.",
        )
    if not already and local_owner_outreach_exists() == 0 and not token_store.has_credentials(
        DEFAULT_USER_ID
    ):
        return ImportLocalResponse(already_imported=True)
    try:
        imported_rows = 0 if already else import_local_owner_outreach(target_user_id=user.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    tokens_moved = False if already else _import_gmail_tokens(user.user_id)
    return ImportLocalResponse(
        imported_outreach_rows=imported_rows,
        imported_gmail_tokens=tokens_moved,
        already_imported=already,
    )


__all__ = ["router"]

"""HTTP surface for the Gmail draft integration (per authenticated user)."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from api.auth.dependencies import (
    AuthenticatedUser,
    optional_user,
    require_user,
    require_user_and_csrf,
)
from api.gmail import service, sync
from api.gmail.config import ConfigError, failure_url
from api.gmail.oauth import GmailApiError, GmailAuthError
from api.gmail.service import DraftMissingError
from api.gmail.drafts import RecipientError
from api.gmail.threads import ThreadNotFoundError
from api.schemas.gmail import (
    FollowUpDraftResult,
    GmailConnectResponse,
    GmailDisconnectResponse,
    GmailDraftRequest,
    GmailDraftResult,
    GmailStatus,
    GmailSyncAllResult,
    GmailSyncResult,
)

router = APIRouter(tags=["gmail"])


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, ConfigError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, GmailAuthError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, RecipientError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, (DraftMissingError, ThreadNotFoundError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, GmailApiError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/api/gmail/status", response_model=GmailStatus)
def gmail_status(_user: AuthenticatedUser = Depends(require_user)) -> GmailStatus:
    return service.status(_user.user_id)


@router.get("/api/gmail/connect", response_model=GmailConnectResponse)
def gmail_connect(_user: AuthenticatedUser = Depends(require_user)) -> GmailConnectResponse:
    try:
        return service.begin_connect(_user.user_id)
    except Exception as exc:
        _raise(exc)


@router.get("/api/gmail/callback")
def gmail_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    user = optional_user(request)
    if user is None:
        return RedirectResponse(failure_url("auth"), status_code=302)
    try:
        url = service.handle_callback(
            code=code,
            state=state or "",
            error=error,
            user_id=user.user_id,
        )
        return RedirectResponse(url, status_code=302)
    except GmailAuthError as exc:
        return RedirectResponse(failure_url("denied"), status_code=302)
    except Exception as exc:  # noqa: BLE001 - any OAuth failure redirects back
        return RedirectResponse(failure_url("error"), status_code=302)


@router.post("/api/gmail/disconnect", response_model=GmailDisconnectResponse)
def gmail_disconnect(_user: AuthenticatedUser = Depends(require_user_and_csrf)) -> GmailDisconnectResponse:
    try:
        revocation = service.disconnect(_user.user_id)
    except Exception as exc:
        _raise(exc)
    return GmailDisconnectResponse(disconnected=True, revocation=revocation)


@router.post("/api/outreach/{professor_id}/gmail-draft", response_model=GmailDraftResult)
def outreach_create_gmail_draft(
    professor_id: int,
    request: GmailDraftRequest,
    _user: AuthenticatedUser = Depends(require_user_and_csrf),
) -> GmailDraftResult:
    try:
        return service.create_gmail_draft(professor_id, request, _user.user_id)
    except Exception as exc:
        _raise(exc)


@router.patch("/api/outreach/{professor_id}/gmail-draft", response_model=GmailDraftResult)
def outreach_update_gmail_draft(
    professor_id: int,
    request: GmailDraftRequest,
    _user: AuthenticatedUser = Depends(require_user_and_csrf),
) -> GmailDraftResult:
    try:
        return service.update_gmail_draft(professor_id, request, _user.user_id)
    except Exception as exc:
        _raise(exc)


@router.post(
    "/api/outreach/{professor_id}/gmail-sync",
    response_model=GmailSyncResult,
    summary="Check one outreach record against Gmail and update thread state",
)
def outreach_gmail_sync_one(
    professor_id: int,
    _user: AuthenticatedUser = Depends(require_user_and_csrf),
) -> GmailSyncResult:
    try:
        return sync.sync_one(professor_id, user_id=_user.user_id)
    except Exception as exc:
        _raise(exc)


@router.post(
    "/api/outreach/gmail-sync",
    response_model=GmailSyncAllResult,
    summary="Check every linked outreach record against Gmail",
)
def outreach_gmail_sync_all(
    _user: AuthenticatedUser = Depends(require_user_and_csrf),
) -> GmailSyncAllResult:
    return sync.sync_all(user_id=_user.user_id)


@router.post(
    "/api/outreach/{professor_id}/follow-up-draft",
    response_model=FollowUpDraftResult,
    summary="Generate a grounded follow-up draft for a sent outreach email",
)
def outreach_follow_up_draft(
    professor_id: int,
    _user: AuthenticatedUser = Depends(require_user_and_csrf),
) -> FollowUpDraftResult:
    try:
        return sync.build_follow_up_draft(professor_id, user_id=_user.user_id)
    except Exception as exc:
        _raise(exc)

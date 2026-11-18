"""Private per-user state routes: saved researchers and outreach workflow."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from api.auth.dependencies import (
    AuthenticatedUser,
    require_user,
    require_user_and_csrf,
)
from api.schemas.user_state import (
    MutationResult,
    OutreachListResponse,
    OutreachResult,
    OutreachUpdate,
    SavedListResponse,
)
from api.services import (
    get_outreach_item,
    list_outreach,
    list_saved,
    set_saved,
    update_outreach,
)

router = APIRouter(prefix="/api", tags=["user-state"])


def _raise_for_exc(exc: ValueError) -> NoReturn:
    message = str(exc)
    if "not found" in message.casefold():
        raise HTTPException(status_code=404, detail="Researcher not found")
    raise HTTPException(status_code=422, detail=message)


@router.get(
    "/saved",
    response_model=SavedListResponse,
    summary="List saved researchers with outreach state",
)
def get_saved(_user: AuthenticatedUser = Depends(require_user)) -> SavedListResponse:
    return list_saved(user_id=_user.user_id)


@router.post(
    "/saved/{professor_id}",
    response_model=MutationResult,
    summary="Save a researcher to the shortlist",
)
def add_saved(professor_id: int, _user: AuthenticatedUser = Depends(require_user_and_csrf)) -> MutationResult:
    try:
        return set_saved(professor_id, True, user_id=_user.user_id)
    except ValueError as exc:
        return _raise_for_exc(exc)


@router.delete(
    "/saved/{professor_id}",
    response_model=MutationResult,
    summary="Remove a researcher from the shortlist",
)
def remove_saved(professor_id: int, _user: AuthenticatedUser = Depends(require_user_and_csrf)) -> MutationResult:
    try:
        return set_saved(professor_id, False, user_id=_user.user_id)
    except ValueError as exc:
        return _raise_for_exc(exc)


@router.get(
    "/outreach",
    response_model=OutreachListResponse,
    summary="List tracked outreach rows",
)
def get_outreach(_user: AuthenticatedUser = Depends(require_user)) -> OutreachListResponse:
    return list_outreach(user_id=_user.user_id)


@router.get(
    "/outreach/{professor_id}",
    response_model=OutreachResult,
    summary="Get outreach state for one researcher",
)
def get_outreach_one(professor_id: int, _user: AuthenticatedUser = Depends(require_user)) -> OutreachResult:
    result = get_outreach_item(professor_id, user_id=_user.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Researcher not found")
    return result


@router.patch(
    "/outreach/{professor_id}",
    response_model=OutreachResult,
    summary="Update selected outreach fields for one researcher",
)
def patch_outreach(
    professor_id: int, update: OutreachUpdate, _user: AuthenticatedUser = Depends(require_user_and_csrf)
) -> OutreachResult:
    if update.expected_user_id is not None and update.expected_user_id != _user.user_id:
        raise HTTPException(status_code=409, detail="Your account changed. Reload before saving.")
    try:
        return update_outreach(professor_id, update, user_id=_user.user_id)
    except ValueError as exc:
        return _raise_for_exc(exc)

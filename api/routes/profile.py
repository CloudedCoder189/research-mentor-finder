"""Authenticated, per-user student profile endpoints (Phase 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth.dependencies import (
    AuthenticatedUser,
    require_user,
    require_user_and_csrf,
)
from api.schemas.profile import StudentProfileDto, StudentProfileUpdate
from database import get_student_profile, save_student_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])

EDUCATION_LEVELS = {"unspecified", "high_school", "college", "university", "graduate"}


def _dto(row: dict) -> StudentProfileDto:
    return StudentProfileDto(
        interests=row["interests"],
        interest_text=row["interest_text"],
        skills=row["skills"],
        experience=row["experience"],
        coursework=row["coursework"],
        education_level=row["education_level"],
        preferences=row["preferences"],
        completed=row["completed"],
        updated_at=row["updated_at"],
    )


def _empty_dto(user_id: str) -> StudentProfileDto:
    return StudentProfileDto()


@router.get("", response_model=StudentProfileDto)
def get_profile(user: AuthenticatedUser = Depends(require_user)) -> StudentProfileDto:
    row = get_student_profile(user.user_id)
    return _dto(row) if row is not None else _empty_dto(user.user_id)


@router.put("", response_model=StudentProfileDto)
def put_profile(update: StudentProfileUpdate, user: AuthenticatedUser = Depends(require_user_and_csrf)) -> StudentProfileDto:
    if update.expected_user_id is not None and update.expected_user_id != user.user_id:
        raise HTTPException(status_code=409, detail="The signed-in account changed. Reload before saving this profile.")
    level = (update.education_level or "unspecified").strip().lower()
    if level not in EDUCATION_LEVELS:
        raise HTTPException(
            status_code=422,
            detail="Choose a valid education level.",
        )
    # A completed profile requires at least one interest: the UI states that
    # interests are required, and recommendations cannot be built without them.
    # In-progress drafts (completed=False) stay allowed because the onboarding
    # form saves each chip toggle as it happens.
    if update.completed:
        interests = [value.strip() for value in update.interests if value.strip()]
        if not interests:
            raise HTTPException(
                status_code=422,
                detail="Select at least one interest to complete your profile.",
            )
    row = save_student_profile(
        user.user_id,
        interests=update.interests,
        interest_text=update.interest_text,
        skills=update.skills,
        experience=update.experience,
        coursework=update.coursework,
        education_level=level,
        preferences={
            "locations": update.preferences.locations,
            "university_types": update.preferences.university_types,
            "support_level": update.preferences.support_level,
            "remote_ok": update.preferences.remote_ok,
        },
        completed=update.completed,
    )
    return _dto(row)


__all__ = ["router"]

"""Models for the authenticated, per-user student profile."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfilePreferences(BaseModel):
    locations: list[str] = Field(default_factory=list)
    university_types: list[str] = Field(default_factory=list)
    support_level: str = ""
    remote_ok: bool = False


class StudentProfileUpdate(BaseModel):
    expected_user_id: str | None = Field(default=None, max_length=300)
    interests: list[str] = Field(default_factory=list, max_length=100)
    interest_text: str = Field(default="", max_length=3000)
    skills: list[str] = Field(default_factory=list, max_length=200)
    experience: list[str] = Field(default_factory=list, max_length=200)
    coursework: list[str] = Field(default_factory=list, max_length=200)
    education_level: str = Field(default="unspecified", max_length=50)
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)
    completed: bool = False


class StudentProfileDto(BaseModel):
    interests: list[str] = Field(default_factory=list)
    interest_text: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    education_level: str = "unspecified"
    preferences: ProfilePreferences = Field(default_factory=ProfilePreferences)
    completed: bool = False
    updated_at: str = ""


__all__ = [
    "ProfilePreferences",
    "StudentProfileDto",
    "StudentProfileUpdate",
]

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from services.ui_helpers import joint_affiliation_values, topic_values
from services.reviewed_directory import reviewed_record

NOT_AVAILABLE = "Not publicly available"


def _clean(value: Any) -> str:
    cleaned = str(value or "").strip()
    return cleaned if cleaned and cleaned != NOT_AVAILABLE else ""


class MatchDetail(BaseModel):
    score: float
    keyword_score: float
    semantic_score: float
    mode: str
    reason: str
    strength: str


def _strength_for(score: float) -> str:
    if score >= 80:
        return "Strong match"
    if score >= 55:
        return "Related match"
    return "Possible match"


class ResearcherSummary(BaseModel):
    id: int
    name: str
    university: str
    department: str
    title: str
    city: str
    state: str
    field: str
    # Broad academic area the field belongs to. Published so client-side
    # filtering can apply the same broad-category matching the API uses
    # (see services.ui_helpers.field_filter_matches) instead of comparing
    # only exact field labels.
    discipline: str = ""
    affiliation_fields: list[str] = Field(default_factory=list)
    affiliation_disciplines: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    research_interests: str
    ai_summary: str
    email: str
    verification_status: str
    opportunity_level: str
    data_source_url: str


class MatchRow(BaseModel):
    """A search result row: a researcher plus the match detail for the query."""

    researcher: ResearcherSummary
    match: MatchDetail | None = None

    def researcher_id(self) -> int:
        return self.researcher.id


class SearchResponse(BaseModel):
    query: str
    mode: str
    semantic_cached: bool = False
    total: int
    offset: int
    limit: int
    results: list[MatchRow]
    fallback_message: str = ""


class ProfessorProfile(BaseModel):
    researcher: ResearcherSummary
    department_category: str
    website_url: str
    website_status_label: str
    website_status_detail: str
    website_checked_at: str
    profile_url: str
    verification_issues: str
    verified_at: str
    last_checked_at: str
    opportunity_signals: str
    opportunity_source_url: str
    source_type: str


class OptionsResponse(BaseModel):
    universities: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    department_categories: list[str] = Field(default_factory=list)
    verification_statuses: list[str] = Field(default_factory=list)
    opportunity_signals: list[str] = Field(default_factory=list)
    total_researchers: int = 0


def _website_status_label(status: str) -> str:
    status = str(status or "").strip()
    if not status or status == "Not checked":
        return "Not checked"
    if "verified" in status.casefold():
        return "Verified"
    if any(
        token in status.casefold()
        for token in (
            "failed",
            "blocked",
            "rejected",
            "identity mismatch",
            "unavailable",
            "could not",
        )
    ):
        return "Broken"
    if status == "Not provided":
        return "Not checked"
    return "Review"


def summary_dto(record: dict[str, Any]) -> ResearcherSummary:
    """Build the public researcher summary, never leaking internal fields."""
    record = reviewed_record(record)
    affiliation_fields, affiliation_disciplines = joint_affiliation_values(record)
    return ResearcherSummary(
        id=int(record.get("id", 0)),
        name=str(record.get("name", "")).strip(),
        university=str(record.get("university", "")).strip(),
        department=str(record.get("department", "")).strip(),
        title=str(record.get("title", "")).strip(),
        city=str(record.get("city", "")).strip(),
        state=str(record.get("state", "")).strip(),
        field=str(record.get("field", "")).strip(),
        discipline=str(record.get("discipline", "")).strip(),
        affiliation_fields=affiliation_fields,
        affiliation_disciplines=affiliation_disciplines,
        topics=topic_values(record, limit=8),
        research_interests=str(record.get("research_interests", "")).strip(),
        ai_summary=str(record.get("ai_summary", "")).strip(),
        email=str(record.get("email", "")).strip(),
        verification_status=str(record.get("verification_status", "Not checked")),
        opportunity_level=str(record.get("opportunity_level", "Basic")),
        data_source_url=_clean(record.get("data_source_url")),
    )


def match_detail_dto(item: dict[str, Any]) -> MatchDetail:
    score = float(item.get("match_score", 0.0))
    return MatchDetail(
        score=score,
        keyword_score=float(item.get("keyword_score", 0.0)),
        semantic_score=float(item.get("semantic_score", 0.0)),
        mode=str(item.get("search_mode", "Keyword")),
        reason=str(item.get("match_reason", "")).strip(),
        strength=_strength_for(score),
    )


def profile_dto(record: dict[str, Any]) -> ProfessorProfile:
    record = reviewed_record(record)
    website_detail = str(record.get("website_status", "Not checked")).strip()
    return ProfessorProfile(
        researcher=summary_dto(record),
        department_category=str(record.get("department_category", "")).strip(),
        website_url=_clean(record.get("website_url")),
        website_status_label=_website_status_label(website_detail),
        website_status_detail=website_detail,
        website_checked_at=str(record.get("website_checked_at", "")).strip(),
        profile_url=_clean(record.get("profile_url")),
        verification_issues=str(record.get("verification_issues", "")).strip(),
        verified_at=str(record.get("verified_at", "")).strip(),
        last_checked_at=str(record.get("last_checked_at", "")).strip(),
        opportunity_signals=str(record.get("opportunity_signals", "")).strip(),
        opportunity_source_url=_clean(record.get("opportunity_source_url")),
        source_type=str(record.get("source_type", "")).strip(),
    )

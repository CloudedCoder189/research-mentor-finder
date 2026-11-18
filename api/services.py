from __future__ import annotations

from datetime import datetime, timezone

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from api.dependencies.filters import apply_filters, unified_university
from api.schemas.recommendations import (
    RecommendationResponse,
    recommendation_row_dto,
)
from api.schemas.researcher import (
    ProfessorProfile,
    MatchRow,
    SearchResponse,
    match_detail_dto,
    profile_dto,
    summary_dto,
)
from api.schemas.user_state import (
    STORED_STATUS_BY_FRONTEND,
    MutationResult,
    OutreachListResponse,
    OutreachResult,
    OutreachUpdate,
    SavedListResponse,
    outreach_result_dto,
)
from database import (
    fetch_outreach_professors,
    fetch_professors,
    get_professor_outreach,
    set_professor_favorite,
    update_professor_outreach,
)
from services.ai_enrichment import query_embedding_with_source, text_model_name
from services.ai_explanation import MAX_RANKED_FOR_AI, generate_reasons
from services.recommendations import (
    build_profile_query,
    recommend_from_profile,
    score_for_profile,
)
from services.search import rank_professors
from services.reviewed_directory import discovery_candidate, reviewed_record
from services.ui_helpers import resolve_search_query


ProfileTerm = Annotated[str, StringConstraints(max_length=200)]
ExperienceTerm = Annotated[str, StringConstraints(max_length=2000)]


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=300)
    topics: list[ProfileTerm] = Field(default_factory=list, max_length=100)
    university: str = ""
    state: str = ""
    field: str = ""
    department_category: str = ""
    verification: str = ""
    opportunity: str = ""
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class BrowseRequest(BaseModel):
    university: str = ""
    state: str = ""
    field: str = ""
    department_category: str = ""
    verification: str = ""
    opportunity: str = ""
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class RecommendationFilters(BaseModel):
    university: str = ""
    state: str = ""
    field: str = ""
    department_category: str = ""
    verification: str = ""
    opportunity: str = ""


class PreferencesInput(BaseModel):
    locations: list[ProfileTerm] = Field(default_factory=list, max_length=50)
    remote_ok: bool = False


class StudentProfileInput(BaseModel):
    """Stateless profile, bounded before expensive directory scoring begins."""

    interests: list[ProfileTerm] = Field(min_length=1, max_length=100)
    interest_text: str = Field(default="", max_length=3000)
    skills: list[ProfileTerm] = Field(default_factory=list, max_length=200)
    experience: list[ExperienceTerm] = Field(default_factory=list, max_length=200)
    coursework: list[ProfileTerm] = Field(default_factory=list, max_length=200)
    preferences: PreferencesInput = Field(default_factory=PreferencesInput)

    @field_validator("interests")
    @classmethod
    def require_nonblank_interests(cls, values: list[str]) -> list[str]:
        interests = [value.strip() for value in values if value.strip()]
        if not interests:
            raise ValueError("Select at least one interest.")
        return interests


class RecommendationsRequest(BaseModel):
    profile: StudentProfileInput
    filters: RecommendationFilters = Field(default_factory=RecommendationFilters)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class ExplainRequest(BaseModel):
    profile: StudentProfileInput
    researcher_id: int = Field(gt=0)
    include_ai: bool = False


def _load_and_filter(
    *,
    university: str | None,
    state: str = "",
    field: str = "",
    department_category: str = "",
    verification: str = "",
    opportunity: str = "",
    topics: list[str] | None = None,
) -> list[dict]:
    records = [reviewed_record(record) for record in fetch_professors(university)
               if discovery_candidate(record)]
    return apply_filters(
        records,
        state=state,
        field=field,
        department_category=department_category,
        verification=verification,
        opportunity=opportunity,
        topics=topics,
    )


def browse_records(request: BrowseRequest) -> SearchResponse:
    candidates = _load_and_filter(
        university=unified_university(request.university),
        state=request.state,
        field=request.field,
        department_category=request.department_category,
        verification=request.verification,
        opportunity=request.opportunity,
    )
    ordered = sorted(
        candidates,
        key=lambda record: (
            str(record.get("university", "")),
            str(record.get("name", "")).casefold(),
        ),
    )
    total = len(ordered)
    page = ordered[request.offset : request.offset + request.limit]
    rows = [MatchRow(researcher=summary_dto(record), match=None) for record in page]
    return SearchResponse(
        query="",
        mode="Browse",
        semantic_cached=False,
        total=total,
        offset=request.offset,
        limit=request.limit,
        results=rows,
    )


def search_records(request: SearchRequest) -> SearchResponse:
    effective_query = resolve_search_query(request.query, request.topics)
    candidates = _load_and_filter(
        university=unified_university(request.university),
        state=request.state,
        field=request.field,
        department_category=request.department_category,
        verification=request.verification,
        opportunity=request.opportunity,
        topics=request.topics,
    )

    if not effective_query:
        browse = BrowseRequest(**request.model_dump(exclude={"query", "topics"}))
        return browse_records(browse)

    query_vector = None
    try:
        query_vector, _ = query_embedding_with_source(
            effective_query, allow_api=False
        )
    except RuntimeError:
        pass

    ranked = rank_professors(
        candidates,
        effective_query,
        limit=None,
        query_embedding=query_vector,
    )
    rows = [
        MatchRow(researcher=summary_dto(item), match=match_detail_dto(item))
        for item in ranked
    ]
    total = len(rows)
    page = rows[request.offset : request.offset + request.limit]

    mode = "AI semantic + keyword" if query_vector is not None else "Keyword"
    fallback_message = ""
    if query_vector is None:
        fallback_message = (
            "No stored semantic vector was available for this query, "
            "so keyword ranking was used."
        )

    return SearchResponse(
        query=effective_query,
        mode=mode,
        semantic_cached=query_vector is not None,
        total=total,
        offset=request.offset,
        limit=request.limit,
        results=page,
        fallback_message=fallback_message,
    )


def fetch_profile(professor_id: int) -> ProfessorProfile | None:
    records = fetch_professors(omit_embeddings=True)
    for record in records:
        if int(record.get("id", -1)) == professor_id:
            return profile_dto(reviewed_record(record))
    return None


def _profile_payload(profile: StudentProfileInput) -> dict:
    return {
        "interests": profile.interests,
        "interest_text": profile.interest_text,
        "skills": profile.skills,
        "experience": profile.experience,
        "coursework": profile.coursework,
        "preferences": {
            "locations": profile.preferences.locations,
            "remote_ok": profile.preferences.remote_ok,
        },
    }


def _query_vector_or_none(query: str) -> tuple[tuple[float, ...] | None, str]:
    try:
        vector, _ = query_embedding_with_source(query, allow_api=False)
        return vector, ""
    except RuntimeError:
        return None, (
            "No stored semantic vector was available for this profile query, "
            "so keyword-based ranking was used."
        )


def recommend_records(request: RecommendationsRequest) -> RecommendationResponse:
    candidates = _load_and_filter(
        university=unified_university(request.filters.university),
        state=request.filters.state,
        field=request.filters.field,
        department_category=request.filters.department_category,
        verification=request.filters.verification,
        opportunity=request.filters.opportunity,
    )

    payload = _profile_payload(request.profile)
    query = build_profile_query(payload)
    query_vector, fallback_message = _query_vector_or_none(query)

    page, built_query, semantic_used, total = recommend_from_profile(
        candidates,
        payload,
        limit=request.limit,
        offset=request.offset,
        query_embedding=query_vector,
    )

    rows = [
        recommendation_row_dto(item["record"], item["match"]) for item in page
    ]
    return RecommendationResponse(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        query=built_query,
        mode="AI semantic + keyword" if semantic_used else "Keyword",
        semantic_cached=semantic_used,
        total=total,
        offset=request.offset,
        limit=request.limit,
        results=rows,
        fallback_message=fallback_message,
    )


def _attach_ai_explanation(
    record: dict,
    payload: dict,
    match: dict,
    candidates: list[dict],
) -> None:
    """Add optional AI wording to one match.

    Explanation-only by construction: the record is already fixed by the caller,
    the score and label above are untouched, and the deterministic ranking
    decides who is eligible, so the model can never change what is shown.
    """
    page, _query, _semantic_used, _total = recommend_from_profile(
        candidates,
        payload,
        limit=MAX_RANKED_FOR_AI,
    )
    ranked_ids = {int(item["record"].get("id", 0)) for item in page}
    if int(record.get("id", 0)) not in ranked_ids:
        match["ai_explanation"] = {
            "source": "deterministic",
            "model": "",
            "reasons": [],
            "status": "not_top_matches",
        }
        return

    reasons, status = generate_reasons(record, payload)
    match["ai_explanation"] = {
        "source": "ai" if reasons else "deterministic",
        "model": text_model_name() if reasons else "",
        "reasons": list(reasons or []),
        "status": status,
    }


def explain_record(
    professor_id: int,
    profile: StudentProfileInput,
    include_ai: bool = False,
) -> RecommendationResponse | None:
    records = fetch_professors(omit_embeddings=True)
    target: dict | None = None
    for record in records:
        if int(record.get("id", -1)) == professor_id:
            target = reviewed_record(record)
            break
    if target is None:
        return None

    payload = _profile_payload(profile)
    match = score_for_profile(target, payload)
    explained = match["research_fit_score"] >= 30

    if explained and include_ai:
        _attach_ai_explanation(target, payload, match, records)

    results = (
        [recommendation_row_dto(target, match)]
        if explained
        else []
    )

    return RecommendationResponse(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        query=build_profile_query(payload),
        mode="Explain",
        semantic_cached=False,
        total=len(results),
        offset=0,
        limit=1,
        results=results,
    )


def _single_researcher(professor_id: int) -> dict | None:
    records = fetch_professors(omit_embeddings=True)
    for record in records:
        if int(record.get("id", -1)) == professor_id:
            return reviewed_record(record)
    return None


def list_saved(*, user_id: str) -> SavedListResponse:
    rows = fetch_outreach_professors(favorites_only=True, user_id=user_id)
    return SavedListResponse(
        total=len(rows),
        results=[outreach_result_dto(row) for row in rows],
    )


def set_saved(professor_id: int, saved: bool, *, user_id: str) -> MutationResult:
    set_professor_favorite(professor_id=professor_id, is_favorite=saved, user_id=user_id)
    return MutationResult(professor_id=professor_id, saved=saved)


def list_outreach(*, user_id: str) -> OutreachListResponse:
    rows = fetch_outreach_professors(user_id=user_id)
    results = [outreach_result_dto(row) for row in rows]
    # Default dashboard order: needs-attention (follow-up due) first.
    results.sort(
        key=lambda item: (
            0 if item.outreach.follow_up_due else 1,
            item.researcher.university.casefold(),
            item.researcher.name.casefold(),
        )
    )
    return OutreachListResponse(total=len(results), results=results)


def get_outreach_item(professor_id: int, *, user_id: str) -> OutreachResult | None:
    target = _single_researcher(professor_id)
    if target is None:
        return None
    outreach = get_professor_outreach([professor_id], user_id=user_id).get(professor_id, {})
    merged = dict(target)
    merged.update(outreach)
    return outreach_result_dto(merged)


def update_outreach(professor_id: int, updates: OutreachUpdate, *, user_id: str) -> OutreachResult:
    stored_status: str | None = None
    if updates.outreach_status is not None:
        if updates.outreach_status not in STORED_STATUS_BY_FRONTEND:
            raise ValueError("Choose a valid outreach status.")
        stored_status = STORED_STATUS_BY_FRONTEND[updates.outreach_status]
    row = update_professor_outreach(
        professor_id,
        user_id=user_id,
        outreach_status=stored_status,
        notes=updates.notes,
        email_sent_at=updates.email_sent_at,
        follow_up_date=updates.follow_up_date,
        email_to=updates.email_to,
        email_subject=updates.email_subject,
        email_body=updates.email_body,
    )
    target = _single_researcher(professor_id)
    merged = dict(target)
    merged.update(row)
    return outreach_result_dto(merged)

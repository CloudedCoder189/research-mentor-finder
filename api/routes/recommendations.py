from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth.dependencies import require_user_and_csrf
from api.auth.ai_limits import reserve_explanation
from services.ai_explanation import ai_explanations_enabled

from api.schemas.recommendations import RecommendationResponse
from api.services import (
    ExplainRequest,
    RecommendationsRequest,
    explain_record,
    recommend_records,
)

router = APIRouter(prefix="/api", tags=["recommendations"])


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="Personalized recommendations from a student profile",
)
def recommendations(request: RecommendationsRequest) -> RecommendationResponse:
    """Rank researchers against a local student profile (stateless)."""
    return recommend_records(request)


@router.post(
    "/recommendations/explain",
    response_model=RecommendationResponse,
    summary="Why a specific professor matches a student profile",
)
def explain(request: ExplainRequest, http_request: Request) -> RecommendationResponse:
    """Return the personalized match explanation for one researcher.

    ``include_ai`` is opt-in per request: the deterministic reasons are always
    computed, and richer AI wording is only attempted when the caller (the For
    You "Show reasons" action) asks for it.
    """
    if request.include_ai:
        user = require_user_and_csrf(http_request, http_request.headers.get("X-CSRF-Token"))
        if ai_explanations_enabled():
            reserve_explanation(user.user_id)
    response = explain_record(
        request.researcher_id,
        request.profile,
        include_ai=request.include_ai,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Researcher not found")
    return response

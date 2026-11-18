from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.schemas.researcher import ResearcherSummary


class SignalInfo(BaseModel):
    source: str
    label: str
    detail: str
    topic: str = ""


class ExplanationSource(BaseModel):
    """Optional AI wording for one match. Never affects ranking."""

    source: str
    model: str = ""
    reasons: list[str] = Field(default_factory=list)
    status: str = ""


class RecommendationMatch(BaseModel):
    label: str
    research_fit_score: float
    components: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    signals: list[SignalInfo] = Field(default_factory=list)
    ai_explanation: ExplanationSource | None = None


class RecommendationRow(BaseModel):
    researcher: ResearcherSummary
    match: RecommendationMatch

    def researcher_id(self) -> int:
        return self.researcher.id


class RecommendationResponse(BaseModel):
    generated_at: str
    query: str
    mode: str
    semantic_cached: bool = False
    total: int
    offset: int
    limit: int
    results: list[RecommendationRow] = Field(default_factory=list)
    fallback_message: str = ""


def recommendation_match_dto(match: dict[str, Any]) -> RecommendationMatch:
    explanation = match.get("ai_explanation")
    return RecommendationMatch(
        label=str(match.get("label", "")),
        research_fit_score=float(match.get("research_fit_score", 0.0)),
        components={key: float(value) for key, value in (match.get("components") or {}).items()},
        reasons=[str(reason) for reason in (match.get("reasons") or [])],
        signals=[
            SignalInfo(
                source=str(signal.get("source", "")),
                label=str(signal.get("label", "")),
                detail=str(signal.get("detail", "")),
                topic=str(signal.get("topic", "")),
            )
            for signal in (match.get("signals") or [])
        ],
        ai_explanation=(
            ExplanationSource(
                source=str(explanation.get("source", "")),
                model=str(explanation.get("model", "")),
                reasons=[str(reason) for reason in (explanation.get("reasons") or [])],
                status=str(explanation.get("status", "")),
            )
            if isinstance(explanation, dict)
            else None
        ),
    )


def recommendation_row_dto(record: dict, match: dict) -> RecommendationRow:
    from api.schemas.researcher import summary_dto

    return RecommendationRow(
        researcher=summary_dto(record),
        match=recommendation_match_dto(match),
    )

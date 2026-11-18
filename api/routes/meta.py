from __future__ import annotations

from fastapi import APIRouter

from api.schemas.researcher import OptionsResponse
from database import (
    list_department_categories,
    list_fields,
    list_states,
    list_universities,
    fetch_professors,
)
from services.reviewed_directory import discovery_candidate

VERIFICATION_STATUSES = ["Verified", "Review", "Failed", "Not checked"]
OPPORTUNITY_SIGNALS = ["Moderate or strong", "Strong only"]

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/meta/options", response_model=OptionsResponse, summary="Search filter options")
def options() -> OptionsResponse:
    return OptionsResponse(
        universities=list_universities(),
        states=list_states(),
        fields=list_fields(),
        department_categories=list_department_categories(),
        verification_statuses=list(VERIFICATION_STATUSES),
        opportunity_signals=list(OPPORTUNITY_SIGNALS),
        total_researchers=sum(discovery_candidate(record) for record in fetch_professors(omit_embeddings=True)),
    )

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.researcher import ProfessorProfile, SearchResponse
from api.services import BrowseRequest, browse_records, fetch_profile

router = APIRouter(prefix="/api", tags=["researchers"])


@router.get("/researchers", response_model=SearchResponse, summary="Browse researchers")
def browse(
    university: str = "",
    state: str = "",
    field: str = "",
    department_category: str = "",
    verification: str = "",
    opportunity: str = "",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SearchResponse:
    """List researchers with filters, no match scoring."""
    request = BrowseRequest(
        university=university,
        state=state,
        field=field,
        department_category=department_category,
        verification=verification,
        opportunity=opportunity,
        limit=limit,
        offset=offset,
    )
    return browse_records(request)


@router.get(
    "/researchers/{professor_id}",
    response_model=ProfessorProfile,
    summary="Get one professor profile",
)
def get_professor(professor_id: int) -> ProfessorProfile:
    profile = fetch_profile(professor_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Researcher not found")
    return profile
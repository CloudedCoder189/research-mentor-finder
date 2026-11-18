from __future__ import annotations

from fastapi import APIRouter

from api.schemas.researcher import SearchResponse
from api.services import SearchRequest, search_records

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse, summary="Search researchers")
def search(request: SearchRequest) -> SearchResponse:
    """Rank professors by the existing keyword/hybrid semantic pipeline."""
    return search_records(request)
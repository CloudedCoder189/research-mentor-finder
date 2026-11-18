"""Untrusted public ranking inputs are rejected before scoring work."""
import pytest
from fastapi.testclient import TestClient
from api.main import create_app


@pytest.mark.parametrize("path,payload", [
    ("/api/search", {"topics": ["robotics"] * 101}),
    ("/api/search", {"topics": ["r" * 201]}),
    ("/api/recommendations", {"profile": {"interests": ["robotics"] * 101}}),
    ("/api/recommendations", {"profile": {"interests": ["r" * 201]}}),
    ("/api/recommendations", {"profile": {"interests": ["robotics"], "interest_text": "r" * 3001}}),
    *[("/api/recommendations", {"profile": {"interests": ["robotics"], key: ["term"] * 201}})
      for key in ("skills", "experience", "coursework")],
    ("/api/recommendations", {"profile": {"interests": ["robotics"], "preferences": {"locations": ["state"] * 51}}}),
    ("/api/recommendations/explain", {"researcher_id": 1, "profile": {"interests": ["robotics"] * 101}}),
])
def test_oversized_ranking_input_never_reaches_scoring(monkeypatch, path, payload):
    from api.routes import search, recommendations
    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized request reached expensive scoring")
    monkeypatch.setattr(search, "search_records", forbidden)
    monkeypatch.setattr(recommendations, "recommend_records", forbidden)
    monkeypatch.setattr(recommendations, "explain_record", forbidden)
    with TestClient(create_app()) as client:
        assert client.post(path, json=payload).status_code == 422


def test_supported_profile_limits_remain_accepted():
    from api.services import StudentProfileInput, SearchRequest
    profile = StudentProfileInput(interests=["r" * 200] * 100,
        interest_text="r" * 3000, skills=["s" * 200] * 200,
        coursework=["c" * 200] * 200, experience=["e" * 2000] * 200,
        preferences={"locations": ["state"] * 50})
    assert len(profile.interests) == 100
    assert len(SearchRequest(topics=["r" * 200] * 100).topics) == 100

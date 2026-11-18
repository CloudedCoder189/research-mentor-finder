"""Phase 3 recommendation API tests (stateless, read-only)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from services.recommendations import build_profile_query, label_for_score

REDACTED_KEYS = (
    "embedding_json",
    "embedding_model",
    "embedding_source_hash",
    "embedding",
    "_hash",
)

VALID_PROFILE = {
    "profile": {
        "interests": ["Machine learning"],
        "interest_text": "I want to work on applied deep learning for visual recognition.",
        "skills": ["Python"],
        "experience": ["Built a CNN image classifier"],
        "coursework": ["Machine Learning", "Linear Algebra"],
        "preferences": {"locations": ["Anywhere"], "remote_ok": True},
    }
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _assert_no_internal_fields(payload: object) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = key.casefold()
            assert not any(token in lowered for token in REDACTED_KEYS), (
                f"Internal field leaked: {key}"
            )
            _assert_no_internal_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_internal_fields(item)


def _options(client: TestClient) -> dict:
    response = client.get("/api/meta/options")
    assert response.status_code == 200
    return response.json()


def test_recommendations_require_interests(client: TestClient) -> None:
    for payload in (
        {"profile": {"skills": ["Python"]}},
        {"profile": {"interests": []}},
    ):
        response = client.post("/api/recommendations", json=payload)
        assert response.status_code == 422, payload


def test_recommendations_response_schema(client: TestClient) -> None:
    response = client.post("/api/recommendations", json=VALID_PROFILE)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    assert len(body["results"]) > 0
    assert body["mode"] in {"AI semantic + keyword", "Keyword"}
    assert body["query"]

    for row in body["results"]:
        assert isinstance(row["researcher"]["id"], int)
        match = row["match"]
        assert match["label"] in {
            "Strong research match",
            "Good research match",
            "Potential match",
        }
        assert isinstance(match["research_fit_score"], (int, float))
        for key in ("interest", "skills", "projects", "coursework", "location"):
            assert key in match["components"]
        assert match["reasons"]
        assert all(isinstance(signal["source"], str) for signal in match["signals"])
    _assert_no_internal_fields(body)


def test_recommendations_use_interest_text_in_query(client: TestClient) -> None:
    profile = VALID_PROFILE["profile"]
    query = build_profile_query(
        {
            **profile,
            "preferences": {"locations": profile["preferences"]["locations"], "remote_ok": True},
        }
    )
    assert "visual recognition" in query
    assert "Python" in query
    assert "CNN" in query


def test_skills_affect_explanation_deterministically() -> None:
    record = {
        "id": 1,
        "name": "Dr. Jane Smith",
        "university": "U Washington",
        "state": "WA",
        "research_interests": (
            "Computer vision and machine learning using Python and PyTorch "
            "for visual recognition"
        ),
        "ai_summary": (
            "Focuses on CNN image classifiers, linear algebra methods, and "
            "autonomous systems."
        ),
        "categories": "Computer Vision",
        "ai_categories": "Machine Learning",
        "department": "CSE",
        "title": "Professor",
        "field": "Computer Science",
    }
    from services.recommendations import score_for_profile

    match = score_for_profile(
        record,
        {
            "interests": ["Machine learning"],
            "interest_text": "",
            "skills": ["Pytorch", "Python"],
"experience": ["CNN image classifier"],
            "coursework": ["Linear Algebra"],
            "preferences": {"locations": [], "remote_ok": False},
        },
    )
    assert match["research_fit_score"] >= 50
    joined = " ".join(match["reasons"])
    assert "Machine learning" in joined
    assert "Professor Smith" in joined
    sources = {signal["source"] for signal in match["signals"]}
    assert "skills" in sources
    assert "projects" in sources
    assert "coursework" in sources


def test_no_invented_student_experience() -> None:
    record = {
        "id": 2,
        "name": "Dr. Alan Fox",
        "university": "U Washington",
        "state": "WA",
        "research_interests": "Robotics, robot perception, autonomous systems",
        "ai_summary": "Robot perception and autonomous navigation.",
        "categories": "Robotics",
        "ai_categories": "Autonomous Systems",
        "department": "ME",
        "title": "Professor",
        "field": "Engineering",
    }
    from services.recommendations import score_for_profile

    profile = {
        "interests": ["Robotics", "Machine learning"],
        "interest_text": "",
        "skills": ["Python"],
        "experience": [],
        "coursework": [],
        "preferences": {"locations": ["Anywhere"], "remote_ok": True},
    }
    match = score_for_profile(record, profile)
    assert "Professor Fox" in " ".join(match["reasons"])
    # Experience was empty, so no projects/personal claims should appear.
    assert not any(reason.lower().startswith("your experience") for reason in match["reasons"])


def test_explain_returns_single_match(client: TestClient) -> None:
    live = client.get("/api/researchers?limit=1").json()["results"][0]["researcher"]
    response = client.post(
        "/api/recommendations/explain",
        json={"profile": VALID_PROFILE["profile"], "researcher_id": live["id"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] in {0, 1}
    if body["total"] == 1:
        assert body["results"][0]["researcher"]["id"] == live["id"]
    _assert_no_internal_fields(body)


def test_explain_missing_researcher_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/recommendations/explain",
        json={"profile": VALID_PROFILE["profile"], "researcher_id": 999999999},
    )
    assert response.status_code == 404


def test_recommendations_university_filter(client: TestClient) -> None:
    university = _options(client)["universities"][0]
    response = client.post(
        "/api/recommendations",
        json={**VALID_PROFILE, "filters": {"university": university}, "limit": 20},
    )
    assert response.status_code == 200
    body = response.json()
    for row in body["results"]:
        assert row["researcher"]["university"] == university


def test_recommendations_verification_filter(client: TestClient) -> None:
    response = client.post(
        "/api/recommendations",
        json={**VALID_PROFILE, "filters": {"verification": "Verified"}, "limit": 20},
    )
    assert response.status_code == 200
    body = response.json()
    for row in body["results"]:
        assert row["researcher"]["verification_status"] == "Verified"


def test_minimal_profile_handled(client: TestClient) -> None:
    response = client.post(
        "/api/recommendations",
        json={"profile": {"interests": ["Astronomy and astrophysics"]}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 0
    for row in body["results"]:
        assert row["match"]["label"] in {
            "Strong research match",
            "Good research match",
            "Potential match",
        }


def test_label_thresholds() -> None:
    assert label_for_score(85) == "Strong research match"
    assert label_for_score(70) == "Strong research match"
    assert label_for_score(60) == "Good research match"
    assert label_for_score(35) == "Potential match"
    assert label_for_score(20) == "Potential match"


def test_recommendations_pagination(client: TestClient) -> None:
    first = client.post(
        "/api/recommendations", json={**VALID_PROFILE, "limit": 3}
    ).json()
    second = client.post(
        "/api/recommendations", json={**VALID_PROFILE, "limit": 3, "offset": 3}
    ).json()
    assert first["total"] == second["total"]
    first_ids = {row["researcher"]["id"] for row in first["results"]}
    second_ids = {row["researcher"]["id"] for row in second["results"]}
    assert not first_ids & second_ids
"""Read-only FastAPI route tests for the Research Mentor Finder Phase 2 API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

REDACTED_KEYS = (
    "embedding_json",
    "embedding_model",
    "embedding_source_hash",
    "embedding",
    "_hash",
)


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


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["total_researchers"], int)


def test_options_response_schema(client: TestClient) -> None:
    body = _options(client)
    for key in (
        "universities",
        "states",
        "fields",
        "department_categories",
        "verification_statuses",
        "opportunity_signals",
    ):
        assert key in body, f"Missing options key: {key}"
        assert isinstance(body[key], list)
    assert "Verified" in body["verification_statuses"]
    _assert_no_internal_fields(body)


def test_browse_returns_valid_researchers(client: TestClient) -> None:
    response = client.get("/api/researchers?limit=5&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "Browse"
    assert body["total"] > 0
    assert 0 < len(body["results"]) <= 5

    for row in body["results"]:
        researcher = row["researcher"]
        for key in (
            "id",
            "name",
            "university",
            "department",
            "title",
            "topics",
            "email",
            "verification_status",
            "data_source_url",
        ):
            assert key in researcher
        assert row["match"] is None
        assert isinstance(researcher["id"], int)
    _assert_no_internal_fields(body)


@pytest.fixture(scope="module")
def live_researcher(client: TestClient) -> dict:
    body = client.get("/api/researchers?limit=1").json()
    return body["results"][0]["researcher"]


def test_valid_professor_lookup(client: TestClient, live_researcher: dict) -> None:
    professor_id = live_researcher["id"]
    response = client.get(f"/api/researchers/{professor_id}")
    assert response.status_code == 200
    profile = response.json()

    researcher = profile["researcher"]
    assert researcher["id"] == professor_id
    for key in (
        "name",
        "university",
        "department",
        "title",
        "city",
        "state",
        "topics",
        "research_interests",
        "ai_summary",
        "email",
        "verification_status",
    ):
        assert key in researcher
    for key in (
        "profile_url",
        "website_url",
        "website_status_label",
        "verification_issues",
        "verified_at",
        "last_checked_at",
        "opportunity_signals",
        "source_type",
    ):
        assert key in profile
    assert profile["website_status_label"] in {
        "Verified",
        "Review",
        "Broken",
        "Not checked",
    }
    _assert_no_internal_fields(profile)


def test_missing_professor_returns_404(client: TestClient) -> None:
    response = client.get("/api/researchers/999999999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].casefold()


def test_search_query_returns_ranked_results(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={"query": "machine learning", "limit": 10, "offset": 0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    assert len(body["results"]) > 0
    for row in body["results"]:
        assert row["researcher"]["id"] > 0
        assert row["match"] is not None
        assert row["match"]["score"] > 0
        assert row["match"]["strength"] in {
            "Strong match",
            "Related match",
            "Possible match",
        }
        assert row["match"]["reason"]
    # Ranking is descending by score.
    scores = [row["match"]["score"] for row in body["results"]]
    assert scores == sorted(scores, reverse=True)
    _assert_no_internal_fields(body)


def test_search_respects_pagination(client: TestClient) -> None:
    first = client.post("/api/search", json={"query": "robotics", "limit": 3}).json()
    second = client.post(
        "/api/search", json={"query": "robotics", "limit": 3, "offset": 3}
    ).json()
    assert first["total"] == second["total"]
    first_ids = [row["researcher"]["id"] for row in first["results"]]
    second_ids = [row["researcher"]["id"] for row in second["results"]]
    assert not set(first_ids) & set(second_ids)


def test_search_university_filter(client: TestClient) -> None:
    university = _options(client)["universities"][0]
    response = client.post(
        "/api/search",
        json={"query": "", "university": university, "limit": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    for row in body["results"]:
        assert row["researcher"]["university"] == university


def test_search_state_filter(client: TestClient) -> None:
    state = _options(client)["states"][0]
    response = client.post(
        "/api/search",
        json={"query": "", "state": state, "limit": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    for row in body["results"]:
        assert row["researcher"]["state"] == state


def test_search_field_filter(client: TestClient) -> None:
    field = _options(client)["fields"][0]
    response = client.post(
        "/api/search",
        json={"query": "", "field": field, "limit": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    for row in body["results"]:
        assert row["researcher"]["field"] == field


def test_search_verification_filter(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={"query": "", "verification": "Verified", "limit": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 0
    for row in body["results"]:
        assert row["researcher"]["verification_status"] == "Verified"


def test_search_combined_filters(client: TestClient) -> None:
    options = _options(client)
    university = options["universities"][0]
    state = options["states"][0]
    response = client.post(
        "/api/search",
        json={
            "query": "",
            "university": university,
            "state": state,
            "verification": "Verified",
            "limit": 50,
        },
    )
    assert response.status_code == 200
    body = response.json()
    for row in body["results"]:
        assert row["researcher"]["university"] == university
        assert row["researcher"]["state"] == state
        assert row["researcher"]["verification_status"] == "Verified"


def test_search_no_results(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={"query": "zzzzqxyz nonexistent research topic", "limit": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["results"] == []


def test_empty_search_query_browses(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={"query": "", "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "Browse"
    assert body["total"] > 0
    assert all(row["match"] is None for row in body["results"])


def test_topics_instead_of_query(client: TestClient) -> None:
    response = client.post(
        "/api/search",
        json={"topics": ["Systems"], "limit": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 0
    assert any(
        "Systems" in row["researcher"]["topics"]
        for row in body["results"]
        if row["researcher"]["topics"]
    )


def test_invalid_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/researchers/not-an-integer")
    assert response.status_code == 422


def test_cors_headers_for_frontend_origin(client: TestClient) -> None:
    response = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
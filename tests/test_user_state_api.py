"""API tests for the private local saved + outreach endpoints (Phase 4).

Each test runs against a throwaway SQLite database under ``tmp_path`` so the
real professor database is never written during the suite. Write-boundary and
leak checks prove these endpoints mutate only user-scoped ``professor_outreach``
rows.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from api.main import create_app
from tests._auth_helpers import DEV_USER_ID, signed_client

REDACTED_KEYS = (
    "embedding_json",
    "embedding_model",
    "embedding_source_hash",
    "embedding",
    "_hash",
)

BASE = {
    "name": "User State API Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and robotics",
    "email": "user-state@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/user-state",
    "categories": "Machine Learning, Robotics",
    "source_type": "Test",
}


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


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    try:
        yield signed_client()
    finally:
        database.DB_PATH = original


def _seed_professor(tmp_path: Path, name: str, email: str) -> int:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        record = dict(BASE)
        record["name"] = name
        record["email"] = email
        record["profile_url"] = f"https://profiles.stanford.edu/{email.split('@')[0]}"
        database.upsert_professors([record])
        for row in database.fetch_professors():
            if str(row["email"]) == email:
                return int(row["id"])
        raise AssertionError(f"seeded professor {email} not found")
    finally:
        database.DB_PATH = original


def test_saved_endpoints_persist_across_instances(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]

    created = client.post(f"/api/saved/{professor_id}")
    assert created.status_code == 200
    assert created.json() == {"professor_id": professor_id, "saved": True}

    listed = client.get("/api/saved")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["results"][0]["researcher"]["id"] == professor_id
    assert body["results"][0]["outreach"]["is_favorite"] is True
    _assert_no_internal_fields(body)

    # A fresh client that logs in again (simulating a restart) still sees the
    # saved row. Signing in again creates a brand-new session, so the outer
    # ``client``'s session is superseded; continue from here with ``fresh``.
    fresh = signed_client()
    assert fresh.get("/api/saved").json()["total"] == 1

    removed = fresh.delete(f"/api/saved/{professor_id}")
    assert removed.status_code == 200
    assert removed.json() == {"professor_id": professor_id, "saved": False}
    assert fresh.get("/api/saved").json()["total"] == 0


def test_outreach_patch_rejects_a_queued_write_from_a_different_account(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    response = client.patch(f"/api/outreach/{professor_id}", json={
        "expected_user_id": "synthetic-other-account", "notes": "Must not be saved"})
    assert response.status_code == 409
    assert client.get(f"/api/outreach/{professor_id}").json()["outreach"]["notes"] == ""
    assert client.patch(f"/api/outreach/{professor_id}", json={
        "expected_user_id": DEV_USER_ID, "notes": "Own account"}).status_code == 200


def test_outreach_patch_persists_draft(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    patch = {
        "outreach_status": "Drafted",
        "email_to": "user-state@stanford.edu",
        "email_subject": "Undergrad research interest",
        "email_body": "Hi Dr., would you take students this year?",
        "notes": "Sent from the Phase 4 composer.",
    }
    response = client.patch(f"/api/outreach/{professor_id}", json=patch)
    assert response.status_code == 200
    outreach = response.json()["outreach"]
    assert outreach["status"] == "Drafted"
    assert outreach["email_subject"] == patch["email_subject"]
    assert outreach["email_body"] == patch["email_body"]
    assert outreach["email_to"] == patch["email_to"]
    assert outreach["notes"] == patch["notes"]

    stored = database.get_professor_outreach(
        [professor_id], user_id=DEV_USER_ID
    )[professor_id]
    assert stored["outreach_status"] == "Email drafted"
    assert stored["email_subject"] == patch["email_subject"]

    tracked = client.get("/api/outreach")
    assert tracked.status_code == 200
    assert tracked.json()["total"] == 1
    assert tracked.json()["results"][0]["outreach"]["status"] == "Drafted"


def test_outreach_get_defaults_for_untracked(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    response = client.get(f"/api/outreach/{professor_id}")
    assert response.status_code == 200
    outreach = response.json()["outreach"]
    assert outreach["status"] == "Not contacted"
    assert outreach["is_favorite"] is False
    assert outreach["email_subject"] == ""
    assert outreach["email_body"] == ""
    assert client.get("/api/outreach").json()["total"] == 0


def test_follow_up_derivation(client: TestClient, tmp_path: Path) -> None:
    due_id = _seed_professor(tmp_path, "Follow Up Due", "follow-up@stanford.edu")
    later_id = _seed_professor(tmp_path, "Follow Up Later", "follow-up-later@stanford.edu")
    replied_id = _seed_professor(tmp_path, "Replied Prof", "replied@stanford.edu")

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()
    sent_week_ago = (date.today() - timedelta(days=7)).isoformat()

    client.patch(
        f"/api/outreach/{due_id}",
        json={
            "outreach_status": "Sent",
            "email_sent_at": sent_week_ago,
            "follow_up_date": yesterday,
        },
    )
    client.patch(
        f"/api/outreach/{later_id}",
        json={
            "outreach_status": "Sent",
            "email_sent_at": sent_week_ago,
            "follow_up_date": next_week,
        },
    )
    client.patch(
        f"/api/outreach/{replied_id}",
        json={
            "outreach_status": "Sent",
            "email_sent_at": sent_week_ago,
            "follow_up_date": yesterday,
        },
    )
    client.patch(f"/api/outreach/{replied_id}", json={"outreach_status": "Replied"})

    assert client.get(f"/api/outreach/{due_id}").json()["outreach"]["status"] == "Follow-up due"
    status = client.get(f"/api/outreach/{later_id}").json()["outreach"]["status"]
    assert status == "Sent"
    assert client.get(f"/api/outreach/{replied_id}").json()["outreach"]["status"] == "Replied"
    assert (
        client.get(f"/api/outreach/{due_id}").json()["outreach"]["follow_up_due"] is True
    )
    assert (
        client.get(f"/api/outreach/{later_id}").json()["outreach"]["follow_up_due"] is False
    )

    rows = client.get("/api/outreach").json()["results"]
    assert rows[0]["researcher"]["id"] == due_id


def test_unsave_preserves_outreach_history(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    client.post(f"/api/saved/{professor_id}")
    client.patch(
        f"/api/outreach/{professor_id}",
        json={"outreach_status": "Sent", "email_sent_at": "2026-07-28"},
    )
    client.delete(f"/api/saved/{professor_id}")
    assert client.get("/api/saved").json()["total"] == 0
    outreach = client.get(f"/api/outreach/{professor_id}").json()["outreach"]
    assert outreach["status"] == "Sent"
    assert outreach["email_sent_at"] == "2026-07-28"
    assert client.get("/api/outreach").json()["total"] == 1


def test_outreach_patch_never_clobbers_favorite(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    client.post(f"/api/saved/{professor_id}")
    client.patch(
        f"/api/outreach/{professor_id}",
        json={"outreach_status": "Drafted", "email_subject": "Subject"},
    )
    assert client.get("/api/saved").json()["total"] == 1
    saved_row = client.get("/api/saved").json()["results"][0]
    assert saved_row["outreach"]["is_favorite"] is True
    assert saved_row["outreach"]["status"] == "Drafted"


def test_saved_and_outreach_validate_professor_ids(client: TestClient) -> None:
    assert client.post("/api/saved/999999").status_code == 404
    assert client.delete("/api/saved/999999").status_code == 404
    assert client.get("/api/outreach/999999").status_code == 404
    assert client.patch("/api/outreach/999999", json={"notes": "x"}).status_code == 404
    assert client.post("/api/saved/not-an-integer").status_code == 422
    assert client.patch("/api/outreach/not-an-integer", json={}).status_code == 422


def test_outreach_patch_rejects_bad_status_and_dates(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    assert (
        client.patch(f"/api/outreach/{professor_id}", json={"outreach_status": "Maybe"}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/outreach/{professor_id}", json={"email_sent_at": "July 28"}
        ).status_code
        == 422
    )


def test_saved_and_outreach_payloads_never_leak_internals(client: TestClient) -> None:
    professor_id = database.fetch_professors()[0]["id"]
    client.post(f"/api/saved/{professor_id}")
    client.patch(
        f"/api/outreach/{professor_id}",
        json={
            "outreach_status": "Drafted",
            "email_subject": "Subj",
            "email_body": "Body",
        },
    )
    _assert_no_internal_fields(client.get("/api/saved").json())
    _assert_no_internal_fields(client.get("/api/outreach").json())
    _assert_no_internal_fields(client.get(f"/api/outreach/{professor_id}").json())


def test_write_boundary_professors_unchanged(client: TestClient) -> None:
    before = database.fetch_professors()
    professor_id = database.fetch_professors()[0]["id"]
    client.post(f"/api/saved/{professor_id}")
    client.delete(f"/api/saved/{professor_id}")
    client.patch(
        f"/api/outreach/{professor_id}",
        json={
            "outreach_status": "Drafted",
            "notes": "Edits",
            "email_subject": "S",
            "email_body": "B",
            "email_sent_at": "2026-07-28",
            "follow_up_date": "2026-08-01",
        },
    )
    client.patch(f"/api/outreach/{professor_id}", json={"outreach_status": "Replied"})
    assert database.fetch_professors() == before


def test_cors_allows_saved_and_outreach_methods(client: TestClient) -> None:
    for method in ("GET", "POST", "PATCH", "DELETE", "OPTIONS"):
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": method,
        }
        response = client.options(
            "/api/saved/1",
            headers=headers,
        )
        assert response.status_code == 200
        allowed = response.headers.get("access-control-allow-methods", "")
        assert "PATCH" in allowed and "DELETE" in allowed, allowed


def test_endpoints_require_authentication(tmp_path: Path) -> None:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    professor_id = database.upsert_professors([BASE])
    try:
        anonymous = TestClient(create_app())
        assert anonymous.get("/api/saved").status_code == 401
        assert anonymous.get("/api/outreach").status_code == 401
        assert anonymous.post(f"/api/saved/{professor_id}").status_code == 401
        assert anonymous.delete(f"/api/saved/{professor_id}").status_code == 401
        assert anonymous.patch(f"/api/outreach/{professor_id}", json={}).status_code == 401
    finally:
        database.DB_PATH = original

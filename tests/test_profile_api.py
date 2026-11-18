"""API tests for the authenticated, per-user student profile (Phase 6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database
from api.main import create_app
from tests._auth_helpers import client_for_user, signed_client

FULL_PROFILE = {
    "interests": ["Machine learning", "Robotics"],
    "interest_text": "I want to build robots that learn from play.",
    "skills": ["Python", "PyTorch"],
    "experience": ["NASA internship"],
    "coursework": ["Linear Algebra", "Algorithms"],
    "education_level": "university",
    "preferences": {
        "locations": ["California", "Seattle"],
        "university_types": ["Research university"],
        "support_level": "funding",
        "remote_ok": True,
    },
    "completed": True,
}


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    yield tmp_path
    database.DB_PATH = original


def test_profile_get_returns_defaults(db: Path) -> None:
    client = signed_client()
    body = client.get("/api/profile").json()
    assert body["interests"] == []
    assert body["interest_text"] == ""
    assert body["completed"] is False
    assert body["education_level"] == "unspecified"
    assert body["preferences"] == {
        "locations": [],
        "university_types": [],
        "support_level": "",
        "remote_ok": False,
    }


def test_profile_put_and_get_round_trip(db: Path) -> None:
    client = signed_client()

    put = client.put("/api/profile", json=FULL_PROFILE)
    assert put.status_code == 200
    body = put.json()
    assert body["interests"] == FULL_PROFILE["interests"]
    assert body["interest_text"] == FULL_PROFILE["interest_text"]
    assert body["education_level"] == "university"
    assert body["completed"] is True
    assert body["preferences"]["remote_ok"] is True
    assert body["preferences"]["locations"] == ["California", "Seattle"]
    assert body["updated_at"]

    again = client.get("/api/profile").json()
    assert again["interests"] == FULL_PROFILE["interests"]
    assert again["completed"] is True

    stored = database.get_student_profile("dev:dev@localhost")
    assert stored is not None
    assert stored["education_level"] == "university"
    assert stored["preferences"]["support_level"] == "funding"


def test_profile_rejects_invalid_education_level(db: Path) -> None:
    client = signed_client()
    payload = dict(FULL_PROFILE)
    payload["education_level"] = "middle school"
    response = client.put("/api/profile", json=payload)
    assert response.status_code == 422


def test_profile_put_replaces_entire_profile(db: Path) -> None:
    client = signed_client()
    client.put("/api/profile", json=FULL_PROFILE)
    response = client.put(
        "/api/profile",
        json={"interests": ["Robotics only"], "completed": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interests"] == ["Robotics only"]
    # PUT is full-profile replace: omitted fields fall back to defaults.
    assert body["education_level"] == "unspecified"
    assert body["preferences"]["locations"] == []
    assert body["completed"] is True


def test_profile_requires_authentication(db: Path) -> None:
    anonymous = TestClient(create_app(), follow_redirects=False)
    assert anonymous.get("/api/profile").status_code == 401
    assert anonymous.put("/api/profile", json=FULL_PROFILE).status_code == 401


def test_profile_write_requires_csrf(db: Path) -> None:
    client = signed_client(with_csrf=False)
    assert client.put("/api/profile", json=FULL_PROFILE).status_code == 403


def test_profile_isolated_between_users(db: Path) -> None:
    alice = client_for_user("google:alice", "alice@example.com")
    bob = client_for_user("google:bob", "bob@example.com")

    alice.put("/api/profile", json=FULL_PROFILE)

    assert alice.get("/api/profile").json()["completed"] is True
    assert alice.get("/api/profile").json()["interests"] == FULL_PROFILE["interests"]

    bob_body = bob.get("/api/profile").json()
    assert bob_body["completed"] is False
    assert bob_body["interests"] == []
    assert bob_body["education_level"] == "unspecified"

    assert database.get_student_profile("google:alice") is not None
    assert database.get_student_profile("google:bob") is None

@pytest.mark.parametrize("level", ["unspecified", "high_school", "college", "university", "graduate"])
def test_explicit_education_is_preserved(db: Path, level: str) -> None:
    client = signed_client()
    response = client.put("/api/profile", json={"education_level": level})
    assert response.status_code == 200
    assert client.get("/api/profile").json()["education_level"] == level

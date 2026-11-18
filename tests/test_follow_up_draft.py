"""Tests for the grounded follow-up draft generator (no sending, no claims)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import database
from api.gmail import token_store
from api.gmail.sync import _timephrase
from api.main import create_app
from tests._auth_helpers import DEV_USER_ID, client_for_user, signed_client

# The follow-up copy quotes a human phrase ("about 2 days ago") derived from the
# real clock, so the assertion only holds when both the seed and the clock agree.
# Pin both to one fixed instant instead of depending on the time of day.
FROZEN_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    """datetime whose ``now()`` is pinned to FROZEN_NOW."""

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001 - matches datetime.now signature
        return FROZEN_NOW.astimezone(tz) if tz is not None else FROZEN_NOW

BASE = {
    "name": "Dr. Amelia Rao",
    "university": "MIT",
    "department": "Brain and Cognitive Sciences",
    "title": "Associate Professor",
    "research_interests": "Computational neuroscience",
    "email": "arao@mit.edu",
    "website_url": "https://example.org/rao",
    "profile_url": "https://profiles.mit.edu/arao",
    "categories": "Neuroscience",
    "source_type": "Test",
}


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    # Freeze only the module that measures elapsed time, so production rounding
    # in api/gmail/sync.py stays untouched.
    monkeypatch.setattr("api.gmail.threads.datetime", _FrozenDatetime)
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor_id = int(database.fetch_professors()[0]["id"])
    yield {"tmp_path": tmp_path, "professor_id": professor_id, "monkeypatch": monkeypatch}
    database.DB_PATH = original


def _seed_sent(professor_id: int, user_id: str = DEV_USER_ID) -> None:
    sent_at = (FROZEN_NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    database.update_professor_outreach(
        professor_id,
        user_id=user_id,
        outreach_status="Email sent",
        email_to="arao@mit.edu",
        email_subject="Research inquiry",
        email_body="Hello, I am interested in your lab.",
        gmail_sent_at=sent_at,
    )


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (0, "recently"),
        (1, "1 hour ago"),
        (59, "1 hour ago"),
        (60, "1 hour ago"),
        (119, "1 hour ago"),
        (1439, "23 hours ago"),
        (1440, "about a day ago"),
        (2879, "about a day ago"),
        (2880, "about 2 days ago"),
        (5759, "about 3 days ago"),
    ],
)
def test_timephrase_boundaries_are_deterministic(
    minutes: int, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin current rounding so it cannot drift unnoticed.

    Production floors elapsed days, so 1439 minutes reads "about a day ago"
    while 1440 reads the same; this is the documented behaviour, not a bug.
    """
    monkeypatch.setattr("api.gmail.threads.datetime", _FrozenDatetime)
    sent_at = (FROZEN_NOW - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _timephrase(sent_at) == expected


def _no_calls_recorder(calls: list):
    def recorder(url, **kwargs):
        calls.append(url)
        return None

    return recorder


def test_follow_up_requires_sent_evidence_and_calls_no_gmail(env, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(requests, "get", _no_calls_recorder(calls))
    database.update_professor_outreach(
        env["professor_id"], user_id=DEV_USER_ID, outreach_status="Email drafted"
    )
    response = signed_client().post(f"/api/outreach/{env['professor_id']}/follow-up-draft")
    assert response.status_code == 422
    assert "date you sent" in response.json()["detail"].lower()
    assert calls == []


def test_follow_up_generates_grounded_content_without_sending(env, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(requests, "get", _no_calls_recorder(calls))
    _seed_sent(env["professor_id"])
    before = database.fetch_professors()

    body = signed_client().post(f"/api/outreach/{env['professor_id']}/follow-up-draft").json()
    assert "nothing was sent" in body["message"].lower()
    outreach = body["outreach"]["outreach"]
    assert outreach["email_to"] == "arao@mit.edu"
    assert outreach["email_subject"] == "Following up: Research inquiry"
    text = outreach["email_body"].lower()
    assert "dr. amelia rao" in text
    assert "research inquiry" in text
    assert "about 2 days ago" in text
    assert "make sure my earlier note reached you" in text
    # Grounding guarantees: no false claims about the professor or a reply.
    for forbidden in (
        "you are interested",
        "you're interested",
        "you ignored",
        "you read",
        "replied",
        "you opened",
    ):
        assert forbidden not in text, forbidden
    # Status was not changed by generating a draft.
    assert outreach["status"] == "Sent"
    assert calls == []
    # Only the local outreach row changed; professor table untouched.
    assert database.fetch_professors() == before


def test_follow_up_includes_student_interest_from_profile(env, monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", _no_calls_recorder([]))
    _seed_sent(env["professor_id"])
    client = signed_client()
    database.upsert_user(user_id=DEV_USER_ID, email="dev@localhost", display_name="Jordan Lee")
    database.save_student_profile(
        DEV_USER_ID,
        interests=["computational neuroscience"],
        interest_text="",
        skills=[],
        experience=[],
        coursework=[],
        education_level="university",
        preferences={},
        completed=True,
    )
    body = client.post(f"/api/outreach/{env['professor_id']}/follow-up-draft").json()
    text = body["outreach"]["outreach"]["email_body"]
    assert "interested in computational neuroscience" in text
    assert "Jordan" in text


def test_follow_up_for_unknown_researcher_is_404(env, monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", _no_calls_recorder([]))
    response = signed_client().post("/api/outreach/424242/follow-up-draft")
    assert response.status_code == 404


def test_follow_up_is_scoped_per_user(env, monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", _no_calls_recorder([]))
    _seed_sent(env["professor_id"])
    other = client_for_user("google:other", "other@example.com")
    # The other account has never sent anything to this professor.
    response = other.post(f"/api/outreach/{env['professor_id']}/follow-up-draft")
    assert response.status_code == 404 or response.status_code == 422


def test_follow_up_needs_auth_and_csrf(env, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    _seed_sent(env["professor_id"])
    client = TestClient(create_app(), follow_redirects=False)
    response = client.post(f"/api/outreach/{env['professor_id']}/follow-up-draft")
    assert response.status_code == 401

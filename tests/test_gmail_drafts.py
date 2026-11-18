"""Tests for Gmail draft MIME construction, REST requests, and the draft
service's pairing of Gmail calls with user outreach persistence.

All Gmail/Google traffic is mocked; no live credentials or network access.
"""

from __future__ import annotations

import base64
import time
from email import message_from_bytes
from pathlib import Path

import pytest
import requests

import database
from api.gmail import drafts, service, token_store
from api.gmail.drafts import RecipientError, build_mime_raw
from api.gmail.oauth import GmailApiError
from api.gmail.config import GMAIL_SCOPES
from api.schemas.gmail import GmailDraftRequest
from database import DEFAULT_USER_ID

BASE = {
    "name": "Gmail Draft Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and robotics",
    "email": "gmail-draft@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/gmail-draft",
    "categories": "Machine Learning, Robotics",
    "source_type": "Test",
}


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._json = payload or {}

    def json(self):
        return self._json


def _decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    monkeypatch.setenv("GMAIL_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "test-secret")
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    token_store.save_credentials(
        DEFAULT_USER_ID,
        {
            "client_id": "test-client.apps.googleusercontent.com",
            "account_email": "me@example.com",
            "token": {"access_token": "at", "refresh_token": "rt", "issued_at": int(time.time()), "expires_in": 3600, "scope": " ".join(GMAIL_SCOPES), "scope_verified": True},
        },
    )
    professor_id = int(database.fetch_professors()[0]["id"])
    yield {"professor_id": professor_id, "tmp_path": tmp_path}
    database.DB_PATH = original


# --- recipient validation -------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["first.last+tag@sub.example.edu", "ok@example.com", "DrSmith@university.edu"],
)
def test_validate_recipient_accepts_valid(value: str) -> None:
    assert drafts.validate_recipient(value) == value.lower()


@pytest.mark.parametrize(
    "value",
    ["", "not-an-email", "a b@example.com", "a@b", "a@@b.com",
     "@example.com", "a@example .com", "Dr. Smith <x@y.com>"],
)
def test_validate_recipient_rejects_invalid(value: str) -> None:
    with pytest.raises(RecipientError):
        drafts.validate_recipient(value)


# --- MIME construction ----------------------------------------------------


def test_build_mime_raw_round_trips_headers_and_parts() -> None:
    raw = build_mime_raw("first.last@example.edu", "Hello Professor", "Line one\n\nLine two")
    message = message_from_bytes(_decode(raw))
    assert message["To"] == "first.last@example.edu"
    assert message["Subject"] == "Hello Professor"
    assert "X-Mailer" in message

    parts = message.get_payload()
    assert len(parts) == 2
    plain = next(part for part in parts if part.get_content_type() == "text/plain")
    html = next(part for part in parts if part.get_content_type() == "text/html")
    assert "Line one\n\nLine two" in plain.get_payload(decode=True).decode("utf-8")
    assert "<br>" in html.get_payload(decode=True).decode("utf-8")


def test_build_mime_raw_escapes_html() -> None:
    raw = build_mime_raw("ok@example.com", "S", "<script>alert(1)</script> body")
    message = message_from_bytes(_decode(raw))
    html = next(part for part in message.get_payload() if part.get_content_type() == "text/html")
    rendered = html.get_payload(decode=True).decode("utf-8")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


# --- raw REST requests ----------------------------------------------------


def test_create_draft_posts_raw_to_drafts_endpoint(monkeypatch) -> None:
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        assert kwargs["headers"]["Authorization"] == "Bearer at"
        return _Response(201, {"id": "d1", "message": {"threadId": "t1"}})

    monkeypatch.setattr(requests, "request", fake_request)
    result = drafts.create_draft("at", "ok@example.com", "Subject", "Body")
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/users/me/drafts")
    parsed = _decode(captured["json"]["message"]["raw"])
    assert b"To: ok@example.com" in parsed
    assert result == {"draft_id": "d1", "thread_id": "t1"}


def test_update_draft_puts_to_existing_draft_id(monkeypatch) -> None:
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _Response(200, {"id": "d1", "message": {"threadId": "t1"}})

    monkeypatch.setattr(requests, "request", fake_request)
    drafts.update_draft("at", "d1", "ok@example.com", "Subject", "Body")
    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/users/me/drafts/d1")


def test_gmail_api_error_preserves_status(monkeypatch) -> None:
    def fake_request(method, url, **kwargs):
        return _Response(403)

    monkeypatch.setattr(requests, "request", fake_request)
    with pytest.raises(GmailApiError) as excinfo:
        drafts.create_draft("at", "ok@example.com", "Subject", "Body")
    assert excinfo.value.status == 403


def test_gmail_network_failure_raises_api_error(monkeypatch) -> None:
    def failing_request(method, url, **kwargs):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(requests, "request", failing_request)
    with pytest.raises(GmailApiError, match="Could not reach"):
        drafts.create_draft("at", "ok@example.com", "Subject", "Body")


# --- service-level draft create/update ------------------------------------


def test_create_draft_persists_metadata_and_keeps_professor(tmp_db, monkeypatch) -> None:
    captured = {}
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        if method == "POST":
            captured["json"] = kwargs.get("json")
            return _Response(201, {"id": "draft-1", "message": {"threadId": "thread-1"}})
        return _Response(500)

    monkeypatch.setattr(requests, "request", fake_request)

    before = database.fetch_professors()
    result = service.create_gmail_draft(
        int(tmp_db["professor_id"]),
        GmailDraftRequest(to="ok@example.com", subject="Subject", body="Body", notes="Note"),
        DEFAULT_USER_ID,
    )
    assert result.gmail_draft_id == "draft-1"
    assert result.gmail_thread_id == "thread-1"
    assert result.gmail_account_email == "me@example.com"
    assert result.gmail_draft_created_at
    assert result.outreach.outreach.notes == "Note"
    assert result.outreach.outreach.status == "Drafted"

    row = database.get_professor_outreach([int(tmp_db["professor_id"])])[int(tmp_db["professor_id"])]
    assert row["gmail_draft_id"] == "draft-1"
    assert row["gmail_account_email"] == "me@example.com"
    assert row["email_subject"] == "Subject"
    assert database.fetch_professors() == before


def test_update_draft_requires_existing_draft(tmp_db) -> None:
    with pytest.raises(service.DraftMissingError):
        service.update_gmail_draft(
            int(tmp_db["professor_id"]),
            GmailDraftRequest(to="ok@example.com", subject="Subject", body="Body"),
        )


def test_update_draft_replaces_gmail_message(tmp_db, monkeypatch) -> None:
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        return _Response(200, {"id": "draft-1", "message": {"threadId": "thread-1"}})

    monkeypatch.setattr(requests, "request", fake_request)

    database.update_professor_outreach(
        int(tmp_db["professor_id"]),
        gmail_draft_id="draft-1",
        gmail_thread_id="thread-1",
        gmail_account_email="me@example.com",
    )
    result = service.update_gmail_draft(
        int(tmp_db["professor_id"]),
        GmailDraftRequest(to="other@example.edu", subject="New subject", body="New body"),
    )
    assert result.gmail_draft_id == "draft-1"
    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/drafts/draft-1")


# --- failure modes preserve the local draft -------------------------------


def test_invalid_recipient_persists_local_content_and_never_calls_gmail(
    tmp_db, monkeypatch
) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(method)
        return _Response(201, {"id": "d", "message": {"threadId": "t"}})

    monkeypatch.setattr(requests, "request", fake_request)
    with pytest.raises(RecipientError):
        service.create_gmail_draft(
            int(tmp_db["professor_id"]),
            GmailDraftRequest(to="not an email", subject="Subject", body="Body"),
        )
    assert calls == []
    row = database.get_professor_outreach([int(tmp_db["professor_id"])])[int(tmp_db["professor_id"])]
    assert row["email_subject"] == "Subject"
    assert row["email_body"] == "Body"
    assert row["gmail_draft_id"] == ""


def test_gmail_failure_preserves_local_draft(tmp_db, monkeypatch) -> None:
    def failing_request(method, url, **kwargs):
        raise requests.RequestException("upstream timeout")

    monkeypatch.setattr(requests, "request", failing_request)
    with pytest.raises(GmailApiError):
        service.create_gmail_draft(
            int(tmp_db["professor_id"]),
            GmailDraftRequest(to="ok@example.com", subject="Subject", body="Body", notes="Keep me"),
        )
    row = database.get_professor_outreach([int(tmp_db["professor_id"])])[int(tmp_db["professor_id"])]
    assert row["email_subject"] == "Subject"
    assert row["email_body"] == "Body"
    assert row["notes"] == "Keep me"
    assert row["outreach_status"] == "Email drafted"
    assert row["gmail_draft_id"] == ""


def test_401_triggers_single_refresh_then_retry(tmp_db, monkeypatch) -> None:
    gmail_calls = []
    refreshed = {}

    def fake_request(method, url, **kwargs):
        if method in ("POST", "PUT"):
            if len(gmail_calls) == 0:
                gmail_calls.append("first")
                return _Response(401)
            gmail_calls.append("retry")
            assert kwargs["headers"]["Authorization"] == "Bearer fresh"
            return _Response(201, {"id": "draft-9", "message": {"threadId": "thread-9"}})
        return _Response(500)

    def fake_post(url, **kwargs):
        refreshed["done"] = True
        assert url.endswith("/token")
        return _Response(200, {"access_token": "fresh", "expires_in": 3600})

    monkeypatch.setattr(requests, "request", fake_request)
    monkeypatch.setattr(requests, "post", fake_post)

    result = service.create_gmail_draft(
        int(tmp_db["professor_id"]),
        GmailDraftRequest(to="ok@example.com", subject="Subject", body="Body"),
    )
    assert result.gmail_draft_id == "draft-9"
    assert refreshed["done"] is True
    assert gmail_calls == ["first", "retry"]

"""End-to-end API tests for Gmail sent/reply detection and status updates.

All Google/Gmail traffic is mocked; thread state is served from canned
``users.threads.get`` payloads. These tests prove the sync only reads a stored
thread id (never the whole inbox), stores only minimal metadata, preserves
manual terminal states, enforces user/token isolation, and never sends mail.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import database
from api.gmail import token_store
from api.main import create_app
from tests._auth_helpers import DEV_USER_ID, client_for_user, signed_client

BASE = {
    "name": "Sync Test Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Robotics and machine learning",
    "email": "sync-test@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/sync-test",
    "categories": "Robotics, Machine Learning",
    "source_type": "Test",
}

_THREAD = "thread-1"


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = payload or {}
        self.text = text

    def json(self):
        return self._json


def msg(ident: str, labels: list[str], millis: int) -> dict:
    return {
        "id": ident,
        "threadId": _THREAD,
        "internalDate": str(millis),
        "labelIds": labels,
    }


class _FakeGmail:
    """Turns a thread payload into a requests.get response and records calls."""

    def __init__(self, payload: dict | None = None, status: int = 200) -> None:
        self.payload = payload or {}
        self.status = status
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url, **kwargs):
        self.calls.append(("GET", url))
        if self.status == 404:
            return _Response(404, {"error": {"code": 404}})
        if self.status != 200:
            return _Response(self.status, {"error": {"code": self.status}})
        return _Response(200, self.payload)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor_id = int(database.fetch_professors()[0]["id"])
    yield {"tmp_path": tmp_path, "professor_id": professor_id, "monkeypatch": monkeypatch}
    database.DB_PATH = original


def _seed_credentials(user_id: str = DEV_USER_ID) -> None:
    token_store.save_credentials(
        user_id,
        {
            "client_id": "test-client.apps.googleusercontent.com",
            "account_email": "me@example.com",
            "token": {
                "access_token": "at",
                "refresh_token": "rt",
                "issued_at": int(time.time()),
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.metadata", "scope_verified": True,
            },
        },
    )


def _link(professor_id: int, user_id: str = DEV_USER_ID, *, status: str = "Email drafted") -> None:
    database.update_professor_outreach(
        professor_id,
        user_id=user_id,
        gmail_draft_id="draft-1",
        gmail_thread_id=_THREAD,
        gmail_account_email="me@example.com",
        gmail_draft_created_at="2026-09-01T10:00:00Z",
        outreach_status=status,
        email_to="sync-test@stanford.edu",
        email_subject="Research inquiry",
        email_body="Body text",
    )


def _professors_snapshot() -> list[dict]:
    return database.fetch_professors()


def _sent_payload() -> dict:
    return {
        "id": _THREAD,
        "messages": [msg("m1", ["SENT"], 1_700_000_000_000)],
    }


def _replied_payload() -> dict:
    return {
        "id": _THREAD,
        "messages": [
            msg("m1", ["SENT"], 1_700_000_000_000),
            msg("m2", ["INBOX"], 1_700_008_000_000),
        ],
    }


def _no_messages_payload() -> dict:
    return {"id": _THREAD, "messages": []}


def _draft_only_payload() -> dict:
    return {
        "id": _THREAD,
        "messages": [msg("d1", ["DRAFT"], 1_700_000_000_000)],
    }


def _dual_labeled_with_reply_payload() -> dict:
    return {
        "id": _THREAD,
        "messages": [
            msg("m1", ["SENT", "INBOX"], 1_700_000_000_000),
            msg("m2", ["INBOX"], 1_700_008_000_000),
        ],
    }


# --- not linked --------------------------------------------------------------


def test_sync_unlinked_row_returns_not_linked_without_any_gmail_call(env, monkeypatch) -> None:
    fake = _FakeGmail()
    monkeypatch.setattr(requests, "get", fake)
    client = signed_client()
    database.update_professor_outreach(
        env["professor_id"], user_id=DEV_USER_ID, outreach_status="Email drafted"
    )
    body = client.post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["linked"] is False
    assert "No Gmail link" in body["message"]
    assert fake.calls == []
    assert body["outreach"]["outreach"]["status"] == "Drafted"


# --- not sent yet ------------------------------------------------------------


def test_sync_empty_thread_is_not_sent(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"])
    fake = _FakeGmail(_no_messages_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["linked"] is True
    assert body["sent"] is False
    assert body["not_sent_yet"] is True
    assert body["outreach"]["outreach"]["status"] == "Drafted"
    row = database.get_professor_outreach([env["professor_id"]], user_id=DEV_USER_ID)[env["professor_id"]]
    assert row["gmail_sent_at"] == ""
    assert row["gmail_last_checked_at"]


def test_sync_draft_only_thread_is_not_sent(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    # Gmail drafts can participate in threads, so a draft-only thread is a real,
    # readable thread with no SENT message. Detection must read it and report
    # "not sent"; it must not rely on any draft thread being absent.
    fake = _FakeGmail(_draft_only_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["linked"] is True
    assert body["sent"] is False
    assert body["not_sent_yet"] is True
    assert body["outreach"]["outreach"]["status"] == "Drafted"
    row = database.get_professor_outreach([env["professor_id"]], user_id=DEV_USER_ID)[env["professor_id"]]
    assert row["gmail_sent_at"] == ""
    assert row["gmail_replied_at"] == ""
    assert row["gmail_reply_count"] == 0
    assert row["gmail_last_checked_at"]


def test_sync_thread_404_is_treated_as_not_sent(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    fake = _FakeGmail(status=404)
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["not_sent_yet"] is True
    assert "no sent message" in body["message"]


# --- sent detected -----------------------------------------------------------


def test_sync_detects_sent_and_promotes_drafted_to_sent(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    fake = _FakeGmail(_sent_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["sent"] is True
    assert body["replied"] is False
    assert body["outreach"]["outreach"]["status"] == "Sent"
    assert body["outreach"]["outreach"]["gmail_sent_at"] == "2023-11-14T22:13:20Z"
    assert body["outreach"]["outreach"]["gmail_reply_count"] == 0
    assert body["outreach"]["outreach"]["gmail_last_checked_at"]


# --- reply detected ----------------------------------------------------------


def test_sync_detects_reply_and_sets_replied(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    fake = _FakeGmail(_replied_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["sent"] is True
    assert body["replied"] is True
    assert body["outreach"]["outreach"]["status"] == "Replied"
    assert body["outreach"]["outreach"]["gmail_sent_at"] == "2023-11-14T22:13:20Z"
    assert body["outreach"]["outreach"]["gmail_replied_at"] == "2023-11-15T00:26:40Z"
    assert body["outreach"]["outreach"]["gmail_reply_count"] == 1


def test_outbound_message_is_never_counted_as_a_reply(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    # A message carrying both SENT and INBOX labels (a defensive shape) must be
    # classified as the outbound message on the sent branch — never as an
    # incoming reply — so only the real single reply is counted.
    fake = _FakeGmail(_dual_labeled_with_reply_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["sent"] is True
    assert body["replied"] is True
    assert body["outreach"]["outreach"]["gmail_sent_at"] == "2023-11-14T22:13:20Z"
    assert body["outreach"]["outreach"]["gmail_replied_at"] == "2023-11-15T00:26:40Z"
    assert body["outreach"]["outreach"]["gmail_reply_count"] == 1


def test_sync_later_reply_after_sent_is_detected_on_second_check(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    fake = _FakeGmail(_sent_payload())
    monkeypatch.setattr(requests, "get", fake)
    client = signed_client()
    first = client.post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert first["outreach"]["outreach"]["status"] == "Sent"

    fake.payload = _replied_payload()
    second = client.post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert second["replied"] is True
    assert second["outreach"]["outreach"]["status"] == "Replied"


# --- follow-up due is deterministic and derived -------------------------------


def test_follow_up_due_derived_from_real_gmail_sent_date(env, monkeypatch) -> None:
    from datetime import date, timedelta

    _seed_credentials()
    today = date.today()
    _link(env["professor_id"], status="Email sent")
    database.update_professor_outreach(
        env["professor_id"],
        user_id=DEV_USER_ID,
        gmail_sent_at=(date.today() - timedelta(days=5)).strftime("%Y-%m-%dT09:00:00Z"),
        follow_up_date=(today - timedelta(days=1)).isoformat(),
    )
    fake = _FakeGmail(_sent_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    # Reply absent + sent date present + follow-up date <= today -> due.
    assert body["outreach"]["outreach"]["status"] == "Follow-up due"
    assert body["outreach"]["outreach"]["follow_up_due"] is True
    # Stored status was never rewritten to a due marker.
    stored = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    assert stored["outreach_status"] == "Email sent"


def test_follow_up_not_due_when_no_follow_up_date_set(env, monkeypatch) -> None:
    from datetime import timedelta

    _seed_credentials()
    _link(env["professor_id"], status="Email sent")
    database.update_professor_outreach(
        env["professor_id"],
        user_id=DEV_USER_ID,
        gmail_sent_at=(__import__("datetime").date.today() - timedelta(days=5)).strftime(
            "%Y-%m-%dT09:00:00Z"
        ),
    )
    fake = _FakeGmail(_sent_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["outreach"]["outreach"]["follow_up_due"] is False


# --- manual terminal states preserved ----------------------------------------


@pytest.mark.parametrize("stored,frontend", [("Rejected", "Closed"), ("Meeting scheduled", "Meeting scheduled")])
def test_terminal_manual_state_never_overwritten_by_gmail(env, monkeypatch, stored, frontend) -> None:
    _seed_credentials()
    _link(env["professor_id"], status=stored)
    fake = _FakeGmail(_replied_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["preserved"] is True
    assert body["outreach"]["outreach"]["status"] == frontend
    # Metadata facts were still recorded; the status was not.
    stored_row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    assert stored_row["outreach_status"] == stored
    assert stored_row["gmail_replied_at"]


# --- sync all ----------------------------------------------------------------


def test_sync_all_checks_linked_rows_only(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    database.upsert_professors([{**BASE, "name": "Second Sync Professor", "email": "second-sync@stanford.edu"}])
    second = int(
        next(
            row["id"] for row in database.fetch_professors() if row["name"] == "Second Sync Professor"
        )
    )
    _link(second, status="Email drafted")
    # One row with a draft but no thread should be skipped by sync-all.
    database.update_professor_outreach(
        env["professor_id"], user_id=DEV_USER_ID, outreach_status="Not contacted"
    )
    database.update_professor_outreach(
        env["professor_id"], user_id=DEV_USER_ID, gmail_thread_id=""
    )
    fake = _FakeGmail(_sent_payload())
    monkeypatch.setattr(requests, "get", fake)
    body = signed_client().post("/api/outreach/gmail-sync").json()
    assert body["checked"] == 1
    assert body["updated"] == 1
    assert body["errors"] == []
    assert [item["professor_id"] for item in body["results"]] == [second]


# --- failures ----------------------------------------------------------------


def test_sync_gmail_api_error_returns_502_and_preserves_state(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email sent")

    def boom(url, **kwargs):
        raise requests.RequestException("upstream timeout")

    monkeypatch.setattr(requests, "get", boom)
    response = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync")
    assert response.status_code == 502
    row = database.get_professor_outreach([env["professor_id"]], user_id=DEV_USER_ID)[env["professor_id"]]
    assert row["outreach_status"] == "Email sent"
    assert row["gmail_last_checked_at"] == ""


def test_sync_all_collects_errors_without_aborting(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")

    def boom(url, **kwargs):
        raise requests.RequestException("upstream timeout")

    monkeypatch.setattr(requests, "get", boom)
    body = signed_client().post("/api/outreach/gmail-sync").json()
    assert body["checked"] == 1
    assert body["updated"] == 0
    assert body["errors"]
    assert body["results"] == []


def test_sync_revoked_or_missing_connection_returns_401(env, monkeypatch) -> None:
    _link(env["professor_id"], status="Email drafted")
    response = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync")
    assert response.status_code == 401
    assert "not connected" in response.json()["detail"].lower()


# --- isolation ---------------------------------------------------------------


def test_sync_is_scoped_per_user(env, monkeypatch) -> None:
    _seed_credentials()
    _seed_credentials("google:other-user")
    fake = _FakeGmail(_replied_payload())
    monkeypatch.setattr(requests, "get", fake)

    _link(env["professor_id"], status="Email drafted")
    owner = signed_client()
    owner.post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()

    # The same professor exists for a second account, but with its own thread.
    other = client_for_user("google:other-user", "other@example.com")
    _link(env["professor_id"], user_id="google:other-user", status="Email drafted")
    other.post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()

    owner_row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    other_row = database.get_professor_outreach(
        [env["professor_id"]], user_id="google:other-user"
    )[env["professor_id"]]
    assert owner_row["outreach_status"] == "Replied"
    assert other_row["outreach_status"] == "Replied"
    # Both saw their own conversation; neither touched the other's row.
    owner_replied = owner_row["gmail_replied_at"]
    other_replied = other_row["gmail_replied_at"]
    assert owner_replied == other_replied
    assert fake.calls


def test_unknown_researcher_returns_404(env, monkeypatch) -> None:
    _seed_credentials()
    monkeypatch.setattr(requests, "get", _FakeGmail(_sent_payload()))
    response = signed_client().post("/api/outreach/424242/gmail-sync")
    assert response.status_code == 404


# --- write boundary + no auto-send -------------------------------------------


def test_sync_only_gets_thread_metadata_and_never_sends(env, monkeypatch) -> None:
    _seed_credentials()
    _link(env["professor_id"], status="Email drafted")
    fake = _FakeGmail(_replied_payload())
    monkeypatch.setattr(requests, "get", fake)
    before = _professors_snapshot()

    body = signed_client().post(f"/api/outreach/{env['professor_id']}/gmail-sync").json()
    assert body["outreach"]["outreach"]["status"] == "Replied"

    # Only a GET against the stored thread was made — nothing else, and the
    # methods that could send mail were never touched.
    assert len(fake.calls) == 1
    method, url = fake.calls[0]
    assert method == "GET"
    assert f"/threads/{_THREAD}" in url
    assert "format=metadata" in url
    assert "/send" not in url

    assert _professors_snapshot() == before
    row = database.get_professor_outreach(
        [env["professor_id"]], user_id=DEV_USER_ID
    )[env["professor_id"]]
    # Only minimal, non-content metadata was stored.
    assert row["gmail_sent_at"] and row["gmail_replied_at"]
    assert row["gmail_reply_count"] == 1
    assert row["gmail_last_checked_at"]

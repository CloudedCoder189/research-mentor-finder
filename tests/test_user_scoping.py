"""End-to-end proof that saved/outreach/profile/Gmail state is user-scoped.

Two distinct accounts (Alice, Bob) exercise the same API surface; neither can
see or mutate the other's data, and the ``professors`` table stays untouched.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import database
from api.gmail import token_store
from tests._auth_helpers import client_for_user

ALICE = "google:alice"
BOB = "google:bob"

BASE = {
    "name": "Scoping Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Isolation testing",
    "email": "scoping@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/scoping",
    "categories": "Machine Learning",
    "source_type": "Test",
}


def _env(tmp_path: Path, monkeypatch) -> dict:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "gmail_tokens"))
    professor_id = int(database.fetch_professors()[0]["id"])
    return {
        "professor_id": professor_id,
        "tmp_path": tmp_path,
        "restore": lambda: setattr(database, "DB_PATH", original),
    }


def test_saved_and_outreach_are_isolated(tmp_path: Path, monkeypatch) -> None:
    env = _env(tmp_path, monkeypatch)
    try:
        alice = client_for_user(ALICE, "alice@example.com")
        bob = client_for_user(BOB, "bob@example.com")
        pid = env["professor_id"]

        assert alice.post(f"/api/saved/{pid}").status_code == 200
        alice.patch(
            f"/api/outreach/{pid}",
            json={"outreach_status": "Sent", "email_sent_at": "2026-08-01", "notes": "Alice note"},
        )

        assert alice.get("/api/saved").json()["total"] == 1
        assert bob.get("/api/saved").json()["total"] == 0

        alice_outreach = alice.get(f"/api/outreach/{pid}").json()["outreach"]
        assert alice_outreach["status"] == "Sent"
        assert alice_outreach["notes"] == "Alice note"

        bob_outreach = bob.get(f"/api/outreach/{pid}").json()["outreach"]
        assert bob_outreach["status"] == "Not contacted"
        assert bob_outreach["notes"] == ""
        assert bob_outreach["is_favorite"] is False

        # Bob's mutations never affect Alice's row.
        bob.patch(f"/api/outreach/{pid}", json={"notes": "Bob note", "outreach_status": "Replied"})
        assert bob.get(f"/api/outreach/{pid}").json()["outreach"]["notes"] == "Bob note"
        alice_row = alice.get(f"/api/outreach/{pid}").json()["outreach"]
        assert alice_row["notes"] == "Alice note"
        assert alice_row["status"] == "Sent"
    finally:
        env["restore"]()


def test_gmail_credentials_are_isolated(tmp_path: Path, monkeypatch) -> None:
    env = _env(tmp_path, monkeypatch)
    try:
        alice = client_for_user(ALICE, "alice@example.com")
        bob = client_for_user(BOB, "bob@example.com")

        token_store.save_credentials(
            ALICE,
            {
                "client_id": "test-client.apps.googleusercontent.com",
                "account_email": "alice@example.com",
                "token": {
                    "access_token": "at",
                    "refresh_token": "rt",
                    "issued_at": int(time.time()),
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.metadata", "scope_verified": True,
                },
            },
        )

        alice_status = alice.get("/api/gmail/status").json()
        assert alice_status["connected"] is True
        assert alice_status["account_email"] == "alice@example.com"

        bob_status = bob.get("/api/gmail/status").json()
        assert bob_status["connected"] is False
        assert bob_status["account_email"] == ""
    finally:
        env["restore"]()


def test_professors_table_untouched_by_user_activity(tmp_path: Path, monkeypatch) -> None:
    env = _env(tmp_path, monkeypatch)
    try:
        alice = client_for_user(ALICE, "alice@example.com")
        pid = env["professor_id"]
        before = database.fetch_professors()
        alice.post(f"/api/saved/{pid}")
        alice.patch(f"/api/outreach/{pid}", json={"notes": "xyz", "outreach_status": "Replied"})
        assert database.fetch_professors() == before
    finally:
        env["restore"]()

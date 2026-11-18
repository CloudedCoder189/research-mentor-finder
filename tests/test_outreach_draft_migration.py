"""Data-layer tests for the Phase 4 outreach draft columns and favorites-safe
partial updates.

These tests verify the additive ``email_to`` / ``email_subject`` /
``email_body`` migration (backup + baseline + professors-table integrity), and
that ``update_professor_outreach`` never touches fields it was not asked to
change (especially ``is_favorite`` and existing draft history).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

import database
from api.schemas.user_state import (
    FRONTEND_STATUS_BY_STORED,
    STORED_STATUS_BY_FRONTEND,
    frontend_status,
    follow_up_due,
)

BASE = {
    "name": "Migration Test Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and robotics",
    "email": "migration-test@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/migration-test",
    "categories": "Machine Learning, Robotics",
    "source_type": "Test",
}


def _use_db(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    return original


def test_outreach_draft_migration_legacy_db(tmp_path: Path) -> None:
    """A v9.6-shaped database (no draft columns) upgrades safely with a backup."""
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        # Build a real database, then downgrade its outreach table to the legacy
        # v9.6 shape (composite user PK, no email draft columns) plus a marker.
        with database.connect() as connection:
            connection.executescript(database.SCHEMA)
            connection.executescript(
                """
                DROP TABLE professor_outreach;
                CREATE TABLE IF NOT EXISTS professor_outreach (
                    user_id TEXT NOT NULL,
                    professor_id INTEGER NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 0
                        CHECK (is_favorite IN (0, 1)),
                    notes TEXT NOT NULL DEFAULT '',
                    outreach_status TEXT NOT NULL DEFAULT 'Not contacted',
                    email_sent_at TEXT NOT NULL DEFAULT '',
                    follow_up_date TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, professor_id),
                    FOREIGN KEY (professor_id) REFERENCES professors(id)
                        ON DELETE CASCADE
                );
                INSERT INTO app_migrations (migration_key, details)
                VALUES ('v9.6-outreach-user-scoping', 'outreach rows scoped');
                """
            )
        database.upsert_professors([BASE])
        professor_id = int(
            database.fetch_professors()[0]["id"]
        )
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO professor_outreach ("
                " user_id, professor_id, is_favorite, notes, outreach_status"
                ") VALUES ('local-owner', ?, 1, 'Existing note', 'Email sent')",
                (professor_id,),
            )

        database.initialize_database()

        with database.connect() as connection:
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(professor_outreach)"
                ).fetchall()
            }
            professor_total = int(
                connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
            )
            row = connection.execute(
                "SELECT * FROM professor_outreach WHERE professor_id = ?",
                (professor_id,),
            ).fetchone()
            marker = connection.execute(
                "SELECT 1 FROM app_migrations WHERE migration_key = ?",
                (database.OUTREACH_DRAFT_MIGRATION_KEY,),
            ).fetchone()
        assert "email_to" in columns
        assert "email_subject" in columns
        assert "email_body" in columns
        assert professor_total == 1
        assert marker is not None
        assert dict(row)["notes"] == "Existing note"
        assert dict(row)["is_favorite"] == 1
        assert dict(row)["outreach_status"] == "Email sent"
        assert dict(row)["email_subject"] == ""

        # This fixture predates the draft-column and Gmail-metadata migrations,
        # so at least one backup is produced; the point is that re-running does
        # not create more.
        backups = list(tmp_path.glob("*.bak"))
        assert len(backups) >= 1
        after_migrations = len(backups)

        # Re-running initialization is a no-op: no extra backups, no data loss.
        database.initialize_database()
        assert len(list(tmp_path.glob("*.bak"))) == after_migrations
    finally:
        database.DB_PATH = original


def test_update_professor_outreach_preserves_unmodified_fields(tmp_path: Path) -> None:
    original = _use_db(tmp_path)
    try:
        professor_id = int(database.fetch_professors()[0]["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email drafted",
            notes="Notes v1",
            email_subject="Subject v1",
            email_body="Body v1",
        )
        database.update_professor_outreach(professor_id, notes="Notes v2")
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["notes"] == "Notes v2"
        assert outreach["is_favorite"] == 1
        assert outreach["outreach_status"] == "Email drafted"
        assert outreach["email_subject"] == "Subject v1"
        assert outreach["email_body"] == "Body v1"

        database.update_professor_outreach(professor_id, outreach_status="Replied")
        after = database.get_professor_outreach([professor_id])[professor_id]
        assert after["outreach_status"] == "Replied"
        assert after["notes"] == "Notes v2"
        assert after["is_favorite"] == 1
    finally:
        database.DB_PATH = original


def test_update_professor_outreach_creates_row_without_favorite(tmp_path: Path) -> None:
    original = _use_db(tmp_path)
    try:
        professor_id = int(database.fetch_professors()[0]["id"])
        row = database.update_professor_outreach(professor_id, notes="Just notes.")
        assert row["is_favorite"] == 0
        assert row["outreach_status"] == "Not contacted"
        assert row["notes"] == "Just notes."
        assert database.favorite_professor_ids() == set()
    finally:
        database.DB_PATH = original


def test_update_professor_outreach_validations(tmp_path: Path) -> None:
    original = _use_db(tmp_path)
    try:
        professor_id = int(database.fetch_professors()[0]["id"])
        with pytest.raises(ValueError, match="valid outreach status"):
            database.update_professor_outreach(professor_id, outreach_status="Maybe")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            database.update_professor_outreach(professor_id, email_sent_at="July 28")
        with pytest.raises(ValueError, match="not found"):
            database.update_professor_outreach(999999, notes="x")
    finally:
        database.DB_PATH = original


def test_update_professor_outreach_can_clear_dates(tmp_path: Path) -> None:
    original = _use_db(tmp_path)
    try:
        professor_id = int(database.fetch_professors()[0]["id"])
        database.update_professor_outreach(
            professor_id,
            outreach_status="Email sent",
            email_sent_at="2026-07-28",
            follow_up_date="2026-08-04",
        )
        database.update_professor_outreach(professor_id, follow_up_date="")
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["follow_up_date"] == ""
        assert outreach["email_sent_at"] == "2026-07-28"
    finally:
        database.DB_PATH = original


def test_status_mapping_round_trips_stored_values(tmp_path: Path) -> None:
    assert set(FRONTEND_STATUS_BY_STORED) == set(database.OUTREACH_STATUSES)
    for stored, frontend in FRONTEND_STATUS_BY_STORED.items():
        assert STORED_STATUS_BY_FRONTEND[frontend] == stored


def test_follow_up_derivation_is_deterministic(tmp_path: Path) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()
    sent_week_ago = (date.today() - timedelta(days=7)).isoformat()

    overdue_sent = {
        "outreach_status": "Email sent",
        "email_sent_at": sent_week_ago,
        "follow_up_date": yesterday,
    }
    future_sent = {
        "outreach_status": "Email sent",
        "email_sent_at": sent_week_ago,
        "follow_up_date": next_week,
    }
    explicit = {"outreach_status": "Follow-up needed", "follow_up_date": ""}
    replied = {
        "outreach_status": "Replied",
        "email_sent_at": sent_week_ago,
        "follow_up_date": yesterday,
    }

    assert frontend_status(overdue_sent) == "Follow-up due"
    assert follow_up_due(overdue_sent) is True
    assert frontend_status(future_sent) == "Sent"
    assert follow_up_due(future_sent) is False
    assert frontend_status(explicit) == "Follow-up due"
    assert follow_up_due(explicit) is True
    assert frontend_status(replied) == "Replied"
    assert follow_up_due(replied) is False


def test_write_boundary_professors_table_untouched(tmp_path: Path) -> None:
    original = _use_db(tmp_path)
    try:
        professor_id = int(database.fetch_professors()[0]["id"])
        before = database.fetch_professors()
        database.set_professor_favorite(professor_id, True)
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email drafted",
            email_subject="S",
            email_body="B",
        )
        database.update_professor_outreach(professor_id, outreach_status="Replied")
        database.set_professor_favorite(professor_id, False)
        assert database.fetch_professors() == before
    finally:
        database.DB_PATH = original
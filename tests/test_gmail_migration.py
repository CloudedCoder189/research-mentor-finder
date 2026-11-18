"""Data-layer tests for the v9.8 Gmail draft-metadata migration.

Proves the additive ``gmail_*`` columns upgrade safely on a legacy database:
backup before altering, professors-table integrity, existing outreach rows
preserved, marker recorded, and re-runs are no-ops.
"""

from __future__ import annotations

from pathlib import Path

import database


def test_gmail_columns_migration_legacy_db(tmp_path: Path) -> None:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        # Build a real database, then downgrade its outreach table to the
        # v9.7 shape (user-scoped + draft columns, but no Gmail metadata).
        with database.connect() as connection:
            connection.executescript(database.SCHEMA)
            connection.executescript(
                """
                DROP TABLE professor_outreach;
                CREATE TABLE professor_outreach (
                    user_id TEXT NOT NULL,
                    professor_id INTEGER NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 0
                        CHECK (is_favorite IN (0, 1)),
                    notes TEXT NOT NULL DEFAULT '',
                    outreach_status TEXT NOT NULL DEFAULT 'Not contacted',
                    email_sent_at TEXT NOT NULL DEFAULT '',
                    follow_up_date TEXT NOT NULL DEFAULT '',
                    email_to TEXT NOT NULL DEFAULT '',
                    email_subject TEXT NOT NULL DEFAULT '',
                    email_body TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, professor_id),
                    FOREIGN KEY (professor_id) REFERENCES professors(id)
                        ON DELETE CASCADE
                );
                INSERT INTO app_migrations (migration_key, details)
                VALUES ('v9.7-outreach-draft-columns', 'draft columns added');
                """
            )
        database.upsert_professors([{"name": "Gmail Migration Professor",
                                     "university": "Stanford University",
                                     "department": "Computer Science",
                                     "title": "Assistant Professor",
                                     "research_interests": "Robotics",
                                     "email": "migration@stanford.edu",
                                     "website_url": "https://example.org/lab",
                                     "profile_url": "https://profiles.stanford.edu/x",
                                     "categories": "Robotics",
                                     "source_type": "Test"}])
        professor_id = int(database.fetch_professors()[0]["id"])
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO professor_outreach ("
                " user_id, professor_id, is_favorite, notes, outreach_status"
                ") VALUES ('local-owner', ?, 1, 'Existing outreach note', 'Email sent')",
                (professor_id,),
            )

        database.initialize_database()

        with database.connect() as connection:
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
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
                (database.GMAIL_MIGRATION_KEY,),
            ).fetchone()
        for column in ("gmail_draft_id", "gmail_thread_id", "gmail_account_email", "gmail_draft_created_at"):
            assert column in columns
        assert professor_total == 1
        assert marker is not None
        assert dict(row)["notes"] == "Existing outreach note"
        assert dict(row)["is_favorite"] == 1
        assert dict(row)["outreach_status"] == "Email sent"
        assert dict(row)["gmail_draft_id"] == ""

        backups = list(tmp_path.glob("*.bak"))
        assert len(backups) >= 1
        after_migrations = len(backups)

        # Re-running initialization is a no-op: no extra backup, no data loss.
        database.initialize_database()
        assert len(list(tmp_path.glob("*.bak"))) == after_migrations
    finally:
        database.DB_PATH = original


def test_fresh_database_has_gmail_columns_without_backup(tmp_path: Path) -> None:
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        with database.connect() as connection:
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
            }
        for column in ("gmail_draft_id", "gmail_thread_id", "gmail_account_email", "gmail_draft_created_at"):
            assert column in columns
        assert list(tmp_path.glob("*.bak")) == []

        database.initialize_database()
        assert list(tmp_path.glob("*.bak")) == []
    finally:
        database.DB_PATH = original
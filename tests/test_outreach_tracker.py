from pathlib import Path

import pytest

import database


BASE = {
    "name": "Outreach Test Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and robotics",
    "email": "outreach-test@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/outreach-test",
    "categories": "Machine Learning, Robotics",
    "source_type": "Test",
}


def _use_db(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor = database.fetch_professors()[0]
    return original, professor


def test_v95_migration_creates_outreach_table(tmp_path: Path):
    original, _ = _use_db(tmp_path)
    try:
        with database.connect() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(professor_outreach)"
                ).fetchall()
            }
        assert "professor_outreach" in tables
        assert {
            "professor_id",
            "is_favorite",
            "notes",
            "outreach_status",
            "email_sent_at",
            "follow_up_date",
            "updated_at",
        }.issubset(columns)
    finally:
        database.DB_PATH = original


def test_shortlist_and_outreach_round_trip(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email sent",
            notes="Strong match for climate ML.",
            email_sent_at="2026-07-28",
            follow_up_date="2026-08-04",
        )
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["is_favorite"] == 1
        assert outreach["outreach_status"] == "Email sent"
        assert outreach["notes"] == "Strong match for climate ML."
        assert outreach["email_sent_at"] == "2026-07-28"
        assert outreach["follow_up_date"] == "2026-08-04"
        assert database.favorite_professor_ids() == {professor_id}

        tracked = database.fetch_outreach_professors(favorites_only=True)
        assert len(tracked) == 1
        assert tracked[0]["name"] == BASE["name"]
        assert tracked[0]["outreach_status"] == "Email sent"
    finally:
        database.DB_PATH = original


def test_favorite_toggle_preserves_notes_and_status(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email drafted",
            notes="Draft ready.",
        )
        database.set_professor_favorite(professor_id, False)
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["is_favorite"] == 0
        assert outreach["outreach_status"] == "Email drafted"
        assert outreach["notes"] == "Draft ready."
        assert database.favorite_professor_ids() == set()
        assert len(database.fetch_outreach_professors()) == 1
    finally:
        database.DB_PATH = original


def test_outreach_validation_rejects_bad_status_and_dates(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        with pytest.raises(ValueError, match="valid outreach status"):
            database.save_professor_outreach(
                professor_id,
                is_favorite=True,
                outreach_status="Maybe",
            )
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            database.save_professor_outreach(
                professor_id,
                is_favorite=True,
                outreach_status="Email sent",
                email_sent_at="July 28",
            )
    finally:
        database.DB_PATH = original


def test_outreach_counts_and_refresh_preservation(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Replied",
            notes="Asked to schedule a call.",
            email_sent_at="2026-07-20",
            follow_up_date="2026-07-25",
        )
        counts = database.outreach_counts()
        assert counts["shortlisted"] == 1
        assert counts["contacted"] == 1
        assert counts["positive_responses"] == 1
        assert counts["follow_ups_due"] == 0

        refreshed = dict(BASE)
        refreshed["title"] = "Associate Professor"
        database.upsert_professors([refreshed])
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["notes"] == "Asked to schedule a call."
        assert outreach["outreach_status"] == "Replied"
    finally:
        database.DB_PATH = original


def test_outreach_row_cascades_when_professor_is_pruned(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.set_professor_favorite(professor_id, True)
        retained = dict(BASE)
        retained.update(
            {
                "name": "Retained Professor",
                "email": "retained@stanford.edu",
                "profile_url": "https://profiles.stanford.edu/retained",
            }
        )
        database.upsert_professors([retained])
        removed = database.prune_university_records(
            "Stanford University", keep_emails=[retained["email"]]
        )
        assert removed == 1
        assert database.get_professor_outreach() == {}
    finally:
        database.DB_PATH = original

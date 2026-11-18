from pathlib import Path

import database
from services.admin_auth import admin_access_decision

BASE = {
    "name": "V952 Shortlist Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and climate",
    "email": "v952-shortlist@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/v952-shortlist",
    "categories": "Machine Learning",
    "source_type": "Test",
}


def _use_db(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([BASE])
    professor = database.fetch_professors()[0]
    return original, professor


def test_v952_shortlist_toggle_preserves_all_outreach_fields(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Follow-up needed",
            notes="Private note preserved.",
            email_sent_at="2026-08-01",
            follow_up_date="2026-08-15",
        )
        database.set_professor_favorite(professor_id, False)
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["is_favorite"] == 0
        assert outreach["notes"] == "Private note preserved."
        assert outreach["outreach_status"] == "Follow-up needed"
        assert outreach["email_sent_at"] == "2026-08-01"
        assert outreach["follow_up_date"] == "2026-08-15"
        assert database.favorite_professor_ids() == set()
    finally:
        database.DB_PATH = original


def test_v952_unfavorite_disappears_from_shortlist_only_view(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email drafted",
            notes="Draft remains tracked.",
        )
        assert len(database.fetch_outreach_professors(favorites_only=True)) == 1
        assert database.outreach_counts()["shortlisted"] == 1

        database.set_professor_favorite(professor_id, False)

        assert database.fetch_outreach_professors(favorites_only=True) == []
        trackable = database.fetch_outreach_professors(favorites_only=False)
        assert [int(row["id"]) for row in trackable] == [professor_id]
        counts = database.outreach_counts()
        assert counts["shortlisted"] == 0
        assert counts["tracked"] == 1
    finally:
        database.DB_PATH = original


def test_v952_refavorite_reappears_in_shortlist_view_without_losing_fields(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=False,
            outreach_status="Replied",
            notes="Keep notes across repeated toggles.",
            email_sent_at="2026-07-10",
            follow_up_date="2026-07-17",
        )
        database.set_professor_favorite(professor_id, True)
        shortlist = database.fetch_outreach_professors(favorites_only=True)
        assert [int(row["id"]) for row in shortlist] == [professor_id]
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["outreach_status"] == "Replied"
        assert outreach["notes"] == "Keep notes across repeated toggles."
        assert outreach["email_sent_at"] == "2026-07-10"
        assert outreach["follow_up_date"] == "2026-07-17"
        assert database.outreach_counts()["shortlisted"] == 1
    finally:
        database.DB_PATH = original


def test_v952_shortlist_editor_save_keeps_favorite_flag(tmp_path: Path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.set_professor_favorite(professor_id, True)
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Email sent",
            notes="Editor notes.",
            email_sent_at="2026-08-02",
            follow_up_date="2026-08-09",
        )
        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert outreach["is_favorite"] == 1
        assert outreach["outreach_status"] == "Email sent"
        assert outreach["notes"] == "Editor notes."
        assert outreach["email_sent_at"] == "2026-08-02"
        assert outreach["follow_up_date"] == "2026-08-09"
    finally:
        database.DB_PATH = original


def test_v952_admin_access_decision_fails_closed_in_public_without_password():
    assert admin_access_decision(public_mode=True, password_configured=False) == "fail_closed"
    assert admin_access_decision(public_mode=False, password_configured=False) == "auto_unlock"
    assert admin_access_decision(public_mode=True, password_configured=True) == "password"
    assert admin_access_decision(public_mode=False, password_configured=True) == "password"
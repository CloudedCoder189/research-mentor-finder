from pathlib import Path

import database
from services.search import rank_professors
from services.taxonomy import (
    NOT_AVAILABLE,
    infer_discipline,
    infer_field,
    infer_school_or_college,
    infer_subfield,
    infer_taxonomy,
)
from services.ui_helpers import filter_candidates

BASE = {
    "name": "V96 Test Professor",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning and climate modeling",
    "email": "v96-test@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/v96-test",
    "categories": "Machine Learning",
    "source_type": "Test",
}


def _use_db(tmp_path: Path, record=None):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    database.upsert_professors([record or BASE])
    professor = database.fetch_professors()[0]
    return original, professor


# ---------- Multi-user outreach scoping ----------


def test_v96_user_isolation_between_users(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        alice = "alice"
        bob = "bob"
        database.set_professor_favorite(professor_id, True, user_id=alice)
        database.save_professor_outreach(
            professor_id,
            user_id=bob,
            is_favorite=False,
            outreach_status="Email sent",
            notes="Bob's private note.",
        )
        assert database.favorite_professor_ids(user_id=alice) == {professor_id}
        assert database.favorite_professor_ids(user_id=bob) == set()
        assert database.favorite_professor_ids() == set()

        assert database.get_professor_outreach([professor_id], user_id=alice)[professor_id][
            "is_favorite"
        ] == 1
        bob_outreach = database.get_professor_outreach([professor_id], user_id=bob)[professor_id]
        assert bob_outreach["notes"] == "Bob's private note."
        assert database.get_professor_outreach([professor_id]) == {}

        assert len(database.fetch_outreach_professors(user_id=alice)) == 1
        tracked_bob = database.fetch_outreach_professors(user_id=bob)
        assert [int(row["id"]) for row in tracked_bob] == [professor_id]
        bob_counts = database.outreach_counts(user_id=bob)
        assert bob_counts["shortlisted"] == 0
        assert bob_counts["contacted"] == 1
        assert bob_counts["tracked"] == 1
        alice_counts = database.outreach_counts(user_id=alice)
        assert alice_counts["shortlisted"] == 1
        assert alice_counts["contacted"] == 0
    finally:
        database.DB_PATH = original


def test_v96_same_professor_kept_once_per_user(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        for _ in range(3):
            database.set_professor_favorite(professor_id, True, user_id="alice")
        for _ in range(2):
            database.set_professor_favorite(professor_id, True, user_id="bob")
        with database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM professor_outreach WHERE professor_id = ?",
                (professor_id,),
            ).fetchone()[0]
        assert count == 2
        assert database.favorite_professor_ids(user_id="alice") == {professor_id}
        assert database.favorite_professor_ids(user_id="bob") == {professor_id}
    finally:
        database.DB_PATH = original


def test_v96_legacy_outreach_migrated_to_default_user(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            is_favorite=True,
            outreach_status="Follow-up needed",
            notes="Kept verbatim.",
            email_sent_at="2026-08-01",
            follow_up_date="2026-08-15",
        )
        with database.connect() as connection:
            legacy = connection.execute(
                "SELECT professor_id, is_favorite, notes, outreach_status, "
                "email_sent_at, follow_up_date, updated_at FROM professor_outreach"
            ).fetchall()
            connection.execute("DROP TABLE professor_outreach")
            connection.execute(
                "CREATE TABLE professor_outreach ("
                " professor_id INTEGER PRIMARY KEY,"
                " is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),"
                " notes TEXT NOT NULL DEFAULT '',"
                " outreach_status TEXT NOT NULL DEFAULT 'Not contacted',"
                " email_sent_at TEXT NOT NULL DEFAULT '',"
                " follow_up_date TEXT NOT NULL DEFAULT '',"
                " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                " FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE"
                ")"
            )
            connection.executemany(
                "INSERT INTO professor_outreach VALUES (?, ?, ?, ?, ?, ?, ?)", legacy
            )

        database.initialize_database()

        outreach = database.get_professor_outreach([professor_id])[professor_id]
        assert database.DEFAULT_USER_ID == "local-owner"
        assert outreach["user_id"] == "local-owner"
        assert outreach["is_favorite"] == 1
        assert outreach["outreach_status"] == "Follow-up needed"
        assert outreach["notes"] == "Kept verbatim."
        assert outreach["email_sent_at"] == "2026-08-01"
        assert outreach["follow_up_date"] == "2026-08-15"
        assert database.favorite_professor_ids() == {professor_id}

        with database.connect() as connection:
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'professor_outreach'"
            ).fetchone()[0]
        assert "PRIMARY KEY (user_id, professor_id)" in sql
        assert "ON DELETE CASCADE" in sql

        # A second init must be a no-op: still one row, still the composite key.
        database.initialize_database()
        assert len(database.fetch_outreach_professors()) == 1
        with database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM professor_outreach"
            ).fetchone()[0]
        assert count == 1
    finally:
        database.DB_PATH = original


def test_v96_favorite_toggle_preserves_fields_for_any_user(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        database.save_professor_outreach(
            professor_id,
            user_id="carol",
            is_favorite=True,
            outreach_status="Email drafted",
            notes="Carol's draft.",
            email_sent_at="2026-08-05",
            follow_up_date="2026-08-12",
        )
        database.set_professor_favorite(professor_id, False, user_id="carol")
        outreach = database.get_professor_outreach([professor_id], user_id="carol")[professor_id]
        assert outreach["is_favorite"] == 0
        assert outreach["outreach_status"] == "Email drafted"
        assert outreach["notes"] == "Carol's draft."
        assert outreach["email_sent_at"] == "2026-08-05"
        assert outreach["follow_up_date"] == "2026-08-12"
        assert database.favorite_professor_ids(user_id="carol") == set()
    finally:
        database.DB_PATH = original


# ---------- Academic taxonomy ----------


def test_v96_taxonomy_inferrers_are_conservative():
    assert infer_field("Computer Science") == "Computer Science"
    assert infer_field("Computer Science; Psychology") == NOT_AVAILABLE
    assert infer_field("  Unmapped Department  ") == NOT_AVAILABLE
    assert infer_discipline("Computer Science") == "Computing"
    assert infer_discipline(NOT_AVAILABLE) == NOT_AVAILABLE
    assert infer_subfield("Reinforcement Learning, Machine Learning", "") == (
        "Reinforcement Learning"
    )
    assert infer_subfield("", "") == NOT_AVAILABLE
    assert infer_school_or_college("Stanford University") == "School of Engineering"
    assert infer_school_or_college("Mystery University") == NOT_AVAILABLE
    school, discipline, field, subfield = infer_taxonomy(
        university="University of California, San Diego",
        department="Bioengineering",
        categories="Robotics, Machine Learning",
    )
    assert school == "Jacobs School of Engineering"
    assert discipline == "Engineering"
    assert field == "Bioengineering"
    assert subfield == "Robotics"


def test_v96_taxonomy_backfill_known_and_missing(tmp_path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        known = dict(BASE)
        known.update(
            {
                "name": "Known Field Professor",
                "email": "known@stanford.edu",
                "profile_url": "https://profiles.stanford.edu/known-field",
                "categories": "Security & Privacy, Systems",
            }
        )
        joint = dict(BASE)
        joint.update(
            {
                "name": "Joint Appointment Professor",
                "email": "joint@stanford.edu",
                "profile_url": "https://profiles.stanford.edu/joint",
                "department": "Computer Science; Psychology",
                "categories": "Cognitive Science",
            }
        )
        unknown_univ = dict(BASE)
        unknown_univ.update(
            {
                "name": "Unknown University Professor",
                "university": "Mystery University",
                "email": "unknown@example.org",
                "profile_url": "https://example.org/unknown",
                "categories": "Theory",
            }
        )
        bio = dict(BASE)
        bio.update(
            {
                "name": "Bioengineering Professor",
                "university": "University of California, San Diego",
                "department": "Bioengineering",
                "email": "bio@ucsd.edu",
                "profile_url": "https://cse.ucsd.edu/bio",
                "categories": "Machine Learning",
            }
        )
        database.upsert_professors([known, joint, unknown_univ, bio])

        by_name = {str(r["name"]): r for r in database.fetch_professors()}
        assert by_name["Known Field Professor"]["school_or_college"] == "School of Engineering"
        assert by_name["Known Field Professor"]["discipline"] == "Computing"
        assert by_name["Known Field Professor"]["field"] == "Computer Science"
        assert by_name["Known Field Professor"]["subfield"] == "Security & Privacy"
        assert by_name["Joint Appointment Professor"]["field"] == NOT_AVAILABLE
        assert by_name["Joint Appointment Professor"]["discipline"] == NOT_AVAILABLE
        assert by_name["Unknown University Professor"]["school_or_college"] == NOT_AVAILABLE
        assert by_name["Unknown University Professor"]["field"] == "Computer Science"
        assert by_name["Bioengineering Professor"]["school_or_college"] == (
            "Jacobs School of Engineering"
        )
        assert by_name["Bioengineering Professor"]["discipline"] == "Engineering"
        assert by_name["Bioengineering Professor"]["field"] == "Bioengineering"

        assert len(database.list_disciplines()) >= 2
        assert len(database.list_fields()) >= 2
    finally:
        database.DB_PATH = original


def test_v96_taxonomy_maintenance_never_touches_embeddings(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        with database.connect() as connection:
            connection.execute(
                "UPDATE professors SET embedding_json = ?, embedding_model = ?, "
                "ai_summary = ?, ai_categories = ? WHERE id = ?",
                ("[0.1,0.2,0.3]", "test-model", "AI summary text.", "Machine Learning", professor_id),
            )
        before = database.fetch_professors()[0]
        embeddings_before = before["embedding_json"]
        model_before = before["embedding_model"]
        summary_before = before["ai_summary"]
        ai_categories_before = before["ai_categories"]

        database.update_verification_results(
            [{"professor_id": professor_id, "status": "Verified", "issues": "None"}]
        )

        after = database.fetch_professors()[0]
        assert after["embedding_json"] == embeddings_before
        assert after["embedding_model"] == model_before
        assert after["ai_summary"] == summary_before
        assert after["ai_categories"] == ai_categories_before
        assert after["verification_status"] == "Verified"
        assert after["discipline"] == "Computing"
        assert after["field"] == "Computer Science"
    finally:
        database.DB_PATH = original


def test_v96_filters_by_discipline_and_field(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        with database.connect() as connection:
            connection.execute(
                "UPDATE professors SET discipline = 'Engineering', field = 'Bioengineering' "
                "WHERE id = ?",
                (professor_id,),
            )
        records = [r for r in database.fetch_professors() if int(r["id"]) == professor_id]

        assert filter_candidates(records) == records
        assert len(filter_candidates(records, discipline_filter="Engineering")) == 1
        assert filter_candidates(records, discipline_filter="Computing") == []
        assert len(filter_candidates(records, field_filter="Bioengineering")) == 1
        assert filter_candidates(records, field_filter="Computer Science") == []
        assert filter_candidates(
            records, discipline_filter="Engineering", field_filter="Computer Science"
        ) == []
    finally:
        database.DB_PATH = original


def test_broad_field_category_matches_discipline(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        professor_id = int(professor["id"])
        with database.connect() as connection:
            connection.execute(
                "UPDATE professors SET discipline = 'Computing', field = 'Computer Science' "
                "WHERE id = ?",
                (professor_id,),
            )
        records = [r for r in database.fetch_professors() if int(r["id"]) == professor_id]

        # The home page offers broad categories that are discipline names.
        assert len(filter_candidates(records, field_filter="Computing")) == 1
        assert len(filter_candidates(records, field_filter="Engineering")) == 0
        # Concrete department fields keep matching the field column only.
        assert len(filter_candidates(records, field_filter="Computer Science")) == 1
        assert len(filter_candidates(records, field_filter="Bioengineering")) == 0
    finally:
        database.DB_PATH = original


def test_v96_search_still_works_with_taxonomy_fields(tmp_path):
    original, professor = _use_db(tmp_path)
    try:
        with database.connect() as connection:
            connection.execute(
                "UPDATE professors SET embedding_json = ?, embedding_model = ? "
                "WHERE id = ?",
                (
                    "[0.5,0.1,0.9]",
                    "test-model",
                    professor["id"],
                ),
            )
        base = {"query": "machine learning climate", "limit": 3}
        ranked = rank_professors(
            [r for r in database.fetch_professors() if int(r["id"]) == professor["id"]],
            base["query"],
            limit=base["limit"],
        )
        assert len(ranked) == 1
        assert int(ranked[0]["id"]) == int(professor["id"])
    finally:
        database.DB_PATH = original
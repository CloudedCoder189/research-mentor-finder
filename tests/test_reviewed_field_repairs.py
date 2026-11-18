import sqlite3

import pytest

import database
from scripts.stage_reviewed_field_repairs import apply_reviewed_repairs


@pytest.fixture
def staged():
    connection = sqlite3.connect(":memory:")
    connection.executescript(database.SCHEMA)
    # These columns are normally added by the app's schema migration.
    for column in ("school_or_college", "discipline", "field", "subfield"):
        connection.execute(f"ALTER TABLE professors ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    for record_id in (1, 2):
        connection.execute("""INSERT INTO professors
            (id, name, university, email, title, department, research_interests,
             embedding_json, embedding_model, embedding_source_hash, ai_summary,
             ai_categories, verification_status)
            VALUES (?, ?, 'University of California, Los Angeles', ?,
                'Expert Directory', 'Bioengineering', 'Machine learning',
                '[0.1]', 'test-model', 'old-hash', 'Old paid summary', 'Robotics', 'Verified')""",
            (record_id, f"Example Person {record_id}", f"example-{record_id}@example.edu"))
    connection.commit()
    yield connection
    connection.close()


def repair(record_id=1, field="title", old="Expert Directory", proposed="Assistant Professor"):
    return {"id": str(record_id), "name": f"Example Person {record_id}",
            "field": field, "old": old, "proposed": proposed,
            "source_url": "https://samueli.ucla.edu/people/example/",
            "status": "proposed_not_applied"}


def test_only_reviewed_record_changes_and_stale_enrichment_is_cleared(staged):
    unaffected = staged.execute("SELECT * FROM professors WHERE id = 2").fetchone()
    applied = apply_reviewed_repairs(staged, [repair(), repair(field="department", old="Bioengineering", proposed="Computer Science")])
    assert len(applied) == 1
    assert staged.execute("""SELECT title, department, embedding_json, embedding_model,
        embedding_source_hash, ai_summary, ai_categories, verification_status, field
        FROM professors WHERE id = 1""").fetchone() == (
        "Assistant Professor", "Computer Science", "", "", "", "", "", "Not checked", "Computer Science")
    assert staged.execute("SELECT * FROM professors WHERE id = 2").fetchone() == unaffected
    with pytest.raises(ValueError, match="no longer matches"):
        apply_reviewed_repairs(staged, [repair()])


def test_changed_research_regenerates_keyword_categories_without_provider_calls(staged):
    apply_reviewed_repairs(staged, [repair(field="research_interests", old="Machine learning", proposed="Natural language processing and machine learning")])
    categories = staged.execute("SELECT categories FROM professors WHERE id = 1").fetchone()[0]
    assert "Natural Language Processing" in categories
    assert "Machine Learning" in categories


def test_stale_manifest_is_rejected_before_any_update(staged):
    before = staged.execute("SELECT * FROM professors ORDER BY id").fetchall()
    with pytest.raises(ValueError, match="no longer matches"):
        apply_reviewed_repairs(staged, [repair(), repair(2, old="Unexpected title")])
    assert staged.execute("SELECT * FROM professors ORDER BY id").fetchall() == before


def test_database_failure_rolls_back_entire_batch(staged):
    before = staged.execute("SELECT * FROM professors ORDER BY id").fetchall()
    staged.execute("""CREATE TRIGGER reject_second BEFORE UPDATE ON professors
        WHEN NEW.id = 2 BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="simulated failure"):
        apply_reviewed_repairs(staged, [repair(), repair(2)])
    assert staged.execute("SELECT * FROM professors ORDER BY id").fetchall() == before


@pytest.mark.parametrize("field", ["email", "verification_status"])
def test_unreviewed_columns_cannot_be_written(staged, field):
    with pytest.raises(ValueError, match="unsupported"):
        apply_reviewed_repairs(staged, [repair(field=field)])


def test_reviewed_name_correction_preserves_record_id(staged):
    apply_reviewed_repairs(staged, [repair(field="name", old="Example Person 1", proposed="Example (Nickname) Person 1")])
    assert staged.execute("SELECT id, name, embedding_json FROM professors WHERE id = 1").fetchone() == (1, "Example (Nickname) Person 1", "")
    assert staged.execute("SELECT count(*) FROM professors").fetchone()[0] == 2

import json
import sqlite3
from contextlib import closing

import pytest

import database
from scripts.plan_professor_expansion import rehearsal
from scripts.prepare_pilot_package import ROOT


@pytest.fixture
def expansion(tmp_path, monkeypatch):
    path = tmp_path / "source.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    database.initialize_database(run_maintenance=False)
    database.upsert_professors([{"name": "Existing researcher", "university": "Existing University", "email": "existing@example.edu"}])
    database.upsert_user(user_id="synthetic-owner", email="student@example.test")
    rows = json.loads((ROOT / "tests/fixtures/professor-candidates.json").read_text(encoding="utf-8"))["records"]
    return path, rows


def test_rehearsal_preserves_input_and_private_data(expansion):
    path, records = expansion
    before = path.read_bytes()
    result = rehearsal(path, records)
    assert result["candidate_rows"] == 7 and result["private_tables_unchanged"]
    assert path.read_bytes() == before
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 1
        assert connection.execute("SELECT user_id FROM users").fetchall() == [("synthetic-owner",)]


def test_duplicate_batch_and_existing_person_fail_closed(expansion):
    path, records = expansion
    with pytest.raises(ValueError, match="duplicate"):
        rehearsal(path, records + [records[0]])
    records[0]["name"] = "Existing researcher"
    with pytest.raises(ValueError, match="duplicate"):
        rehearsal(path, records)


def test_unsafe_sources_rejected_before_insertion(expansion):
    path, records = expansion
    records[0]["data_source_url"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="HTTPS"):
        rehearsal(path, records)

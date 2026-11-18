import sqlite3
from contextlib import closing

import pytest

import database
from scripts.export_public_seed import export, PUBLIC_COLUMNS


@pytest.fixture
def seed_source(tmp_path, monkeypatch):
    path = tmp_path / "source.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    database.initialize_database(run_maintenance=False)
    database.upsert_professors([{"name":"Synthetic Academic", "university":"Test University", "email":"academic@example.test", "research_interests":"Robotics"}])
    database.upsert_user(user_id="private-person", email="private-person@example.test")
    return path


def test_exports_only_public_rows_preserving_ids_and_source(seed_source, tmp_path):
    before = seed_source.read_bytes()
    destination = tmp_path / "public.db"
    result = export(seed_source, destination)
    assert result["rows"] == 1 and result["private_tables_copied"] is False
    assert seed_source.read_bytes() == before
    assert b"private-person" not in destination.read_bytes()
    with closing(sqlite3.connect(destination)) as conn:
        assert {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"professors", "sqlite_sequence"}
        assert conn.execute("SELECT id,name FROM professors").fetchall() == [(1,"Synthetic Academic")]


@pytest.mark.parametrize("target", ["source", "existing"])
def test_never_overwrites_existing_files(seed_source, tmp_path, target):
    destination = seed_source if target == "source" else tmp_path / "existing.db"
    if target == "existing": destination.write_bytes(b"preserve")
    before = destination.read_bytes()
    with pytest.raises(ValueError, match="new destination"):
        export(seed_source, destination)
    assert destination.read_bytes() == before


def test_unreviewed_new_column_fails_closed(seed_source, tmp_path):
    with closing(sqlite3.connect(seed_source)) as conn:
        conn.execute("ALTER TABLE professors ADD COLUMN private_note TEXT")
        conn.commit()
    destination = tmp_path / "public.db"
    with pytest.raises(ValueError, match="allowlist"):
        export(seed_source, destination)
    assert not destination.exists()


def test_seed_can_be_initialized_without_repair_or_private_data(seed_source, tmp_path, monkeypatch):
    destination = tmp_path / "public.db"
    export(seed_source, destination)
    with closing(sqlite3.connect(destination)) as conn:
        names = ','.join(f'"{c}"' for c in PUBLIC_COLUMNS)
        before = conn.execute(f"SELECT {names} FROM professors").fetchall()
    monkeypatch.setattr(database, "DB_PATH", destination)
    database.initialize_database(run_maintenance=False)
    with closing(sqlite3.connect(destination)) as conn:
        assert conn.execute(f"SELECT {names} FROM professors").fetchall() == before
        for table in ("users","sessions","student_profiles","professor_outreach","query_embedding_cache"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

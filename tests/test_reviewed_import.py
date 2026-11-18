import json
import sqlite3
from contextlib import closing

import pytest
import database
from api.retention import initialize
from scripts.import_reviewed_professors import import_records
from scripts.prepare_pilot_package import ROOT


@pytest.fixture
def batch(tmp_path, monkeypatch):
    path = tmp_path / "runtime.db"
    monkeypatch.setattr(database, "DB_PATH", path)
    monkeypatch.setenv("RETENTION_ROOT", str(tmp_path / "managed"))
    monkeypatch.setenv("RETENTION_KEY_FILE", str(tmp_path / "key"))
    database.initialize_database(run_maintenance=False)
    database.upsert_professors([{"name": "Existing researcher", "university": "Existing University", "email": "existing@example.edu"}])
    database.upsert_user(user_id="google:synthetic", email="synthetic@example.test")
    store = initialize()
    store.maintain()
    records = json.loads((ROOT / "evidence/public-launch-preparation-2026-10-11/professor-candidates.json").read_text())["records"]
    return path, store, records


def test_insert_preserves_private_rows_and_backup_can_be_decrypted(batch):
    path, store, records = batch
    with closing(sqlite3.connect(path)) as conn:
        original = conn.execute("SELECT * FROM professors").fetchall()
        users = conn.execute("SELECT * FROM users").fetchall()
    result = import_records(records, expected_database=path)
    assert result["inserted"] == 7 and result["total"] == 8
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT * FROM professors WHERE id=1").fetchall() == original
        assert conn.execute("SELECT * FROM users").fetchall() == users
        assert conn.execute("SELECT MIN(id) FROM professors WHERE id != 1").fetchone()[0] > 1
    with closing(store.connect()) as ledger:
        assert ledger.execute("SELECT COUNT(*) FROM backups").fetchone()[0] == 2
        name = ledger.execute("SELECT name FROM backups ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    encrypted = (store.root / "backups" / name).read_bytes()
    assert b"SQLite format" not in encrypted
    with closing(sqlite3.connect(":memory:")) as restored:
        restored.deserialize(store.cipher.decrypt(encrypted))
        assert restored.execute("SELECT * FROM users").fetchall() == users
        assert restored.execute("SELECT * FROM professors").fetchall() == original
    with pytest.raises(ValueError, match="duplicate"):
        import_records(records, expected_database=path)


def test_backup_failure_prevents_import(batch, monkeypatch):
    path, store, records = batch
    monkeypatch.setattr("api.retention.Store.maintain", lambda *a, **k: False)
    with pytest.raises(ValueError, match="backup"):
        import_records(records, expected_database=path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 1


def test_transaction_failure_rolls_back_all_rows(batch, monkeypatch):
    path, store, records = batch
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TRIGGER reject_batch BEFORE INSERT ON professors WHEN NEW.name LIKE 'Sarah%' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        import_records(records, expected_database=path)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 1


def test_no_backup_cleanup_during_forced_snapshot(batch):
    path, store, records = batch
    historical = store.root / "logs" / "api-2020-01-01.jsonl"
    historical.write_text("{}")
    import_records(records, expected_database=path)
    assert historical.exists()


def test_wrong_target_rejected(batch, tmp_path):
    path, store, records = batch
    other = tmp_path / "other.db"
    other.write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="identity"):
        import_records(records, expected_database=other)

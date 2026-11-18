import hashlib
import json
import logging
import gc
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet, InvalidToken
from fastapi.testclient import TestClient

import database
from api.retention import Store, initialize, PrivateSafeHandler
from api.auth.account_deletion import delete_account, DeletionError
from api.main import create_app
from scripts.restore_private_backup import restore


@pytest.fixture
def managed(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "runtime.db")
    monkeypatch.setenv("RETENTION_ROOT", str(tmp_path / "managed"))
    monkeypatch.setenv("RETENTION_KEY_FILE", str(tmp_path / "key"))
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "tokens"))
    database.initialize_database(run_maintenance=False)
    database.upsert_user(user_id="google:alice", email="alice@example.test")
    database.upsert_user(user_id="google:bob", email="bob@example.test")
    return initialize()


def backup_path(store):
    with closing(store.connect()) as conn:
        return store.root / "backups" / conn.execute("SELECT name FROM backups ORDER BY created_at DESC LIMIT 1").fetchone()[0]


def test_encrypted_backup_omits_sessions_and_restore_honors_independent_receipts(managed, tmp_path):
    with database.connect() as conn:
        conn.execute("CREATE TABLE oauth_login_attempts(state_hash TEXT, verifier TEXT)")
        conn.execute("INSERT INTO oauth_login_attempts VALUES ('private-state','private-verifier')")
    conn.close()
    managed.maintain()
    backup = backup_path(managed)
    assert b"SQLite format" not in backup.read_bytes()
    with closing(sqlite3.connect(":memory:")) as snapshot:
        snapshot.deserialize(managed.cipher.decrypt(backup.read_bytes()))
        assert snapshot.execute("SELECT COUNT(*) FROM oauth_login_attempts").fetchone()[0] == 0
        assert snapshot.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    delete_account("google:alice")
    with closing(managed.connect()) as ledger:
        assert ledger.execute("SELECT subject_hash FROM account_deletion_receipts").fetchone()[0] == hashlib.sha256(b"google:alice").hexdigest()
    gc.collect()  # Release legacy initialization connections on Windows.
    database.DB_PATH.unlink()  # Simulate total loss of the live database.
    restored = restore(backup, managed.ledger, tmp_path / "restored.db", cipher=managed.cipher)
    with closing(sqlite3.connect(restored)) as conn:
        assert conn.execute("SELECT user_id FROM users").fetchall() == [("google:bob",)]


def test_exact_expiry_and_unknown_historical_files_preserved(managed, tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    managed.maintain(now)
    old = backup_path(managed)
    unknown = managed.root / "backups" / "historical.db"
    unknown.write_bytes(b"preserve")
    outside = tmp_path / "old-original.db"
    outside.write_bytes(b"preserve")
    log = managed.root / "logs" / "api-2026-01-01.jsonl"
    log.write_text("{}\n", encoding="utf-8")
    managed.maintain(now + timedelta(days=29, hours=23, minutes=59))
    assert old.exists() and log.exists()
    managed.maintain(now + timedelta(days=30))
    assert not old.exists() and not log.exists()
    assert unknown.read_bytes() == outside.read_bytes() == b"preserve"


def test_concurrent_daily_backup_and_wrong_runtime_refused(managed, monkeypatch, tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: managed.maintain(), range(2))) == [False, True]
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "another.db")
    with pytest.raises(ValueError, match="does not match"):
        Store()


def test_missing_ledger_blocks_deletion_before_user_rows_removed(managed):
    managed.ledger.unlink()
    with pytest.raises(DeletionError):
        delete_account("google:alice")
    with database.connect() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE user_id='google:alice'").fetchone()


def test_receipt_write_failure_rolls_back_both_databases(managed):
    with closing(managed.connect()) as ledger:
        ledger.execute("CREATE TRIGGER deny_receipt BEFORE INSERT ON account_deletion_receipts BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        ledger.commit()
    with pytest.raises(DeletionError):
        delete_account("google:alice")
    with database.connect() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE user_id='google:alice'").fetchone()
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='account_deletion_receipts'").fetchone()


def test_wal_refused_before_deletion(managed):
    with database.connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    with pytest.raises(DeletionError):
        delete_account("google:alice")
    with database.connect() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE user_id='google:alice'").fetchone()


@pytest.mark.parametrize("tamper", [False, True])
def test_failed_decryption_leaves_no_partial_restore(managed, tmp_path, tamper):
    managed.maintain()
    file = backup_path(managed)
    cipher = managed.cipher
    if tamper:
        file.write_bytes(file.read_bytes()[:-5] + b"XXXXX")
    else:
        cipher = Fernet(Fernet.generate_key())
    destination = tmp_path / "rejected.db"
    with pytest.raises(InvalidToken):
        restore(file, managed.ledger, destination, cipher=cipher)
    assert not destination.exists()


def test_key_replacement_and_existing_store_fail_closed(managed):
    with pytest.raises(ValueError, match="new dedicated"):
        initialize()
    managed.key.write_bytes(Fernet.generate_key())
    with pytest.raises(ValueError, match="does not match"):
        Store()


def test_linked_registered_backup_never_deleted(managed, tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    managed.maintain(now)
    file = backup_path(managed)
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve")
    file.unlink()
    try:
        file.symlink_to(outside)
    except OSError:
        pytest.skip("OS does not allow symlink creation")
    with pytest.raises(ValueError, match="linked"):
        managed.maintain(now + timedelta(days=30))
    assert outside.read_bytes() == b"preserve"


def test_log_discards_credentials_personal_data_and_tracebacks(managed):
    handler = PrivateSafeHandler(managed)
    handler.handle(logging.LogRecord("provider", logging.ERROR, "private-path", 1, "alice@example.test Cookie: session=private-secret", (), None))
    text = next((managed.root / "logs").iterdir()).read_text(encoding="utf-8")
    assert "alice" not in text and "private" not in text and "Cookie" not in text
    assert json.loads(text)["event"] == "application_event"


def test_startup_runs_maintenance_and_reports_status(managed, monkeypatch):
    monkeypatch.setenv("APP_MODE", "local")
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["retention"]["status"] == "ok"
    assert backup_path(managed).exists()


def test_authenticated_orphan_recovered_after_interrupted_registry_commit(managed):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    managed.maintain(now)
    file = backup_path(managed)
    with closing(managed.connect()) as conn:
        conn.execute("DELETE FROM backups")
        conn.commit()
    assert managed.maintain(now + timedelta(hours=2)) is False
    assert backup_path(managed) == file


def test_background_failure_visible_and_later_tick_recovers(managed, monkeypatch):
    import api.retention as retention
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.setattr(retention, "CHECK_SECONDS", 0.05)
    original = Store.maintain
    calls = []
    def maintenance(self, *args):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("synthetic private error")
        return original(self, *args)
    monkeypatch.setattr(Store, "maintain", maintenance)
    with TestClient(create_app()) as client:
        deadline = time.monotonic() + 5
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert client.get("/api/health").json()["retention"]["status"] == "error"
        while client.get("/api/health").json()["retention"]["status"] != "ok" and time.monotonic() < deadline:
            time.sleep(0.005)
        assert client.get("/api/health").json()["retention"]["status"] == "ok"

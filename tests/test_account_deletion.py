"""Destructive checks use disposable accounts, token files and database copies."""
import hashlib
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import database
from api.auth import account_deletion, login_attempts
from api.gmail import token_store
from api.main import create_app
from scripts.restore_private_backup import restore
from tests._auth_helpers import client_for_user


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "accounts.db")
    monkeypatch.setenv("GMAIL_TOKEN_DIR", str(tmp_path / "tokens"))
    monkeypatch.delenv("GMAIL_TOKEN_ENCRYPTION_KEY", raising=False)
    database.initialize_database()
    database.upsert_professors([{"name": "Synthetic professor", "university": "Test University", "email": "professor@example.test"}])
    professor = database.fetch_professors()[0]["id"]
    alice = client_for_user("google:alice", "alice@example.test")
    bob = client_for_user("google:bob", "bob@example.test")
    for client, name in [(alice, "Alice"), (bob, "Bob")]:
        assert client.put("/api/profile", json={"interest_text": name+" research"}).status_code == 200
        assert client.post(f"/api/saved/{professor}").status_code == 200
    calls = []
    def revoke(url, **kwargs):
        calls.append((url, kwargs))
        return type("Response", (), {"status_code": 200})()
    monkeypatch.setattr(account_deletion.requests, "post", revoke)
    return alice, bob, professor, calls


def remove(client, user="google:alice", confirmation="DELETE"):
    return client.request("DELETE", "/api/auth/account", json={"confirmation": confirmation, "expected_user_id": user})


def credentials(user="google:alice"):
    token_store.save_credentials(user, {"token": {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh"}, "client_id": "synthetic-client", "account_email": "synthetic@example.test"})
    token_store.save_pending_state(user, "synthetic-state")


def test_consumed_oauth_state_lock_does_not_block_account_deletion(accounts):
    alice, _, _, _ = accounts
    credentials()
    assert token_store.pop_pending_state("google:alice") == "synthetic-state"
    assert remove(alice).status_code == 200
    assert not token_store.credentials_path("google:alice").parent.exists()


def test_delete_wipes_only_owner_and_preserves_public_directory(accounts):
    alice, bob, professor, calls = accounts
    credentials()
    credentials("google:bob")
    state, _, _ = login_attempts.begin("google:alice")
    with database.connect() as conn:
        conn.execute("CREATE TABLE ai_explanation_requests(user_id TEXT, requested_at REAL)")
        conn.execute("INSERT INTO ai_explanation_requests VALUES (?,?)", ("google:alice", time.time()))
    result = remove(alice)
    assert result.status_code == 200
    assert result.json() == {"deleted": True, "google_revocation": "revoked"}
    assert calls[0][1]["timeout"] == 10
    assert database.get_user("google:alice") is None
    assert database.get_student_profile("google:alice") is None
    assert database.get_professor_outreach(None, user_id="google:alice") == {}
    assert login_attempts.consume(state) is None
    assert not token_store.credentials_path("google:alice").exists()
    assert not token_store.pending_path("google:alice").exists()
    assert alice.get("/api/profile").status_code == 401
    assert remove(alice).status_code == 401
    assert "Bob research" in str(bob.get("/api/profile").json())
    assert bob.get("/api/saved").json()["total"] == 1
    assert token_store.has_credentials("google:bob")
    assert database.professor_count() == 1
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_explanation_requests").fetchone()[0] == 0
        assert conn.execute("SELECT subject_hash FROM account_deletion_receipts").fetchone()[0] == hashlib.sha256(b"google:alice").hexdigest()


@pytest.mark.parametrize("status", [400, 403, 503])
def test_provider_failure_still_removes_local_credentials(accounts, monkeypatch, status):
    credentials()
    monkeypatch.setattr(account_deletion.requests, "post", lambda *args, **kwargs: type("Response", (), {"status_code": status})())
    result = remove(accounts[0])
    assert result.status_code == 200
    assert result.json()["google_revocation"] == "unconfirmed"
    assert not token_store.has_credentials("google:alice")


def test_provider_timeout_still_deletes(accounts, monkeypatch):
    credentials()
    def timeout(*args, **kwargs):
        raise requests.Timeout("synthetic outage")
    monkeypatch.setattr(account_deletion.requests, "post", timeout)
    assert remove(accounts[0]).json()["google_revocation"] == "unconfirmed"
    assert database.get_user("google:alice") is None


def test_corrupt_credentials_are_removed_without_google_call(accounts):
    credentials()
    token_store.credentials_path("google:alice").write_text("invalid JSON")
    assert remove(accounts[0]).json()["google_revocation"] == "unconfirmed"
    assert accounts[3] == []
    assert not token_store.credentials_path("google:alice").exists()


@pytest.mark.parametrize("mode", ["wrong-confirmation", "wrong-account", "missing-csrf", "anonymous"])
def test_confirmation_identity_and_csrf_required(accounts, mode):
    alice = accounts[0]
    if mode == "missing-csrf":
        alice.headers.pop("X-CSRF-Token")
    if mode == "anonymous":
        alice = TestClient(create_app())
    response = remove(alice, "google:bob" if mode == "wrong-account" else "google:alice", "delete" if mode == "wrong-confirmation" else "DELETE")
    assert response.status_code in {401, 403, 409, 422}
    assert database.get_user("google:alice") is not None
    assert database.get_user("google:bob") is not None


def test_file_failure_does_not_report_deleted_and_can_retry(accounts, monkeypatch):
    credentials()
    blocked = token_store.credentials_path("google:alice")
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("synthetic denied file")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    assert remove(accounts[0]).status_code == 503
    assert database.get_user("google:alice") is not None
    assert accounts[0].get("/api/profile").status_code == 200
    monkeypatch.setattr(Path, "unlink", original)
    assert remove(accounts[0]).status_code == 200


def test_storage_collision_fails_without_deleting_another_user(accounts):
    database.upsert_user(user_id="google:ali/ce", email="one@example.test")
    client = client_for_user("google:ali_ce", "two@example.test")
    # Model an existing legacy collision; new writes through the token store
    # now reject the unsupported slash identity before accessing this file.
    legacy = token_store.credentials_path("google:ali_ce")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy credentials preserved", encoding="utf-8")
    assert remove(client, user="google:ali_ce").status_code == 503
    assert legacy.read_text(encoding="utf-8") == "legacy credentials preserved"
    assert database.get_user("google:ali/ce") is not None


def test_inflight_mutation_completes_before_delete_and_queued_save_is_rejected(accounts, monkeypatch):
    alice = accounts[0]
    entered, release = threading.Event(), threading.Event()
    from api.routes import profile
    original = profile.save_student_profile
    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(profile, "save_student_profile", delayed)
    with ThreadPoolExecutor(max_workers=3) as pool:
        saving = pool.submit(alice.put, "/api/profile", json={"interest_text": "in flight"})
        assert entered.wait(5)
        deleting = pool.submit(remove, alice)
        time.sleep(0.2)
        assert not deleting.done()
        release.set()
        assert saving.result().status_code == 200
        assert deleting.result().status_code == 200
    assert alice.put("/api/profile", json={"interest_text": "late write"}).status_code == 401
    assert database.get_student_profile("google:alice") is None


def test_restoring_old_backup_applies_receipts_and_revokes_sessions(accounts, tmp_path):
    backup, restored = tmp_path / "before.db", tmp_path / "restored.db"
    with sqlite3.connect(database.DB_PATH) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    assert remove(accounts[0]).status_code == 200
    restore(backup, database.DB_PATH, restored)
    with sqlite3.connect(restored) as conn:
        assert [row[0] for row in conn.execute("SELECT user_id FROM users")] == ["google:bob"]
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 1
    with pytest.raises(ValueError):
        restore(backup, database.DB_PATH, restored)


def test_fresh_sign_in_creates_empty_account(accounts):
    assert remove(accounts[0]).status_code == 200
    fresh = client_for_user("google:alice", "alice@example.test")
    assert fresh.get("/api/profile").json()["interest_text"] == ""
    assert fresh.get("/api/saved").json()["total"] == 0


def test_new_account_after_deletion_is_preserved_in_later_backup(accounts, tmp_path):
    assert remove(accounts[0]).status_code == 200
    fresh = client_for_user("google:alice", "alice@example.test")
    assert fresh.put("/api/profile", json={"interest_text": "New profile after deletion"}).status_code == 200
    destination = tmp_path / "later.db"
    restore(database.DB_PATH, database.DB_PATH, destination)
    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT interest_text FROM student_profiles WHERE user_id='google:alice'").fetchone()[0] == "New profile after deletion"


def test_restore_fails_closed_without_deletion_receipts(accounts, tmp_path):
    destination = tmp_path / "unsafe.db"
    with pytest.raises(ValueError, match="Deletion receipts"):
        restore(database.DB_PATH, database.DB_PATH, destination)
    assert not destination.exists()


def test_queued_write_during_deletion_cannot_recreate_data(accounts, monkeypatch):
    alice = accounts[0]
    credentials()
    entered, release = threading.Event(), threading.Event()
    def delayed_revoke(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return type("Response", (), {"status_code": 200})()
    monkeypatch.setattr(account_deletion.requests, "post", delayed_revoke)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleting = pool.submit(remove, alice)
        assert entered.wait(5)
        saving = pool.submit(alice.put, "/api/profile", json={"interest_text": "queued after deletion began"})
        time.sleep(0.2)
        assert not saving.done()
        release.set()
        assert deleting.result().status_code == 200
        assert saving.result().status_code == 401
    assert database.get_student_profile("google:alice") is None


def test_lock_supports_deep_windows_checkout_paths(tmp_path, monkeypatch):
    import asyncio
    from api.auth.account_lock import account_lock
    nested = tmp_path
    while len(str(nested)) < 180:
        nested /= "nested-checkout-path"
    nested.mkdir(parents=True)
    monkeypatch.setattr(database, "DB_PATH", nested / "accounts.db")
    async def acquire():
        async with account_lock("google:synthetic-deep-path"):
            pass
    asyncio.run(acquire())
    files = list((nested / ".account_locks").glob("*.lock"))
    assert len(files) == 1
    assert len(files[0].name) == 37

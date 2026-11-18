"""Adversarial account selectors against disposable signed-in accounts."""
import pytest

import database
from tests._auth_helpers import client_for_user


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "boundaries.db")
    database.initialize_database()
    database.upsert_professors([{
        "name": "Synthetic researcher", "university": "Test University",
        "email": "researcher@example.test",
    }])
    professor = database.fetch_professors()[0]["id"]
    alice = client_for_user("google:alice", "alice@example.test")
    bob = client_for_user("google:bob", "bob@example.test")
    assert alice.post(f"/api/saved/{professor}").status_code == 200
    assert alice.patch(f"/api/outreach/{professor}", json={"notes": "Alice private note"}).status_code == 200
    yield alice, bob, professor
    alice.close()
    bob.close()


def test_forged_query_selectors_cannot_read_other_account(accounts):
    alice, bob, professor = accounts
    assert bob.get("/api/saved?user_id=google:alice").json()["total"] == 0
    assert bob.get("/api/outreach?user_id=google:alice").json()["total"] == 0
    response = bob.get(f"/api/outreach/{professor}?user_id=google:alice")
    assert response.status_code == 200
    assert response.json()["outreach"]["notes"] == ""
    assert alice.get(f"/api/outreach/{professor}").json()["outreach"]["notes"] == "Alice private note"


def test_forged_mutation_selectors_only_change_callers_rows(accounts):
    alice, bob, professor = accounts
    assert bob.post(f"/api/saved/{professor}?user_id=google:alice").status_code == 200
    response = bob.patch(f"/api/outreach/{professor}", json={
        "user_id": "google:alice", "notes": "Bob private note",
    })
    assert response.status_code == 200
    assert alice.get(f"/api/outreach/{professor}").json()["outreach"]["notes"] == "Alice private note"
    assert bob.get(f"/api/outreach/{professor}").json()["outreach"]["notes"] == "Bob private note"
    assert bob.delete(f"/api/saved/{professor}?user_id=google:alice").status_code == 200
    assert bob.get("/api/saved").json()["total"] == 0
    assert alice.get("/api/saved").json()["total"] == 1


def test_other_accounts_csrf_token_cannot_authorize_write(accounts):
    alice, bob, professor = accounts
    bob.headers["X-CSRF-Token"] = alice.headers["X-CSRF-Token"]
    assert bob.patch(f"/api/outreach/{professor}", json={"notes": "Blocked"}).status_code == 403
    assert alice.get(f"/api/outreach/{professor}").json()["outreach"]["notes"] == "Alice private note"
    assert bob.get(f"/api/outreach/{professor}").json()["outreach"]["notes"] == ""


def test_clear_profile_preserves_saved_outreach_and_other_account(accounts):
    alice, bob, professor = accounts
    original = {"expected_user_id": "google:alice", "interests": ["Robotics"], "interest_text": "Build robots", "skills": ["Python"], "coursework": ["Physics"], "experience": ["Sensor project"], "education_level": "university", "completed": True, "preferences": {"locations": ["Washington"], "university_types": ["R1 university"], "support_level": "funding", "remote_ok": True}}
    assert alice.put('/api/profile', json=original).status_code == 200
    assert bob.put('/api/profile', json={"interests": ["Biology"]}).status_code == 200
    empty = {"expected_user_id": "google:alice", "interests": [], "interest_text": "", "skills": [], "coursework": [], "experience": [], "education_level": "high_school", "completed": False, "preferences": {"locations": [], "university_types": [], "support_level": "No preference", "remote_ok": False}}
    assert alice.put('/api/profile', json=empty).status_code == 200
    cleared = alice.get('/api/profile').json()
    for field in ['interests', 'skills', 'coursework', 'experience']:
        assert cleared[field] == []
    assert cleared['interest_text'] == '' and not cleared['completed']
    assert not cleared['preferences']['remote_ok']
    assert alice.get('/api/saved').json()['total'] == 1
    assert alice.get(f'/api/outreach/{professor}').json()['outreach']['notes'] == 'Alice private note'
    assert bob.get('/api/profile').json()['interests'] == ['Biology']
    assert alice.put('/api/profile', json=original).status_code == 200
    assert alice.get('/api/profile').json()['coursework'] == ['Physics']

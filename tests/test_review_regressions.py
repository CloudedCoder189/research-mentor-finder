from pathlib import Path
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import database
from api.main import create_app
from api.auth import config, ai_limits
from api.routes import recommendations as routes
from services import ai_explanation as ai
from tests._auth_helpers import signed_client, client_for_user
from tests.test_ai_explanation import PROFILE, VISION_RECORD, GROUNDED_REASONS


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "regressions.db")
    monkeypatch.setenv("APP_MODE", "local")
    database.initialize_database()
    return tmp_path


@pytest.mark.parametrize("mode", ["public", "production", "staging", "typo", ""])
def test_developer_login_not_implicitly_enabled_outside_local(monkeypatch, mode):
    monkeypatch.delenv("AUTH_ALLOW_DEV_LOGIN", raising=False)
    monkeypatch.setenv("APP_MODE", mode)
    assert not config.dev_login_allowed()


def test_remote_account_cannot_claim_unimported_local_data(isolated):
    other = client_for_user("google:other", "other@example.test")
    assert other.post("/api/auth/import-local").status_code == 403
    assert not database.local_owner_import_marker()


def test_import_disabled_in_public_even_for_local_owner(isolated, monkeypatch):
    client = signed_client()
    monkeypatch.setenv("APP_MODE", "public")
    assert client.post("/api/auth/import-local").status_code == 403


def test_paid_explanation_requires_auth_and_csrf(isolated, monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "explain_record", lambda *a, **kw: calls.append(kw))
    payload = {"profile": PROFILE, "researcher_id": 11, "include_ai": True}
    assert TestClient(create_app()).post("/api/recommendations/explain", json=payload).status_code == 401
    client = signed_client(with_csrf=False)
    assert client.post("/api/recommendations/explain", json=payload).status_code == 403
    assert calls == []


def test_ai_quota_is_shared_atomic_and_recovers_after_window(isolated, monkeypatch):
    monkeypatch.setenv("AI_EXPLANATIONS_PER_USER_HOUR", "3")
    monkeypatch.setenv("AI_EXPLANATIONS_PER_DAY", "4")
    monkeypatch.setattr(ai_limits.time, "time", lambda: 100000)

    def reserve(_):
        try:
            ai_limits.reserve_explanation("user-a")
            return True
        except HTTPException as exc:
            assert exc.status_code == 429
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(8))) == 3
    ai_limits.reserve_explanation("user-b")
    with pytest.raises(HTTPException):
        ai_limits.reserve_explanation("user-c")
    monkeypatch.setattr(ai_limits.time, "time", lambda: 190000)
    ai_limits.reserve_explanation("user-a")


def test_read_does_not_repair_dirty_records_or_invalidate_embeddings(isolated):
    database.upsert_professors([VISION_RECORD | {"email": "test@example.edu", "profile_url": "https://example.edu/test"}])
    with database.connect() as connection:
        connection.execute("UPDATE professors SET title = 'Professor Profile Publications Teaching', embedding_json = '[1,2]', ai_summary = 'Kept', verification_status = 'Verified'")
        database._bump_data_revision(connection)
    # Also exercise a fresh process-style schema readiness cache miss.
    database._INITIALIZED_FILES.clear()
    before = database.fetch_professors()[0]
    database.professor_count()
    database.get_user("nobody")
    after = database.fetch_professors()[0]
    for field in ("title", "embedding_json", "ai_summary", "verification_status"):
        assert before[field] == after[field]
    assert after["title"] == 'Professor Profile Publications Teaching'
    assert after["embedding_json"] == '[1,2]'


@pytest.mark.parametrize("claim", [
    "This research lab won a Nobel Prize.",
    "Professor Chandraker uses Python to study quantum astrology.",
    "Your Computer vision interests match a guaranteed paid position.",
])
def test_ai_cannot_add_facts_even_with_shared_context_words(claim):
    context = ai.build_context(VISION_RECORD, PROFILE)
    assert ai.validate_reasons({"reasons": [claim]}, context, GROUNDED_REASONS) is None


def test_student_technology_cannot_become_professor_fact():
    record = VISION_RECORD | {"research_interests": "Computer vision", "ai_summary": "Computer vision"}
    context = ai.build_context(record, PROFILE)
    assert ai.validate_reasons({"reasons": ["This professor uses Python for Computer vision."]}, context, []) is None


def test_queued_profile_cannot_write_to_changed_account(isolated):
    client = signed_client()
    response = client.put("/api/profile", json={"expected_user_id": "google:previous", "interests": ["Robotics"]})
    assert response.status_code == 409
    assert client.get("/api/profile").json()["interests"] == []


def test_dotenv_database_path_loaded_before_database_import(tmp_path):
    root = Path(database.__file__).resolve().parent
    for name in ("database.py", "runtime_config.py"):
        shutil.copyfile(root / name, tmp_path / name)
    (tmp_path / ".env").write_text("PROFESSOR_DB_PATH=isolated/from-dotenv.db\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(root))
    env.pop("PROFESSOR_DB_PATH", None)
    result = subprocess.run([sys.executable, "-c", "import database; print(database.DB_PATH)"], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert Path(result.stdout.strip()) == tmp_path / "isolated" / "from-dotenv.db"
    env["PROFESSOR_DB_PATH"] = str(tmp_path / "explicit.db")
    result = subprocess.run([sys.executable, "-c", "import database; print(database.DB_PATH)"], cwd=tmp_path, env=env, capture_output=True, text=True, check=True)
    assert Path(result.stdout.strip()) == tmp_path / "explicit.db"

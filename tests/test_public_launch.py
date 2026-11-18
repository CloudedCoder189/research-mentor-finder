"""Public configuration safety and disposable account acceptance."""
import pytest

import database
from deploy.pilot.provision import access_mode, settings, validate_gate
from scripts.prepare_pilot_package import ROOT, selected_files
from tests._auth_helpers import client_for_user


def test_public_mode_is_explicit_and_private_remains_default(monkeypatch, tmp_path):
    monkeypatch.delenv("PILOT_ACCESS_MODE", raising=False)
    assert access_mode({}) == "private"
    assert settings(tmp_path)["APP_MODE"] == "staging"
    with pytest.raises(ValueError):
        validate_gate({})
    monkeypatch.setenv("PILOT_ACCESS_MODE", "public")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "inherited-synthetic-client")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "inherited-synthetic-secret")
    config = settings(tmp_path)
    assert config["APP_MODE"] == "public"
    assert config["AUTH_ALLOW_DEV_LOGIN"] == "false"
    assert config["AUTH_COOKIE_SECURE"] == "true"
    assert config["OPENAI_API_KEY"] == "" and config["AI_EXPLANATIONS"] == "0"
    assert config["GMAIL_CLIENT_ID"] == "" and config["GMAIL_CLIENT_SECRET"] == ""
    validate_gate({"PILOT_ACCESS_MODE": "public", "PORT": "8080"})
    assert ROOT / "deploy/pilot/Caddyfile.public" in selected_files(ROOT)


@pytest.mark.parametrize("mode", ["", "pubic", "local", "true"])
def test_unknown_access_mode_fails_closed(mode):
    with pytest.raises(ValueError):
        validate_gate({"PILOT_ACCESS_MODE": mode})


@pytest.mark.parametrize("port", ["18501", "18503", "13310", "80", "65536", "bad"])
def test_public_mode_preserves_port_checks(port):
    with pytest.raises(ValueError):
        validate_gate({"PILOT_ACCESS_MODE": "public", "PORT": port})


@pytest.fixture
def public_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "public.db")
    database.initialize_database(run_maintenance=False)
    database.upsert_professors([{"name": "Synthetic researcher", "university": "Example University", "email": "researcher@example.test", "research_interests": "Robotics"}])
    # Only synthetic provider configuration; no Google requests occur.
    for key, value in {"APP_MODE": "public", "AUTH_ALLOW_DEV_LOGIN": "false", "AUTH_COOKIE_SECURE": "true", "AUTH_CLIENT_ID": "synthetic", "AUTH_CLIENT_SECRET": "synthetic", "AUTH_REDIRECT_URI": "https://example.test/api/auth/callback", "AUTH_LOGIN_SUCCESS_URL": "https://example.test/account", "CORS_ORIGINS": "https://example.test", "PROFESSOR_DB_PATH": str(tmp_path / "public.db"), "OPENAI_API_KEY": "", "AI_EXPLANATIONS": "0", "GMAIL_CLIENT_ID": "", "GMAIL_CLIENT_SECRET": ""}.items():
        monkeypatch.setenv(key, value)
    alice = client_for_user("google:launch-a", "a@example.test")
    bob = client_for_user("google:launch-b", "b@example.test")
    # Secure cookies require HTTPS even for in-process TestClient calls.
    alice.base_url = bob.base_url = "https://testserver"
    from fastapi.testclient import TestClient
    from api.main import create_app
    anonymous = TestClient(create_app(), base_url="https://testserver")
    yield alice, bob, anonymous, database.fetch_professors()[0]["id"]
    alice.close()
    bob.close()
    anonymous.close()


def test_public_directory_and_private_account_boundaries(public_accounts):
    alice, bob, anonymous, professor = public_accounts
    assert anonymous.get("/api/researchers").status_code == 200
    for visitor in (alice, bob, anonymous):
        assert visitor.get("/api/auth/me").json()["local_import_available"] is False
    for path in ("/api/profile", "/api/saved", "/api/outreach", "/api/gmail/status"):
        assert anonymous.get(path).status_code == 401
    assert anonymous.post("/api/auth/dev-login").status_code == 404
    assert anonymous.post("/api/profile/resume-preview").status_code == 401
    assert alice.post(f"/api/saved/{professor}").status_code == 200
    assert alice.put("/api/profile", json={"interests": ["Robotics"]}).status_code == 200
    assert bob.get("/api/saved?user_id=google:launch-a").json()["total"] == 0
    assert bob.get("/api/profile?user_id=google:launch-a").json()["interests"] == []
    bob.headers["X-CSRF-Token"] = alice.headers["X-CSRF-Token"]
    assert bob.put("/api/profile", json={"interests": ["Chemistry"]}).status_code == 403
    assert alice.get("/api/profile").json()["interests"] == ["Robotics"]
    assert alice.get("/api/gmail/status").json()["available"] is False


def test_five_people_on_shared_network_have_ranking_headroom():
    from concurrent.futures import ThreadPoolExecutor
    from api.admission import Admission
    limiter = Admission(clock=lambda: 0)
    # Five people: a search, a recommendation refresh and three comparison explanations each.
    with ThreadPoolExecutor(max_workers=5) as pool:
        result = list(pool.map(lambda _: limiter.admit("ranking", "shared-network"), range(25)))
    assert result == [0] * 25
    assert all(limiter.admit("login", "shared-network") == 0 for _ in range(5))


def test_paid_ai_disabled_even_with_key_present(monkeypatch):
    from services.ai_explanation import ai_explanations_enabled
    monkeypatch.setenv("AI_EXPLANATIONS", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-not-a-real-key")
    assert not ai_explanations_enabled()

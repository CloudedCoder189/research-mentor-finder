from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.auth import config
from api.main import create_app
from api.production_config import validate_production_config
from services.categorization import categorize_with_keywords
from services.search import record_concepts


@pytest.fixture
def public_config(monkeypatch, tmp_path):
    values = {
        "APP_MODE": "public", "AUTH_ALLOW_DEV_LOGIN": "false",
        "AUTH_COOKIE_SECURE": "true", "AUTH_CLIENT_ID": "synthetic-client",
        "AUTH_CLIENT_SECRET": "synthetic-secret", "CORS_ORIGINS": "https://mentor.example.org",
        "AUTH_REDIRECT_URI": "https://mentor.example.org/api/auth/callback",
        "AUTH_LOGIN_SUCCESS_URL": "https://mentor.example.org/account",
        "PROFESSOR_DB_PATH": str(tmp_path / "runtime.db"), "AI_EXPLANATIONS": "0",
        "GMAIL_CLIENT_ID": "", "GMAIL_CLIENT_SECRET": "", "GMAIL_TOKEN_ENCRYPTION_KEY": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_safe_public_configuration_starts_without_developer_login(public_config):
    client = TestClient(create_app())
    assert client.post("/api/auth/dev-login").status_code == 404
    assert client.get("/api/auth/me").json()["dev_login_available"] is False


@pytest.mark.parametrize("key,value", [
    ("APP_MODE", "prodction"), ("AUTH_ALLOW_DEV_LOGIN", "true"),
    ("AUTH_COOKIE_SECURE", "false"), ("AUTH_CLIENT_ID", ""), ("AUTH_CLIENT_SECRET", ""),
    ("AUTH_REDIRECT_URI", "http://mentor.example.org/api/auth/callback"),
    ("AUTH_REDIRECT_URI", "https://localhost/api/auth/callback"),
    ("AUTH_REDIRECT_URI", "https://127.0.0.1/api/auth/callback"),
    ("AUTH_REDIRECT_URI", "https://mentor.example.org/api/gmail/callback"),
    ("AUTH_LOGIN_SUCCESS_URL", "https://mentor.example.org/account?next=evil"),
    ("CORS_ORIGINS", "*"), ("CORS_ORIGINS", "https://mentor.example.org,https://192.168.1.2"),
    ("CORS_ORIGINS", "https://user:password@mentor.example.org"),
    ("PROFESSOR_DB_PATH", "data/professors.db"), ("AI_EXPLANATIONS", "1"),
    ("AI_EXPLANATIONS", ""), ("GMAIL_CLIENT_ID", "configured-without-encryption"),
])
def test_unsafe_public_settings_rejected_before_start(public_config, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(config.ConfigError, match="Unsafe deployment configuration") as failure:
        create_app()
    assert "synthetic-secret" not in str(failure.value)


@pytest.mark.parametrize("mode", ["public", "production", "staging", "typo"])
def test_explicit_developer_override_cannot_enable_remote_login(monkeypatch, mode):
    monkeypatch.setenv("APP_MODE", mode)
    monkeypatch.setenv("AUTH_ALLOW_DEV_LOGIN", "true")
    assert not config.dev_login_allowed()


def test_configured_gmail_enforces_encryption_and_callback_paths(public_config, monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    values = {
        "GMAIL_CLIENT_ID": "synthetic-gmail", "GMAIL_CLIENT_SECRET": "synthetic-gmail-secret",
        "GMAIL_TOKEN_DIR": str(tmp_path / "tokens"),
        "GMAIL_REDIRECT_URI": "https://mentor.example.org/api/gmail/callback",
        "GMAIL_REDIRECT_SUCCESS_URL": "https://mentor.example.org/outreach",
        "GMAIL_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    validate_production_config()
    monkeypatch.setenv("GMAIL_TOKEN_ENCRYPTION_KEY", "invalid-secret")
    with pytest.raises(config.ConfigError, match="valid Fernet key") as failure:
        validate_production_config()
    assert "invalid-secret" not in str(failure.value)


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/saved", "/api/profile", "/api/gmail/status", "/api/researchers/999999"])
def test_account_and_error_responses_cannot_be_cached(monkeypatch, path):
    monkeypatch.setenv("APP_MODE", "local")
    response = TestClient(create_app()).get(path)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_decision_making_does_not_become_reinforcement_learning():
    text = "Decision making in engineering under uncertainty"
    assert "Reinforcement Learning" not in categorize_with_keywords(text)
    assert "Reinforcement Learning" not in record_concepts({"research_interests": text})
    assert "Reinforcement Learning" in categorize_with_keywords("Reinforcement learning for robots")

"""Google responses are mocked; no credentials or external calls are used."""
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from fastapi.testclient import TestClient

from api.auth import google_oauth
from api.main import create_app


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("AUTH_CLIENT_ID", "fixture.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "fixture-secret")
    monkeypatch.setenv("AUTH_REDIRECT_URI", "http://localhost:18501/api/auth/callback")
    monkeypatch.setenv("AUTH_LOGIN_SUCCESS_URL", "http://localhost:13310/account")
    claims = {
        "aud": "fixture.apps.googleusercontent.com",
        "iss": "https://accounts.google.com",
        "exp": str(int(time.time()) + 600),
        "sub": "synthetic-subject",
        "email": "synthetic@example.test",
        "email_verified": "true",
        "name": "Synthetic identity",
        "nonce": "fixture-nonce",
    }
    responses = [Response({"id_token": "mock-id-token"})]
    monkeypatch.setattr(google_oauth, "_verify_id_token", lambda token: claims)
    monkeypatch.setattr(google_oauth.requests, "post", lambda *args, **kwargs: responses.pop(0))
    return claims, responses


def test_identity_is_bound_to_configured_google_client(google):
    assert google_oauth.exchange_code("mock-code", code_verifier="fixture-verifier", expected_nonce="fixture-nonce")["user_id"] == "google:synthetic-subject"


@pytest.mark.parametrize("value", [True, "true"])
def test_supported_verified_email_representations(google, value):
    google[0]["email_verified"] = value
    assert google_oauth.exchange_code("mock-code", code_verifier="fixture-verifier", expected_nonce="fixture-nonce")["email"] == "synthetic@example.test"


@pytest.mark.parametrize("key,value", [
    ("aud", "another.apps.googleusercontent.com"),
    ("aud", None),
    ("iss", "https://example.test"),
    ("iss", None),
    ("exp", "1"),
    ("exp", "invalid"),
    ("exp", None),
    ("sub", ""),
    ("email", ""),
    ("email_verified", False),
    ("email_verified", "false"),
    ("email_verified", 1),
])
def test_invalid_identity_claims_are_rejected(google, key, value):
    google[0][key] = value
    with pytest.raises(google_oauth.GoogleAuthError):
        google_oauth.exchange_code("mock-code", code_verifier="fixture-verifier", expected_nonce="fixture-nonce")


@pytest.mark.parametrize("response", [
    Response({}, 503), Response(ValueError("invalid JSON")), Response([]), Response({}),
])
def test_bad_provider_responses_fail_closed(google, response):
    google[1][0] = response
    with pytest.raises(google_oauth.GoogleAuthError):
        google_oauth.exchange_code("mock-code", code_verifier="fixture-verifier", expected_nonce="fixture-nonce")


def test_provider_timeout_redirects_instead_of_server_error(google, monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("synthetic provider timeout")

    monkeypatch.setattr(google_oauth.requests, "post", timeout)
    client = TestClient(create_app(), follow_redirects=False)
    login = client.get("/api/auth/login")
    query = parse_qs(urlsplit(login.headers["location"]).query)
    assert query["redirect_uri"] == ["http://localhost:18501/api/auth/callback"]
    assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
    state = client.cookies.get("rmf_oauth_state")
    response = client.get("/api/auth/callback", params={"state": state, "code": "mock-code"})
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:13310/account?auth=error&reason=verification"
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_missing_secret_fails_before_google_consent(google, monkeypatch):
    monkeypatch.delenv("AUTH_CLIENT_SECRET")
    response = TestClient(create_app(), follow_redirects=False).get("/api/auth/login")
    assert response.headers["location"] == "http://localhost:13310/account?auth=error&reason=config"

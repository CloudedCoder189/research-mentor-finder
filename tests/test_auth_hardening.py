"""Offline signed-token, login replay, and Google account separation checks."""
import datetime
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt, jwt, exceptions

import database
from api.auth import config, google_oauth, login_attempts
from api.main import create_app


@pytest.fixture
def auth(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "auth.db")
    database.initialize_database()
    monkeypatch.setenv("AUTH_CLIENT_ID", "offline.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "synthetic-secret")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "offline certificate")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(minutes=1))
            .not_valid_after(now+datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    signer = crypt.RSASigner.from_string(pem, key_id="offline-key")
    monkeypatch.setattr(google_oauth.google_id_token, "_fetch_certs", lambda *args, **kwargs:
                        {"offline-key": cert.public_bytes(serialization.Encoding.PEM).decode()})
    claims = dict(aud=config.client_id(), iss="https://accounts.google.com", iat=int(time.time())-1,
                  exp=int(time.time())+600, sub="alice", email="alice@example.test",
                  email_verified=True, nonce="offline-nonce")
    state = {"claims": claims, "requests": []}

    def post(url, **kwargs):
        state["requests"].append(kwargs)
        class Response:
            status_code = 200
            def json(self):
                return {"id_token": jwt.encode(signer, state["claims"]).decode()}
        return Response()

    monkeypatch.setattr(google_oauth.requests, "post", post)
    state["signer"] = signer
    state["private_pem"] = pem
    return state


def exchange():
    return google_oauth.exchange_code("offline-code", code_verifier="offline-verifier",
                                     expected_nonce="offline-nonce")


def test_real_signature_verifier_and_pkce_exchange(auth):
    assert exchange()["user_id"] == "google:alice"
    assert auth["requests"][0]["data"]["code_verifier"] == "offline-verifier"
    assert auth["requests"][0]["timeout"] == 10


@pytest.mark.parametrize("key,value", [
    ("aud", "wrong-client"), ("iss", "https://attacker.example.test"),
    ("exp", 1), ("iat", 9999999999), ("nonce", "wrong-nonce"),
    ("nonce", None), ("sub", None), ("email_verified", False),
])
def test_signed_but_invalid_claims_rejected(auth, key, value):
    auth["claims"][key] = value
    with pytest.raises(google_oauth.GoogleAuthError):
        exchange()


def test_forged_signature_rejected(auth, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    forged = jwt.encode(crypt.RSASigner.from_string(pem, key_id="offline-key"), auth["claims"]).decode()
    monkeypatch.setattr(google_oauth, "_google_payload", lambda *args: {"id_token": forged})
    with pytest.raises(google_oauth.GoogleAuthError):
        exchange()


def test_certificate_outage_fails_closed(auth, monkeypatch):
    def unavailable(*args, **kwargs):
        raise exceptions.TransportError("offline outage")
    monkeypatch.setattr(google_oauth.google_id_token, "_fetch_certs", unavailable)
    with pytest.raises(google_oauth.GoogleAuthError):
        exchange()


@pytest.mark.parametrize("token", ["", "invalid", "e30.e30.invalid"])
def test_malformed_tokens_fail_closed(auth, monkeypatch, token):
    monkeypatch.setattr(google_oauth, "_google_payload", lambda *args: {"id_token": token})
    with pytest.raises(google_oauth.GoogleAuthError):
        exchange()


def test_certificate_cache_honors_expiry_and_uses_bounded_timeout(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from cachecontrol import CacheControl
    from cachecontrol.cache import DictCache
    import requests

    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.send_header("Cache-Control", "public, max-age=60" if self.path == "/cached" else "no-store")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with requests.Session() as session:
            cached = CacheControl(session, cache=DictCache())
            original_request = cached.request
            timeouts = []
            def request(*args, **kwargs):
                timeouts.append(kwargs.get("timeout"))
                return original_request(*args, **kwargs)
            monkeypatch.setattr(cached, "request", request)
            transport = google_oauth.BoundedCertificateRequest(cached)
            base = f"http://127.0.0.1:{server.server_port}"
            for path in ["/cached", "/cached", "/fresh", "/fresh"]:
                assert transport(base+path).status == 200
            assert calls == ["/cached", "/fresh", "/fresh"]
            assert timeouts == [10]*4
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_rotated_certificate_key_verifies(auth, monkeypatch):
    token = jwt.encode(auth["signer"], auth["claims"]).decode()
    certs = google_oauth.google_id_token._fetch_certs(None, None)
    monkeypatch.setattr(google_oauth.google_id_token, "_fetch_certs", lambda *args, **kwargs: {"new-key": certs["offline-key"]})
    with pytest.raises(google_oauth.GoogleAuthError):
        google_oauth._verify_id_token(token)
    auth["signer"] = crypt.RSASigner.from_string(auth["private_pem"], key_id="new-key")
    assert google_oauth._verify_id_token(jwt.encode(auth["signer"], auth["claims"]).decode())["sub"] == "alice"


def start(client, auth):
    response = client.get("/api/auth/login")
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    auth["claims"]["nonce"] = query["nonce"][0]
    return query["state"][0], query


def finish(client, state):
    return client.get("/api/auth/callback", params={"state": state, "code": "offline-code"})


def test_callback_consumed_once_even_with_restored_browser_cookie(auth):
    client = TestClient(create_app(), follow_redirects=False)
    state, query = start(client, auth)
    assert "auth=success" in finish(client, state).headers["location"]
    assert login_attempts.challenge(auth["requests"][0]["data"]["code_verifier"]) == query["code_challenge"][0]
    client.cookies.set("rmf_oauth_state", state, path="/api/auth/callback")
    assert "reason=state" in finish(client, state).headers["location"]
    assert len(auth["requests"]) == 1


def test_failed_verification_consumes_attempt_and_issues_no_session(auth):
    client = TestClient(create_app(), follow_redirects=False)
    state, _ = start(client, auth)
    auth["claims"]["nonce"] = "attacker-nonce"
    assert "reason=verification" in finish(client, state).headers["location"]
    assert client.cookies.get(config.session_cookie_name()) is None
    assert client.cookies.get("rmf_oauth_state") is None
    assert login_attempts.consume(state) is None
    assert client.get("/api/profile").status_code == 401


def test_expired_attempt_rejected_without_provider_call(auth):
    client = TestClient(create_app(), follow_redirects=False)
    state, _ = start(client, auth)
    with database.connect() as conn:
        conn.execute("UPDATE oauth_login_attempts SET expires_at = 1")
    assert "reason=state" in finish(client, state).headers["location"]
    assert auth["requests"] == []


def test_parallel_callbacks_have_only_one_winner(auth):
    state, challenge, nonce = login_attempts.begin()
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM oauth_login_attempts").fetchone()
        assert row["state_hash"] != state
        assert login_attempts.challenge(row["verifier"]) == challenge
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(login_attempts.consume, [state]*4))
    assert sum(value is not None for value in outcomes) == 1
    assert next(value for value in outcomes if value)["nonce"] == nonce


def test_capacity_bounded_and_expired_entries_cleaned(auth, monkeypatch):
    monkeypatch.setattr(login_attempts, "MAX_PENDING", 1)
    login_attempts.begin()
    with pytest.raises(login_attempts.LoginBusyError):
        login_attempts.begin()
    with database.connect() as conn:
        conn.execute("UPDATE oauth_login_attempts SET expires_at = 1")
    assert login_attempts.begin()[0]


def test_google_account_switch_revokes_old_session_and_separates_profile(auth):
    client = TestClient(create_app(), follow_redirects=False)
    state, _ = start(client, auth)
    assert "auth=success" in finish(client, state).headers["location"]
    old_token = client.cookies.get(config.session_cookie_name())
    me = client.get("/api/auth/me").json()
    client.headers["X-CSRF-Token"] = me["csrf_token"]
    assert client.put("/api/profile", json={"interest_text": "Synthetic Alice robotics"}).status_code == 200
    auth["claims"].update(sub="bob", email="bob@example.test")
    state, _ = start(client, auth)
    assert "auth=success" in finish(client, state).headers["location"]
    assert client.get("/api/auth/me").json()["user"]["user_id"] == "google:bob"
    assert "Synthetic Alice robotics" not in str(client.get("/api/profile").json())
    stale = TestClient(create_app(), follow_redirects=False)
    stale.cookies.set(config.session_cookie_name(), old_token, path="/")
    assert stale.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json={"interest_text": "cross-account mutation"}).status_code == 403
    auth["claims"].update(sub="alice", email="alice@example.test")
    state, _ = start(stale, auth)
    finish(stale, state)
    assert "Synthetic Alice robotics" in str(stale.get("/api/profile").json())

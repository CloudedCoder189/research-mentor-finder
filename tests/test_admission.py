"""Offline admission boundaries, concurrency, and untrusted-header checks."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.admission import Admission, AdmissionMiddleware, category, client_address


def test_client_limit_recovers_and_does_not_slide_on_denial():
    now = [0]
    limiter = Admission(clock=lambda: now[0], policies={"ranking": (2, 60, 20)})
    assert limiter.admit("ranking", "alice") == 0
    assert limiter.admit("ranking", "alice") == 0
    assert limiter.admit("ranking", "alice") == 60
    assert limiter.admit("ranking", "bob") == 0
    now[0] = 59
    assert limiter.admit("ranking", "alice") == 1
    now[0] = 60
    assert limiter.admit("ranking", "alice") == 0


def test_global_limit_applies_across_rotating_clients():
    limiter = Admission(policies={"login": (10, 300, 2)})
    assert limiter.admit("login", "a") == 0
    assert limiter.admit("login", "b") == 0
    assert limiter.admit("login", "c") > 0


def test_default_login_policy_allows_twenty_attempts_and_recovers_in_thirty_seconds():
    now = [0]
    limiter = Admission(clock=lambda: now[0])
    assert all(limiter.admit("login", "shared-network") == 0 for _ in range(20))
    assert limiter.admit("login", "shared-network") == 30
    now[0] = 29
    assert limiter.admit("login", "shared-network") == 1
    now[0] = 30
    assert limiter.admit("login", "shared-network") == 0


def test_default_global_login_cap_survives_network_rotation():
    limiter = Admission(clock=lambda: 0)
    assert all(limiter.admit("login", f"network-{i}") == 0 for i in range(60))
    assert limiter.admit("login", "another-network") == 30


def test_capacity_is_bounded_without_evicting_active_limits():
    now = [0]
    limiter = Admission(clock=lambda: now[0], max_clients=2, policies={"ranking": (1, 60, 100)})
    assert limiter.admit("ranking", "a") == 0
    assert limiter.admit("ranking", "b") == 0
    assert limiter.admit("ranking", "c") == 60
    assert limiter.admit("ranking", "a") == 60
    assert len(limiter.clients) == 2
    assert all(isinstance(key[1], bytes) for key in limiter.clients)
    now[0] = 60
    assert limiter.admit("ranking", "c") == 0


def test_parallel_requests_cannot_overrun_allowance():
    limiter = Admission(policies={"ranking": (3, 60, 100)})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: limiter.admit("ranking", "a"), range(30)))
    assert results.count(0) == 3


def request(peer, headers):
    pairs = headers.items() if isinstance(headers, dict) else headers
    return Request({"type": "http", "method": "GET", "path": "/",
                    "client": (peer, 1234), "headers": [(k.lower().encode(), v.encode()) for k, v in pairs]})


@pytest.mark.parametrize("header", ["X-RMF-Client-IP", "X-Forwarded-For", "X-Real-IP"])
def test_remote_peer_cannot_choose_client_address(monkeypatch, header):
    monkeypatch.setenv("RATE_LIMIT_TRUST_PILOT_PROXY", "1")
    assert client_address(request("8.8.8.8", {header: "1.1.1.1"})) == "8.8.8.8"


def test_loopback_requires_explicit_proxy_trust_and_valid_single_global_ip(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_TRUST_PILOT_PROXY", raising=False)
    assert client_address(request("127.0.0.1", {"X-RMF-Client-IP": "8.8.8.8"})) == "127.0.0.1"
    monkeypatch.setenv("RATE_LIMIT_TRUST_PILOT_PROXY", "1")
    assert client_address(request("127.0.0.1", {"X-RMF-Client-IP": "8.8.8.8"})) == "8.8.8.8"
    for invalid in ["garbage", "8.8.8.8, 1.1.1.1", "10.0.0.1", "::1"]:
        assert client_address(request("127.0.0.1", {"X-RMF-Client-IP": invalid})) == "127.0.0.1"


@pytest.mark.parametrize("values", [
    ["8.8.8.8", "1.1.1.1"],
    ["8.8.8.8", "8.8.8.8"],
])
def test_duplicate_forwarded_client_ip_headers_fall_back_to_socket_peer(monkeypatch, values):
    monkeypatch.setenv("RATE_LIMIT_TRUST_PILOT_PROXY", "1")
    headers = [("X-RMF-Client-IP", value) for value in values]
    assert client_address(request("127.0.0.1", headers)) == "127.0.0.1"


@pytest.mark.parametrize("name", ["X-Real-IP", "X-Forwarded-For", "Forwarded"])
def test_unverified_forwarding_headers_never_choose_client_identity(monkeypatch, name):
    monkeypatch.setenv("RATE_LIMIT_TRUST_PILOT_PROXY", "1")
    assert client_address(request("127.0.0.1", {name: "8.8.8.8"})) == "127.0.0.1"


def test_ipv6_privacy_addresses_share_network_bucket():
    assert client_address(request("2606:4700:4700::1111", {})) == client_address(request("2606:4700:4700::9999", {}))


@pytest.mark.parametrize("method,path,expected", [
    ("POST", "/api/search/", "ranking"), ("POST", "/api/recommendations", "ranking"),
    ("POST", "/api/recommendations/explain", "ranking"), ("GET", "/api/auth/login/", "login"),
    ("OPTIONS", "/api/search", None), ("GET", "/api/health", None),
    ("GET", "/api/auth/callback", None), ("POST", "/api/auth/logout", None),
])
def test_only_admission_routes_are_counted(method, path, expected):
    assert category(method, path) == expected


def test_http_denial_skips_work_and_expires(monkeypatch):
    monkeypatch.setenv("APP_MODE", "staging")
    now, calls = [0], []
    limiter = Admission(clock=lambda: now[0], policies={"ranking": (1, 60, 10)})
    app = FastAPI()
    app.add_middleware(AdmissionMiddleware, limiter=limiter)
    @app.post("/api/search")
    def search():
        calls.append(1)
        return {"ok": True}
    with TestClient(app) as client:
        assert client.post("/api/search").status_code == 200
        denied = client.post("/api/search", headers={"X-Forwarded-For": "1.1.1.1"})
        assert denied.status_code == 429
        assert denied.headers["Retry-After"] == "60"
        assert denied.headers["Content-Type"].startswith("application/json")
        assert denied.headers["Cache-Control"] == "no-store"
        assert "60 seconds" in denied.json()["detail"]
        assert len(calls) == 1
        now[0] = 60
        assert client.post("/api/search").status_code == 200


def test_login_denial_happens_before_attempt_creation(monkeypatch):
    from api.main import create_app
    from api.auth import login_attempts
    monkeypatch.setenv("APP_MODE", "local")
    monkeypatch.setenv("RATE_LIMIT_LOCAL", "1")
    monkeypatch.setenv("AUTH_CLIENT_ID", "synthetic")
    monkeypatch.setenv("AUTH_CLIENT_SECRET", "synthetic")
    app = create_app()
    app.state.admission.policies = {"login": (1, 300, 10)}
    calls = []
    def begin(*args):
        calls.append(1)
        return "synthetic-state", "challenge", "nonce"
    monkeypatch.setattr(login_attempts, "begin", begin)
    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/api/auth/login").status_code == 307
        denied = client.get("/api/auth/login")
        assert denied.status_code == 429
        assert denied.headers["Retry-After"] == "300"
        assert denied.headers["Content-Type"].startswith("text/html")
        assert "Please wait before signing in" in denied.text
        assert 'href="/account"' in denied.text
        assert "300 seconds" in denied.text
        assert 'name="viewport"' in denied.text
        assert "synthetic-state" not in denied.text
        assert "default-src 'none'" in denied.headers["Content-Security-Policy"]
        assert len(calls) == 1


def test_managed_proxy_contract_and_packaging():
    from scripts.prepare_pilot_package import ROOT, selected_files
    from deploy.pilot.provision import settings
    assert ROOT / "api/admission.py" in selected_files(ROOT)
    assert settings(ROOT / "test-runtime/synthetic-managed")["RATE_LIMIT_TRUST_PILOT_PROXY"] == "1"
    runner = (ROOT / "scripts/run_managed_api.py").read_text()
    assert "proxy_headers=False" in runner and 'host="127.0.0.1"' in runner
    for name in ("Caddyfile", "Caddyfile.public"):
        caddy = (ROOT / "deploy/pilot" / name).read_text()
        assert "header_up X-RMF-Client-IP {http.request.header.X-Real-IP}" in caddy
        assert "header_up -Authorization" in caddy

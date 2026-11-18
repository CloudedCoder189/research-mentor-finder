"""Bounded, process-local admission for the single-worker pilot.

No account rows, raw client addresses, or persistent request history are stored.
Additional workers/replicas require a shared limiter before scaling.
"""
import hashlib
import hmac
import ipaddress
import math
import os
import secrets
import threading
import time

from fastapi import Request
from starlette.responses import HTMLResponse, JSONResponse

POLICIES = {"ranking": (60, 60, 300), "login": (20, 30, 60), "resume": (5, 60, 20), "usage": (60, 60, 600)}


def login_limit_response(retry, headers):
    # Only a server-derived integer enters this document; no request data is reflected.
    seconds = max(1, int(retry))
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Please wait before signing in | Research Mentor Finder</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f8fc;color:#102039;
font:16px/1.6 system-ui,sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}}
main{{width:100%;max-width:480px;background:white;border:1px solid #d6e1ef;
border-radius:16px;padding:32px;box-shadow:0 2px 6px #1020390d}}
h1{{font-size:26px;line-height:1.25;margin:12px 0 20px}}p{{margin:12px 0}}
.brand{{color:#2468bc;font-weight:600}}a{{display:inline-block;margin-top:16px;
padding:12px 18px;background:#2468bc;color:white;border-radius:8px;text-decoration:none;font-weight:600}}
a:focus-visible{{outline:3px solid #102039;outline-offset:4px}}
.hint{{color:#46566d;font-size:14px}}
</style></head><body><main>
<div class="brand">Research Mentor Finder</div>
<h1>Please wait before signing in</h1>
<p>There have been several sign-in attempts from this network.
Please wait about <strong>{seconds} seconds</strong>, then try signing in again.</p>
<p class="hint">Your account and saved researchers are unchanged.
Refreshing this page does not extend the wait.</p>
<a href="/account">Back to Account</a>
</main></body></html>""", status_code=429, headers={**headers,
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        "X-Frame-Options": "DENY",
    })


def category(method, path):
    if method == "POST" and path.rstrip("/") == "/api/usage/pageview":
        return "usage"
    if method == "POST" and path.rstrip("/") == "/api/profile/resume-preview":
        return "resume"
    if method == "GET" and path.rstrip("/") == "/api/auth/login":
        return "login"
    if method == "POST" and path.rstrip("/") in {
        "/api/search", "/api/recommendations", "/api/recommendations/explain",
    }:
        return "ranking"
    return None


def client_address(request):
    # Managed Uvicorn must have proxy_headers=False: client is the socket peer.
    peer = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if address.is_loopback and os.getenv("RATE_LIMIT_TRUST_PILOT_PROXY") == "1":
        supplied = request.headers.get("X-RMF-Client-IP", "")
        try:
            forwarded = ipaddress.ip_address(supplied)
            if forwarded.is_global:
                address = forwarded
        except ValueError:
            pass
    # Group IPv6 privacy addresses from the same /64 to limit easy rotation.
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class Admission:
    def __init__(self, *, clock=time.monotonic, policies=None, max_clients=4096):
        self.clock = clock
        self.policies = POLICIES if policies is None else policies
        self.max_clients = max_clients
        self.clients = {}
        self.global_counts = {}
        self.salt = secrets.token_bytes(32)
        self.lock = threading.Lock()
        self.next_cleanup = 0

    def admit(self, group, address):
        limit, period, global_limit = self.policies[group]
        key = (group, hmac.new(self.salt, address.encode(), hashlib.sha256).digest())
        with self.lock:
            now = self.clock()
            if now >= self.next_cleanup:
                self.clients = {k: v for k, v in self.clients.items() if v[1] > now}
                self.next_cleanup = now + 30
            count, expiry = self.clients.get(key, (0, now + period))
            if expiry <= now:
                count, expiry = 0, now + period
            total, total_expiry = self.global_counts.get(group, (0, now + period))
            if total_expiry <= now:
                total, total_expiry = 0, now + period
            if count >= limit:
                return max(1, math.ceil(expiry - now))
            if total >= global_limit:
                return max(1, math.ceil(total_expiry - now))
            if key not in self.clients and len(self.clients) >= self.max_clients:
                # Never evict active limits to let new addresses bypass them.
                return max(1, math.ceil(min(v[1] for v in self.clients.values()) - now))
            self.clients[key] = (count + 1, expiry)
            self.global_counts[group] = (total + 1, total_expiry)
        return 0


class AdmissionMiddleware:
    def __init__(self, app, *, limiter):
        self.app, self.limiter = app, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            group = category(scope["method"], scope["path"])
            enabled = os.getenv("APP_MODE", "local").strip().lower() != "local"
            enabled = enabled or os.getenv("RATE_LIMIT_LOCAL") == "1"
            if group and enabled:
                retry = self.limiter.admit(group, client_address(Request(scope)))
                if retry:
                    headers = {"Retry-After": str(retry), "Cache-Control": "no-store",
                               "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
                    response = login_limit_response(retry, headers) if group == "login" else JSONResponse(
                        {"detail": f"Too many requests. Please try again in {retry} seconds."},
                        status_code=429,
                        headers=headers,
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)

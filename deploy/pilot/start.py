"""One private pilot origin; supervise API, frontend and reverse proxy."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from deploy.pilot.provision import access_mode, provision, settings, validate_gate
from deploy.pilot.monitor import monitoring_healthy


class Health(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self._respond(write_body=True)

    def do_HEAD(self):
        self._respond(write_body=False)

    def _respond(self, *, write_body):
        try:
            with urllib.request.urlopen("http://127.0.0.1:18501/api/health", timeout=2) as response:
                data=json.load(response)
                if data.get("retention", {}).get("status") != "ok":
                    raise ValueError("Maintenance unavailable")
                if urlsplit(self.path).path=="/__pilot_monitor" and not monitoring_healthy(data):
                    raise ValueError("Monitoring unavailable")
            with urllib.request.urlopen("http://127.0.0.1:13310", timeout=2) as response:
                if response.status != 200:
                    raise ValueError("Frontend unavailable")
            status = 200
        except Exception:
            status = 503
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if write_body:
            self.wfile.write(b"ready" if status == 200 else b"unavailable")


def main():
    os.umask(0o077)
    if (ROOT / ".env").exists():
        raise ValueError("Local .env must not be deployed.")
    validate_gate(os.environ)
    proxy_config = ROOT / "deploy/pilot" / ("Caddyfile.public" if access_mode(os.environ) == "public" else "Caddyfile")
    os.environ.update(settings("/var/data/professor-finder"))
    import runtime_config
    from api.production_config import validate_production_config
    validate_production_config()
    subprocess.run(["caddy", "validate", "--config", str(proxy_config), "--adapter", "caddyfile"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    provision("/var/data/professor-finder", ROOT / "deploy/pilot/public-seed.db", ROOT / "deploy/pilot/seed-report.json")
    from deploy.pilot.repair_links import apply_reviewed_links
    link_repair = apply_reviewed_links("/var/data/professor-finder/runtime.db")
    print("RMF_LINK_REPAIR:" + json.dumps(link_repair), flush=True)
    health = ThreadingHTTPServer(("127.0.0.1", 18503), Health)
    health.daemon_threads = True
    threading.Thread(target=health.serve_forever, daemon=True).start()
    children = []
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    try:
        commands = [([sys.executable, "scripts/run_managed_api.py"], ROOT),
                    (["node", "scripts/run_managed_frontend.mjs"], ROOT / "frontend"),
                    (["caddy", "run", "--config", str(proxy_config), "--adapter", "caddyfile"], ROOT)]
        for command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        while not stopped.wait(0.5):
            if any(child.poll() is not None for child in children):
                print("Pilot service stopped; shutting down peer services.", flush=True)
                return 1
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
        health.shutdown()
        health.server_close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("Pilot startup failed. Check required configuration and storage; no secrets logged.", flush=True)
        sys.exit(1)

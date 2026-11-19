import hashlib
import json
import sqlite3
import re
from contextlib import closing

import pytest

import database
from deploy.pilot.provision import provision, settings, validate_gate
from scripts.export_public_seed import export
from scripts.prepare_pilot_package import selected_files, docker_context_allowlist, ROOT


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    source = tmp_path / "source.db"
    monkeypatch.setattr(database, "DB_PATH", source)
    database.initialize_database(run_maintenance=False)
    database.upsert_professors([{"name":"Synthetic Academic","university":"Test University","email":"academic@example.test"}])
    database.upsert_user(user_id="private-local",email="private@example.test")
    seed = tmp_path / "seed.db"
    report = tmp_path / "report.json"
    report.write_text(json.dumps(export(source, seed)),encoding="utf-8")
    root = tmp_path / "hosted"
    for key, value in settings(root).items():
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(database,"DB_PATH",root / "runtime.db")
    return root,seed,report


def test_private_pilot_first_start_and_restart_never_reseed_users(pilot):
    root,seed,report = pilot
    assert provision(root,seed,report)
    with closing(sqlite3.connect(root / "runtime.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 1
    database.upsert_user(user_id="hosted-user",email="hosted@example.test")
    assert not provision(root,seed,report)
    with closing(sqlite3.connect(root / "runtime.db")) as conn:
        assert conn.execute("SELECT user_id FROM users").fetchall() == [("hosted-user",)]


def test_missing_ledger_on_restart_does_not_regenerate(pilot):
    root,seed,report = pilot
    provision(root,seed,report)
    (root / "managed/ledger.db").unlink()
    with pytest.raises(ValueError,match="incomplete"):
        provision(root,seed,report)
    assert not (root / "managed/ledger.db").exists()


@pytest.mark.parametrize("failure", ["tampered_seed","unmarked_private_files"])
def test_provision_rejects_unsafe_initialization(pilot, failure):
    root,seed,report = pilot
    if failure == "tampered_seed":
        seed.write_bytes(seed.read_bytes()+b"tamper")
    else:
        root.mkdir()
        (root / "private.txt").write_text("preserve",encoding="utf-8")
    with pytest.raises(ValueError):
        provision(root,seed,report)
    assert not (root / "runtime.db").exists()


@pytest.mark.parametrize("values", [{}, {"PILOT_BASIC_USER":"owner","PILOT_PASSWORD_HASH":"plaintext"},
    {"PILOT_BASIC_USER":"owner } bad","PILOT_PASSWORD_HASH":"$2b$12$"+"A"*53},
    {"PILOT_BASIC_USER":"owner","PILOT_PASSWORD_HASH":"$2b$12$"+"A"*53,"PORT":"18501"}])
def test_gate_rejects_missing_secret_plaintext_injection_and_port_collision(values):
    with pytest.raises(ValueError):
        validate_gate(values)


def test_gate_accepts_bcrypt_hash_and_hosted_port():
    validate_gate({"PILOT_BASIC_USER":"owner","PILOT_PASSWORD_HASH":"$2b$12$"+"A"*53,"PORT":"8080"})


def test_package_selection_excludes_all_runtime_and_evidence():
    files = selected_files(ROOT)
    for p in files:
        parts=p.relative_to(ROOT).parts
        assert parts[0] != "data"
        assert not set(parts) & {"test-runtime","evidence",".venv","node_modules",".next","__pycache__"}
        assert p.name != ".env" and p.suffix != ".db"


def test_package_includes_every_frontend_alias_import():
    files = selected_files(ROOT)
    relative = {p.relative_to(ROOT / "frontend").as_posix() for p in files if p.is_relative_to(ROOT / "frontend")}
    for p in files:
        if p.suffix in {".ts", ".tsx", ".mjs", ".js"} and p.is_relative_to(ROOT / "frontend"):
            for alias in re.findall(r'["\'](@/[^"\']+)["\']',p.read_text(encoding="utf-8")):
                base=alias[2:]
                assert any(candidate in relative for candidate in [base,base+".ts",base+".tsx",base+".mjs",base+".js",base+"/index.ts",base+"/index.tsx"]), alias


def test_checkout_dockerignore_denies_direct_builds():
    """Public source checkout is not a deployment context with reviewed seed data."""
    lines = [line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert lines == ["*"]


def test_staged_docker_context_reincludes_only_explicit_files():
    source = [
        "requirements.txt", "api/main.py", "frontend/app/page.tsx",
        "frontend/package.json", "deploy/pilot/public-seed.db",
        "deploy/pilot/seed-report.json",
    ]
    lines = docker_context_allowlist(source).splitlines()
    assert lines[2] == "*"
    allowed = {line[1:] for line in lines if line.startswith("!")}
    assert allowed == set(source) | {
        "api", "frontend", "frontend/app", "deploy", "deploy/pilot",
    }
    assert not any("manifest" in path or ".env" in path for path in allowed)


@pytest.mark.parametrize("path", [
    "../private.txt", "/tmp/secrets.txt", ".env", "frontend/.env.local",
    "data/users.db", "api/private.db", "frontend/node_modules/secret.js",
    "deploy/pilot/private.pem", "backups/data.json",
])
def test_staged_docker_context_refuses_private_paths(path):
    with pytest.raises(ValueError, match="Unsafe Docker context path"):
        docker_context_allowlist(["api/main.py", path])

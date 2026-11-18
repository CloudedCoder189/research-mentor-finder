"""Initialize a fresh hosted store only; never re-seed an existing private store."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def access_mode(environ):
    mode = environ.get("PILOT_ACCESS_MODE", "private").strip().lower()
    if mode not in {"private", "public"}:
        raise ValueError("PILOT_ACCESS_MODE must be private or public.")
    return mode


def settings(root):
    root = Path(root).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
        raise ValueError("Linked pilot storage is forbidden.")
    public = access_mode(os.environ) == "public"
    return {"PROFESSOR_DB_PATH": str(root / "runtime.db"),
            "RETENTION_ROOT": str(root / "managed"),
            "RETENTION_KEY_FILE": str(root / "retention-key.txt"),
            "GMAIL_TOKEN_DIR": str(root / "gmail"),
            "MANAGED_API_PORT": "18501", "MANAGED_FRONTEND_PORT": "13310",
            "APP_MODE": "public" if public else "staging", "AUTH_COOKIE_SECURE": "true",
            "RATE_LIMIT_TRUST_PILOT_PROXY": "1",
            "AUTH_ALLOW_DEV_LOGIN": "false", "OPENAI_API_KEY": "", "AI_EXPLANATIONS": "0",
            # Public core launch excludes Gmail regardless of inherited pilot settings.
            **({"GMAIL_CLIENT_ID": "", "GMAIL_CLIENT_SECRET": ""} if public else {})}


def validate_gate(environ):
    mode = access_mode(environ)
    if mode == "private" and not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", environ.get("PILOT_BASIC_USER", "")):
        raise ValueError("Configure a private-pilot username.")
    if mode == "private" and not re.fullmatch(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}", environ.get("PILOT_PASSWORD_HASH", "")):
        raise ValueError("Configure a bcrypt pilot-password hash, never a plaintext password.")
    if mode == "private" and not 12 <= int(environ["PILOT_PASSWORD_HASH"].split("$")[2]) <= 16:
        raise ValueError("Use a bcrypt work factor from 12 to 16.")
    port = int(environ.get("PORT", "8080"))
    if not 1024 <= port <= 65535 or port in {18501, 18503, 13310}:
        raise ValueError("Choose a distinct unprivileged public port.")


def provision(root, seed, report):
    import database
    from api.retention import Store, initialize
    root, seed, report = Path(root).absolute(), Path(seed).resolve(), Path(report).resolve()
    expected = settings(root)
    if any(os.getenv(k) != v for k, v in expected.items()):
        raise ValueError("Hosted storage/configuration mismatch.")
    marker = root / "initialized.json"
    if marker.exists():
        if marker.is_symlink() or marker.is_junction() or json.loads(marker.read_text(encoding="utf-8")) != {"schema": 1}:
            raise ValueError("Invalid pilot initialization marker.")
        if not (root / "runtime.db").is_file() or Path(database.DB_PATH).resolve() != (root / "runtime.db").resolve():
            raise ValueError("Pilot runtime is missing; explicit recovery is required.")
        Store()  # Do not recreate missing keys/ledger, even if a seed is available.
        return False
    if root.exists() and any(root.iterdir()):
        raise ValueError("Unmarked nonempty pilot storage requires operator recovery.")
    metadata = json.loads(report.read_text(encoding="utf-8"))
    if metadata.get("private_tables_copied") is not False or hashlib.sha256(seed.read_bytes()).hexdigest() != metadata.get("sha256"):
        raise ValueError("Public seed manifest verification failed.")
    with closing(sqlite3.connect(seed.as_uri() + "?mode=ro", uri=True)) as source:
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {"professors", "sqlite_sequence"} or "professors" not in tables:
            raise ValueError("Seed contains unexpected tables.")
        if source.execute("SELECT COUNT(*) FROM professors").fetchone()[0] != metadata.get("rows"):
            raise ValueError("Public seed row count mismatch.")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(root / "runtime.db", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(root / "runtime.db")) as destination:
            source.backup(destination)
    if Path(database.DB_PATH).resolve() != (root / "runtime.db").resolve():
        raise ValueError("Imported database module has a different runtime path.")
    database.initialize_database(run_maintenance=False)
    initialize().maintain()
    with marker.open("x", encoding="utf-8") as stream:
        json.dump({"schema": 1}, stream)
    return True

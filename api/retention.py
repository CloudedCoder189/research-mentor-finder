"""Opt-in managed retention. Historical files are never discovered or pruned."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

import database

UTC = timezone.utc
RETENTION = timedelta(days=30)
BACKUP_NAME = re.compile(r"backup-[0-9a-f]{32}\.fernet\Z")
LOG_NAME = re.compile(r"(api|frontend)-\d{4}-\d{2}-\d{2}\.jsonl\Z")
CHECK_SECONDS = 3600


def enabled():
    return bool(os.getenv("RETENTION_ROOT"))


def _plain(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError("Managed storage must not contain linked paths.")
    if any(p.is_symlink() or p.is_junction() for p in path.parents):
        raise ValueError("Managed storage must not contain linked ancestors.")
    return path


def _identity():
    return hashlib.sha256(str(Path(database.DB_PATH).resolve()).encode()).hexdigest()


class Store:
    def __init__(self):
        if not enabled() or not os.getenv("RETENTION_KEY_FILE"):
            raise ValueError("Managed retention requires a root and an existing key file.")
        self.root = _plain(Path(os.environ["RETENTION_ROOT"]).absolute())
        self.key = _plain(Path(os.environ["RETENTION_KEY_FILE"]).absolute())
        self.ledger = self.root / "ledger.db"
        marker = _plain(self.root / "store.json")
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        key = self.key.read_bytes()
        if metadata != {"schema": 1, "database": _identity(), "key": hashlib.sha256(key).hexdigest()}:
            raise ValueError("Managed store does not match this runtime or key.")
        if self.root == Path(database.DB_PATH).parent.resolve() or self.root in self.key.parents:
            raise ValueError("The encryption key must live outside managed storage.")
        self.cipher = Fernet(key)
        for path in (self.ledger, self.root / "backups", self.root / "logs"):
            _plain(path)
            if not path.exists():
                raise ValueError("Managed storage is incomplete; recovery is required.")
        with closing(self.connect()) as conn:
            if conn.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise ValueError("The deletion ledger requires DELETE journal mode.")
            conn.execute("SELECT subject_hash, deleted_at FROM account_deletion_receipts LIMIT 0")

    def connect(self):
        conn = sqlite3.connect(self.ledger.as_uri() + "?mode=rw", uri=True, timeout=30)
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def maintain(self, now=None, *, force_backup=False, cleanup=True):
        now = now or datetime.now(UTC)
        with closing(self.connect()) as ledger:
            ledger.execute("BEGIN IMMEDIATE")  # Serializes daily backup creation across workers.
            # Recover a completed encrypted file if a crash preceded registry commit.
            for file in (self.root / "backups").iterdir():
                if BACKUP_NAME.fullmatch(file.name) and not ledger.execute("SELECT 1 FROM backups WHERE name=?", (file.name,)).fetchone():
                    _plain(file)
                    try:
                        stamp = self.cipher.extract_timestamp(file.read_bytes())
                    except InvalidToken:
                        raise ValueError("Unrecognized backup content; operator recovery required.") from None
                    ledger.execute("INSERT INTO backups VALUES (?, ?)", (file.name, datetime.fromtimestamp(stamp, UTC).isoformat()))
            rows = ledger.execute("SELECT name, created_at FROM backups").fetchall()
            for name, stamp in rows if cleanup else []:
                if not BACKUP_NAME.fullmatch(name):
                    raise ValueError("Unexpected managed backup entry; cleanup refused.")
                created = datetime.fromisoformat(stamp)
                file = _plain(self.root / "backups" / name)
                if not file.exists() or now - created >= RETENTION:
                    file.unlink(missing_ok=True)
                    ledger.execute("DELETE FROM backups WHERE name=?", (name,))
            for file in (self.root / "logs").iterdir() if cleanup else []:
                if not LOG_NAME.fullmatch(file.name):
                    continue  # Unregistered/unknown files are never deleted.
                created = datetime.strptime(file.name.split("-", 1)[1][:-6], "%Y-%m-%d").replace(tzinfo=UTC)
                if now - created >= RETENTION:
                    _plain(file).unlink(missing_ok=True)
            recent = ledger.execute("SELECT MAX(created_at) FROM backups").fetchone()[0]
            if not force_backup and recent and now - datetime.fromisoformat(recent) < timedelta(days=1):
                ledger.commit()
                return False
            name = f"backup-{uuid.uuid4().hex}.fernet"
            destination = self.root / "backups" / name
            deadline = time.monotonic() + 60
            def progress(status, remaining, total):
                if time.monotonic() > deadline:
                    raise TimeoutError("Snapshot deadline exceeded.")
            with closing(sqlite3.connect(Path(database.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)) as source, closing(sqlite3.connect(":memory:")) as snapshot:
                source.backup(snapshot, pages=256, progress=progress)
                snapshot.execute("PRAGMA secure_delete=ON")
                for table in ("sessions", "oauth_login_attempts", "ai_explanation_requests", "query_embedding_cache"):
                    if snapshot.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                        snapshot.execute(f'DELETE FROM "{table}"')
                snapshot.commit()
                if snapshot.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Snapshot integrity check failed.")
                ciphertext = self.cipher.encrypt_at_time(snapshot.serialize(), int(now.timestamp()))
            try:
                with destination.open("xb") as stream:
                    stream.write(ciphertext)
                    stream.flush()
                    os.fsync(stream.fileno())
                ledger.execute("INSERT INTO backups VALUES (?, ?)", (name, now.isoformat()))
                ledger.commit()
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
            return True

    def attach(self, conn):
        if conn.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise sqlite3.OperationalError("Atomic deletion receipts require DELETE journal mode.")
        conn.execute("ATTACH DATABASE ? AS deletion_ledger", (str(self.ledger),))
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA deletion_ledger.synchronous=FULL")


def initialize():
    """Explicit setup only: refuse existing stores/keys, seed existing receipts."""
    root = _plain(Path(os.environ["RETENTION_ROOT"]).absolute())
    key = _plain(Path(os.environ["RETENTION_KEY_FILE"]).absolute())
    if root.exists() or key.exists() or root == Path(database.DB_PATH).parent.resolve() or root in key.parents:
        raise ValueError("Choose a new dedicated store and an external new key file.")
    with closing(sqlite3.connect(Path(database.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)) as source:
        if source.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError("Runtime must use DELETE journal mode for atomic receipts.")
        receipts = source.execute("SELECT subject_hash, deleted_at FROM account_deletion_receipts").fetchall() if source.execute("SELECT 1 FROM sqlite_master WHERE name='account_deletion_receipts'").fetchone() else []
    root.mkdir(parents=True, exist_ok=False)
    key.parent.mkdir(parents=True, exist_ok=True)
    material = Fernet.generate_key()
    descriptor = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(material)
    (root / "backups").mkdir()
    (root / "logs").mkdir()
    with closing(sqlite3.connect(root / "ledger.db")) as conn:
        conn.execute("CREATE TABLE account_deletion_receipts(subject_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)")
        conn.executemany("INSERT INTO account_deletion_receipts VALUES (?, ?)", receipts)
        conn.execute("CREATE TABLE backups(name TEXT PRIMARY KEY, created_at TEXT NOT NULL)")
        conn.commit()
    (root / "store.json").write_text(json.dumps({"schema": 1, "database": _identity(), "key": hashlib.sha256(material).hexdigest()}), encoding="utf-8")
    return Store()


class PrivateSafeHandler(logging.Handler):
    """Store event categories, never arbitrary messages, tracebacks or request data."""
    def __init__(self, store):
        super().__init__()
        self.store = store

    def emit(self, record):
        now = datetime.now(UTC)
        event = record.msg if record.name == "managed_retention" and record.msg in {"maintenance_ok", "maintenance_failed"} else "application_event"
        payload = {"time": now.isoformat(), "level": record.levelname, "event": event}
        try:
            file = _plain(self.store.root / "logs" / f"api-{now.date()}.jsonl")
            with file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload) + "\n")
        except (OSError, ValueError):
            # Logging failures must never leak the original record to stderr.
            pass


@asynccontextmanager
async def lifespan(app):
    if not enabled():
        yield
        return
    store = Store()
    with closing(sqlite3.connect(Path(database.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)) as runtime:
        if runtime.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            raise ValueError("Managed account deletion requires DELETE journal mode.")
    await asyncio.to_thread(store.maintain)
    app.state.retention = {"status": "ok", "last_success": datetime.now(UTC).isoformat()}
    from api.offsite import enabled as offsite_enabled, Archive
    async def synchronize_offsite():
        if offsite_enabled():
            try:
                app.state.offsite = await asyncio.to_thread(Archive(store).sync)
            except Exception:
                app.state.offsite = {"status":"error"}
                logging.getLogger("managed_retention").error("offsite_failed")
        else:
            app.state.offsite = {"status":"disabled"}
    await synchronize_offsite()
    async def worker():
        while True:
            await asyncio.sleep(CHECK_SECONDS)
            try:
                await asyncio.to_thread(store.maintain)
                app.state.retention = {"status": "ok", "last_success": datetime.now(UTC).isoformat()}
                logging.getLogger("managed_retention").info("maintenance_ok")
            except Exception:
                app.state.retention["status"] = "error"
                logging.getLogger("managed_retention").error("maintenance_failed")
            await synchronize_offsite()
    task = asyncio.create_task(worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

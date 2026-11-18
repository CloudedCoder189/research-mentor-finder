"""Restore to a NEW file, applying receipts from the current private runtime.

Never points the app at the restored file and never modifies the backup/ledger.
Do not restore Gmail credential files: deleted grants must stay disconnected.
"""
import argparse
import hashlib
import sqlite3
import os
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=result.tzinfo or timezone.utc)


def restore(backup, ledger_database, destination, *, cipher=None):
    backup, ledger_database, destination = (Path(p).resolve() for p in (backup, ledger_database, destination))
    if destination.exists() or destination in {backup, ledger_database}:
        raise ValueError("Choose a new destination; existing files are never overwritten.")
    with closing(sqlite3.connect(ledger_database.as_uri()+"?mode=ro", uri=True)) as ledger:
        exists = ledger.execute("SELECT 1 FROM sqlite_master WHERE name='account_deletion_receipts'").fetchone()
        if not exists:
            raise ValueError("Deletion receipts are unavailable. Do not restore until the current deletion ledger is recovered.")
        receipts = dict(ledger.execute("SELECT subject_hash, deleted_at FROM account_deletion_receipts"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the new file atomically; a concurrent restore must not overwrite it.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(":memory:" if cipher else backup.as_uri()+"?mode=ro", uri=not bool(cipher))) as source, closing(sqlite3.connect(destination)) as target:
            if cipher:
                source.deserialize(cipher.decrypt(backup.read_bytes()))
            source.backup(target)
            target.execute("PRAGMA secure_delete=ON")
            for user_id, created in target.execute("SELECT user_id, created_at FROM users").fetchall():
                receipt = receipts.get(hashlib.sha256(user_id.encode()).hexdigest())
                if not receipt or instant(created) > instant(receipt):
                    continue
                for table in ("professor_outreach", "student_profiles", "sessions", "ai_explanation_requests"):
                    if target.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                        target.execute(f'DELETE FROM "{table}" WHERE user_id=?', (user_id,))
                target.execute("DELETE FROM users WHERE user_id=?", (user_id,))
                target.execute("UPDATE app_migrations SET details='deleted-account' WHERE migration_key='v9.9-local-owner-import' AND details=?", (user_id,))
            # Never restore sessions or pending OAuth attempts, even for survivors.
            target.execute("DELETE FROM sessions")
            if target.execute("SELECT 1 FROM sqlite_master WHERE name='oauth_login_attempts'").fetchone():
                target.execute("DELETE FROM oauth_login_attempts")
            target.execute("CREATE TABLE IF NOT EXISTS account_deletion_receipts(subject_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)")
            for subject_hash, deleted_at in receipts.items():
                target.execute("INSERT INTO account_deletion_receipts VALUES (?, ?) ON CONFLICT(subject_hash) DO UPDATE SET deleted_at=MAX(deleted_at,excluded.deleted_at)", (subject_hash, deleted_at))
            target.commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--ledger-database", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    restore(args.backup, args.ledger_database, args.destination)
    print("Sanitized restore written to the new destination; no services switched.")

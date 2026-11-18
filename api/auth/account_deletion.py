"""Account deletion; Google failures never prevent local credential removal."""
import hashlib
import sqlite3
from datetime import datetime, timezone
from contextlib import closing

import requests

import database
from api.gmail import token_store
from api.gmail.config import ConfigError, REVOKE_URL


class DeletionError(RuntimeError):
    pass


def _owned_files(user_id):
    root = token_store.token_dir().resolve()
    try:
        credential = token_store.credentials_path(user_id)
    except token_store.TokenStoreError:
        raise DeletionError("Account storage needs administrator attention. Nothing was deleted.") from None
    folder = credential.parent
    if folder.resolve().parent != root or folder.is_symlink() or folder.is_junction():
        raise DeletionError("Account storage needs administrator attention. Nothing was deleted.")
    # The legacy filename sanitizer can collide for unusual synthetic identities.
    with closing(database.connect()) as conn:
        others = [row[0] for row in conn.execute("SELECT user_id FROM users WHERE user_id != ?", (user_id,))]
    try:
        ambiguous = any(token_store.credentials_path(other).parent == folder for other in others)
    except token_store.TokenStoreError:
        # Legacy unsupported identities need operator review; do not delete
        # a potentially shared directory by assuming that they have no files.
        ambiguous = True
    if ambiguous:
        raise DeletionError("Account storage is ambiguous. Nothing was deleted; contact an administrator.")
    pending = token_store.pending_path(user_id)
    files = [credential, pending, credential.with_suffix(".tmp"), pending.with_suffix(".tmp"), folder / "state.lock"]
    if folder.exists() and any(entry not in files for entry in folder.iterdir()):
        raise DeletionError("Account storage contains unexpected files. Nothing was deleted; contact an administrator.")
    for file in files:
        if file.is_symlink() or (file.exists() and file.resolve().parent != folder.resolve()):
            raise DeletionError("Account storage needs administrator attention. Nothing was deleted.")
    return files


def delete_account(user_id):
    """Called under the account lock; all private mutation routes share that lock."""
    files = _owned_files(user_id)
    revocation = "not_connected"
    try:
        credentials = token_store.load_credentials(user_id)
        token = credentials.get("token", {})
        value = (token.get("refresh_token") or token.get("access_token")) if isinstance(token, dict) else None
        if value:
            revocation = "unconfirmed"
            try:
                response = requests.post(REVOKE_URL, data={"token": str(value)}, timeout=10)
                if response.status_code == 200:
                    revocation = "revoked"
            except requests.RequestException:
                pass
        elif files[0].exists():
            revocation = "unconfirmed"
    except (token_store.TokenStoreError, ConfigError, ValueError, TypeError):
        revocation = "unconfirmed"

    try:
        with closing(database.connect()) as conn, conn:
            from api.retention import enabled, Store
            managed = enabled()
            if managed:
                Store().attach(conn)
            conn.execute("PRAGMA secure_delete = ON")
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
                raise DeletionError("The account changed. Reload before trying again.")
            receipt = (hashlib.sha256(user_id.encode()).hexdigest(), datetime.now(timezone.utc).isoformat(timespec="microseconds"))
            from api.offsite import publish_deletion_receipt, OffsiteError
            try:
                publish_deletion_receipt(*receipt)
            except OffsiteError:
                raise DeletionError("Deletion is temporarily unavailable because its recovery receipt could not be secured. Your account remains; try again later.") from None
            # Remove files before committing row deletion. If this fails, the
            # account/session survives so the user can retry; removed files may
            # need reconnection. Never claim a complete deletion after an error.
            for file in files:
                file.unlink(missing_ok=True)
            if files[0].parent.exists():
                files[0].parent.rmdir()
            for table in ("professor_outreach", "student_profiles", "sessions", "ai_explanation_requests"):
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    conn.execute(f'DELETE FROM "{table}" WHERE user_id = ?', (user_id,))
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oauth_login_attempts'").fetchone():
                columns = {row[1] for row in conn.execute("PRAGMA table_info(oauth_login_attempts)")}
                if "owner_hash" in columns:
                    conn.execute("DELETE FROM oauth_login_attempts WHERE owner_hash = ?", (hashlib.sha256(user_id.encode()).hexdigest(),))
            # Preserve the one-time import barrier without retaining its owner.
            conn.execute("UPDATE app_migrations SET details = 'deleted-account' WHERE migration_key = ? AND details = ?",
                         (database.LOCAL_OWNER_IMPORT_MIGRATION_KEY, user_id))
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.execute("CREATE TABLE IF NOT EXISTS account_deletion_receipts (subject_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)")
            conn.execute("INSERT INTO account_deletion_receipts VALUES (?, ?) ON CONFLICT(subject_hash) DO UPDATE SET deleted_at=excluded.deleted_at", receipt)
            if managed:
                conn.execute("INSERT INTO deletion_ledger.account_deletion_receipts VALUES (?, ?) ON CONFLICT(subject_hash) DO UPDATE SET deleted_at=excluded.deleted_at", receipt)
    except (OSError, sqlite3.Error, ValueError):
        raise DeletionError("Deletion could not finish. Your account remains; some Gmail files may already be removed. Try again or contact an administrator.") from None
    from services.ai_explanation import clear_cache
    clear_cache()
    return {"deleted": True, "google_revocation": revocation}

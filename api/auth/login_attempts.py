"""Short-lived, atomically consumed OAuth attempts in the private runtime DB."""
import base64
import hashlib
import secrets
import time

import database

TTL_SECONDS = 600
MAX_PENDING = 4096


class LoginBusyError(RuntimeError):
    pass


def _ensure(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS oauth_login_attempts (
        state_hash TEXT PRIMARY KEY, verifier TEXT NOT NULL, nonce TEXT NOT NULL,
        expires_at REAL NOT NULL)""")
    connection.execute("CREATE INDEX IF NOT EXISTS oauth_login_expiry ON oauth_login_attempts(expires_at)")
    if "owner_hash" not in {row[1] for row in connection.execute("PRAGMA table_info(oauth_login_attempts)")}:
        connection.execute("ALTER TABLE oauth_login_attempts ADD COLUMN owner_hash TEXT")


def _digest(state):
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def begin(user_id=None):
    database.ensure_database_initialized()
    state, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(3))
    now = time.time()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure(connection)
        connection.execute("DELETE FROM oauth_login_attempts WHERE expires_at <= ?", (now,))
        if connection.execute("SELECT COUNT(*) FROM oauth_login_attempts").fetchone()[0] >= MAX_PENDING:
            raise LoginBusyError("Sign-in is temporarily busy.")
        connection.execute("INSERT INTO oauth_login_attempts (state_hash, verifier, nonce, expires_at, owner_hash) VALUES (?, ?, ?, ?, ?)",
                           (_digest(state), verifier, nonce, now + TTL_SECONDS, _digest(user_id) if user_id else None))
    return state, challenge(verifier), nonce


def consume(state):
    database.ensure_database_initialized()
    now = time.time()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure(connection)
        row = connection.execute("SELECT verifier, nonce, expires_at FROM oauth_login_attempts WHERE state_hash = ?",
                                 (_digest(state),)).fetchone()
        connection.execute("DELETE FROM oauth_login_attempts WHERE state_hash = ? OR expires_at <= ?", (_digest(state), now))
    return dict(row) if row is not None and row["expires_at"] > now else None

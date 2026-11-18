"""Isolated, per-user OAuth token storage for local development.

Credentials for the current single-user app live under
``data/gmail_tokens/{user_id}.json``. Files are written with restrictive
permissions, and optionally encrypted with Fernet when
``GMAIL_TOKEN_ENCRYPTION_KEY`` is set (requires the ``cryptography`` package).

The layout is keyed by user id from day one, so the later migration to real
authenticated accounts only changes which user id each request uses.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.gmail.config import ConfigError, token_dir

_BUCKET = "v1"
PENDING_TTL_SECONDS = 600

# Windows does not allow ``:`` in directory names, and user ids such as
# ``google:<sub>`` or ``dev:<email>`` are embedded in the storage path. Map any
# character outside the safe set to ``_`` so every user id round-trips to a
# valid filesystem path.
_UNSAFE_USER_RE = re.compile(r"[^A-Za-z0-9._@+-]")


class TokenStoreError(RuntimeError):
    """Raised when credentials are unreadable or unusably corrupt."""


def _user_dir(user_id: str) -> str:
    # Preserve established Google/dev filenames without allowing alternate
    # identities to collapse into those names or escape the storage root.
    prefixed = re.fullmatch(r"(?:google|dev):[A-Za-z0-9._@+-]+", user_id)
    plain = re.fullmatch(r"[A-Za-z0-9._@+-]+", user_id)
    if not prefixed and (not plain or user_id in {".", ".."} or user_id.startswith(("google_", "dev_"))):
        raise TokenStoreError("Account identity cannot safely address Gmail storage. Contact support.")
    return _UNSAFE_USER_RE.sub("_", user_id)


def _fernet():
    key = os.getenv("GMAIL_TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ConfigError(
            "GMAIL_TOKEN_ENCRYPTION_KEY is set but the cryptography package is "
            "not installed. Install it or unset the key to use permission-only "
            "local storage."
        ) from exc
    return Fernet(key.encode("utf-8"))


def _lockdown(path: Path) -> None:
    """Restrict filesystem permissions as best we can per platform."""
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows best-effort
        pass


def credentials_path(user_id: str) -> Path:
    return token_dir() / _user_dir(user_id) / f"{_BUCKET}_{_user_dir(user_id)}.json"


def pending_path(user_id: str) -> Path:
    return token_dir() / _user_dir(user_id) / "pending_state.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:  # pragma: no cover - Windows best-effort
        pass
    fernet = _fernet()
    if fernet is not None:
        ciphertext = fernet.encrypt(json.dumps(payload).encode("utf-8"))
        blob: dict[str, Any] = {"bucket": _BUCKET, "protected": "fernet", "ciphertext": ciphertext.decode("ascii")}
    else:
        blob = {**payload, "bucket": _BUCKET, "protected": "file-permission"}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(blob, indent=2, sort_keys=True), encoding="utf-8")
    _lockdown(temporary)
    temporary.replace(path)
    _lockdown(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise TokenStoreError(f"{path.name} is unreadable; reconnecting will replace it.")
    if not isinstance(blob, dict):
        raise TokenStoreError(f"{path.name} does not look like a credential file.")
    if blob.get("protected") == "fernet":
        fernet = _fernet()
        if fernet is None:
            raise TokenStoreError(
                f"{path.name} is encrypted but GMAIL_TOKEN_ENCRYPTION_KEY is not set."
            )
        try:
            plaintext = fernet.decrypt(str(blob.get("ciphertext", "")).encode("utf-8"))
        except Exception as exc:
            raise TokenStoreError(f"{path.name} could not be decrypted.") from exc
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TokenStoreError(f"{path.name} did not contain a credential object.")
        return payload
    return blob


def save_credentials(user_id: str, payload: dict[str, Any]) -> Path:
    _write_json(credentials_path(user_id), payload)
    return credentials_path(user_id)


def load_credentials(user_id: str) -> dict[str, Any]:
    payload = _read_json(credentials_path(user_id))
    if payload is None:
        return {}
    if not all(key in payload for key in ("token", "account_email", "client_id")):
        return {}
    return payload


def clear_credentials(user_id: str) -> None:
    path = credentials_path(user_id)
    if path.is_file():
        path.unlink()


def has_credentials(user_id: str) -> bool:
    return bool(load_credentials(user_id))


def save_pending_state(user_id: str, state: str) -> None:
    _write_json(
        pending_path(user_id),
        {
            "state": state,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def pop_pending_state(user_id: str) -> str:
    path = pending_path(user_id)
    # A separate OS lock serializes consumers across processes. Keep its file
    # after releasing it: deleting lock files can split callers between inodes.
    try:
        handle = (path.parent / "state.lock").open("a+b")
    except FileNotFoundError:
        return ""
    locked = False
    try:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 30
        while not locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise TokenStoreError("Gmail connection request is busy; try again.") from None
                time.sleep(0.01)
        try:
            payload = _read_json(path)
        except TokenStoreError:
            payload = None
        finally:
            path.unlink(missing_ok=True)
        if not payload or not isinstance(payload.get("state"), str):
            return ""
        try:
            created = datetime.fromisoformat(str(payload.get("created_at", "")))
            if created.tzinfo is None:
                return ""
            age = (datetime.now(timezone.utc) - created).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return ""
        return payload["state"] if 0 <= age < PENDING_TTL_SECONDS else ""
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def new_state() -> str:
    return secrets.token_urlsafe(32)

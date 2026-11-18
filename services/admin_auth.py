from __future__ import annotations

import hashlib
import hmac


def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()


def password_matches(candidate: str, *, plain: str = "", sha256_hash: str = "") -> bool:
    candidate = str(candidate)
    if sha256_hash:
        return hmac.compare_digest(hash_password(candidate), sha256_hash.strip().casefold())
    if plain:
        return hmac.compare_digest(candidate, plain)
    return True


def admin_access_decision(public_mode: bool, password_configured: bool) -> str:
    """Decide owner-tool access: 'password', 'auto_unlock', or 'fail_closed'."""
    if password_configured:
        return "password"
    return "fail_closed" if public_mode else "auto_unlock"

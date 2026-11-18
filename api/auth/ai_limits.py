"""Atomic, persistent admission limits for authenticated AI explanation requests.

These bound request volume, not dollar spend. Cached requests also count, so
abuse cannot use cache misses or multiple API workers to evade the limits.
"""
import os
import time

from fastapi import HTTPException

import database


def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def reserve_explanation(user_id: str) -> None:
    database.ensure_database_initialized()
    now = time.time()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS ai_explanation_requests (user_id TEXT NOT NULL, requested_at REAL NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS ai_explanation_requests_time ON ai_explanation_requests(requested_at)")
        connection.execute("DELETE FROM ai_explanation_requests WHERE requested_at <= ?", (now - 86400,))
        user_count = connection.execute(
            "SELECT COUNT(*) FROM ai_explanation_requests WHERE user_id = ? AND requested_at > ?",
            (user_id, now - 3600),
        ).fetchone()[0]
        total = connection.execute("SELECT COUNT(*) FROM ai_explanation_requests").fetchone()[0]
        if user_count >= _limit("AI_EXPLANATIONS_PER_USER_HOUR", 20) or total >= _limit("AI_EXPLANATIONS_PER_DAY", 200):
            raise HTTPException(status_code=429, detail="AI explanation limit reached. Use the research-fit reasons and try again later.", headers={"Retry-After": "3600"})
        connection.execute("INSERT INTO ai_explanation_requests VALUES (?, ?)", (user_id, now))

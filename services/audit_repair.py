from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database import (
    DB_PATH,
    NOT_AVAILABLE,
    _bump_data_revision,
    connect,
    initialize_database,
    migration_applied,
)
from scrapers.configurable import sanitize_research_text

MIGRATION_KEY = "v9.4-audit-repair-safe"
UCI = "University of California, Irvine"
CAL_POLY = "California Polytechnic State University, San Luis Obispo"
UC_DAVIS = "University of California, Davis"
UC_SANTA_BARBARA = "University of California, Santa Barbara"
REBUILD_UNIVERSITIES = (UCI, CAL_POLY)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
UCSB_DIRECTORY_URL = "https://www.cs.ucsb.edu/people/faculty"


def _count(connection: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = connection.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def preview_v94_repair() -> dict[str, int | bool]:
    """Summarize the one-time repair without mutating the database."""
    initialize_database()
    with connect() as connection:
        return {
            "already_applied": migration_applied(MIGRATION_KEY),
            "uci_records_to_refresh": _count(
                connection,
                "SELECT COUNT(*) FROM professors WHERE university = ?",
                (UCI,),
            ),
            "calpoly_records_to_refresh": _count(
                connection,
                "SELECT COUNT(*) FROM professors WHERE university = ?",
                (CAL_POLY,),
            ),
            "ucdavis_records_to_reaudit": _count(
                connection,
                "SELECT COUNT(*) FROM professors WHERE university = ?",
                (UC_DAVIS,),
            ),
            "ucsb_profiles_to_repair": _count(
                connection,
                "SELECT COUNT(*) FROM professors WHERE university = ? "
                "AND (trim(profile_url) = '' OR profile_url = ?)",
                (UC_SANTA_BARBARA, NOT_AVAILABLE),
            ),
            "research_rows_with_contact_text": _count(
                connection,
                "SELECT COUNT(*) FROM professors WHERE research_interests LIKE '%@%' "
                "OR research_interests GLOB '*[0-9][0-9][0-9]*[0-9][0-9][0-9]*[0-9][0-9][0-9][0-9]*'",
            ),
        }


def _backup_database() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"professors-before-v9.4-{stamp}.db"
    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def run_v94_repair(*, force: bool = False) -> dict[str, int | str | bool]:
    """Prepare audited rows for safe re-import and targeted re-auditing.

    The repair is deliberately non-destructive. It creates a timestamped SQLite
    backup, keeps all existing UCI and Cal Poly rows until a successful full
    authoritative refresh can replace and prune them, resets UC Davis audit
    results so the browser-compatible verifier can retry them, repairs missing
    UCSB profile fallbacks, and strips contact spillover from research text.
    """
    initialize_database()
    if migration_applied(MIGRATION_KEY) and not force:
        return {"already_applied": True, "backup_path": "Not created"}

    backup_path = _backup_database()
    result: dict[str, int | str | bool] = {
        "already_applied": False,
        "backup_path": str(backup_path),
        "uci_marked_for_refresh": 0,
        "calpoly_marked_for_refresh": 0,
        "ucdavis_marked_for_reaudit": 0,
        "ucdavis_websites_marked_for_recheck": 0,
        "ucsb_profiles_repaired": 0,
        "research_rows_cleaned": 0,
    }

    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for university, key in (
                (UCI, "uci_marked_for_refresh"),
                (CAL_POLY, "calpoly_marked_for_refresh"),
            ):
                cursor = connection.execute(
                    """
                    UPDATE professors
                    SET verification_status = 'Not checked',
                        verification_issues = ?,
                        verified_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE university = ?
                    """,
                    (
                        "V9.4 connector rebuilt; run a full authoritative refresh before re-auditing",
                        NOT_AVAILABLE,
                        university,
                    ),
                )
                result[key] = max(cursor.rowcount, 0)

            # UC Davis profiles were largely false negatives because the old
            # verifier did not use the browser transport required by the site.
            # Preserve all profile and website URLs, then recheck them.
            cursor = connection.execute(
                """
                UPDATE professors
                SET verification_status = 'Not checked',
                    verification_issues = 'Verifier upgraded with UC Davis browser fallback; re-run targeted verification',
                    verified_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE university = ?
                """,
                (NOT_AVAILABLE, UC_DAVIS),
            )
            result["ucdavis_marked_for_reaudit"] = max(cursor.rowcount, 0)

            cursor = connection.execute(
                """
                UPDATE professors
                SET website_status = 'Not checked',
                    website_issue = 'UC Davis profile-link verification upgraded; re-run targeted website audit',
                    website_checked_at = ?, website_final_url = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE university = ?
                  AND website_url <> ? AND trim(website_url) <> ''
                """,
                (NOT_AVAILABLE, NOT_AVAILABLE, UC_DAVIS, NOT_AVAILABLE),
            )
            result["ucdavis_websites_marked_for_recheck"] = max(cursor.rowcount, 0)

            cursor = connection.execute(
                """
                UPDATE professors
                SET profile_url = ?, data_source_url = ?,
                    verification_status = 'Not checked',
                    verification_issues = 'Official UCSB faculty-roster fallback added; re-run targeted verification',
                    verified_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE university = ? AND (trim(profile_url) = '' OR profile_url = ?)
                """,
                (
                    UCSB_DIRECTORY_URL,
                    UCSB_DIRECTORY_URL,
                    NOT_AVAILABLE,
                    UC_SANTA_BARBARA,
                    NOT_AVAILABLE,
                ),
            )
            result["ucsb_profiles_repaired"] = max(cursor.rowcount, 0)

            rows = connection.execute(
                "SELECT id, research_interests FROM professors"
            ).fetchall()
            research_updates: list[tuple[str, int]] = []
            for row in rows:
                original = str(row["research_interests"])
                if not (EMAIL_RE.search(original) or PHONE_RE.search(original)):
                    continue
                cleaned = sanitize_research_text(original)
                if cleaned != original:
                    research_updates.append((cleaned, int(row["id"])))

            if research_updates:
                connection.executemany(
                    """
                    UPDATE professors
                    SET research_interests = ?, ai_categories = '', ai_summary = '',
                        embedding_json = '', embedding_model = '', embedding_source_hash = '',
                        ai_enriched_at = ?, verification_status = 'Not checked',
                        verification_issues = 'Research text cleaned; re-run verification and missing-only AI indexing',
                        verified_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    [
                        (cleaned, NOT_AVAILABLE, NOT_AVAILABLE, professor_id)
                        for cleaned, professor_id in research_updates
                    ],
                )
            result["research_rows_cleaned"] = len(research_updates)

            _bump_data_revision(connection)

            details = json.dumps(result, sort_keys=True)
            connection.execute(
                "INSERT OR REPLACE INTO app_migrations (migration_key, applied_at, details) "
                "VALUES (?, CURRENT_TIMESTAMP, ?)",
                (MIGRATION_KEY, details),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return result

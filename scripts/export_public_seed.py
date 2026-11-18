"""Export allowlisted researcher data into a NEW database, never a runtime copy.

Only professors rows and their schema are included. Source is read-only; no
account/profile/session/outreach/query-cache/ledger/cost data is copied.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

PUBLIC_COLUMNS = (
    "id", "name", "university", "university_slug", "city", "state", "department",
    "department_category", "title", "research_interests", "email", "website_url",
    "website_status", "website_issue", "website_checked_at", "website_final_url",
    "profile_url", "data_source_url", "categories", "ai_categories", "ai_summary",
    "embedding_json", "embedding_model", "embedding_source_hash", "ai_enriched_at",
    "opportunity_level", "opportunity_signals", "opportunity_source_url", "source_type",
    "verification_status", "verification_issues", "verified_at", "last_checked_at",
    "updated_at", "school_or_college", "discipline", "field", "subfield",
)


def export(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).absolute()
    if destination.resolve() == source or destination.exists() or destination.is_symlink():
        raise ValueError("Choose a new destination. Existing files are never overwritten.")
    if any(p.is_symlink() or p.is_junction() for p in destination.parents):
        raise ValueError("Linked destination paths are not allowed.")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
        reader.execute("BEGIN")  # Consistent schema/rows; never modifies the source.
        columns = [row[1] for row in reader.execute("PRAGMA table_info(professors)")]
        if set(columns) != set(PUBLIC_COLUMNS):
            raise ValueError("Researcher schema changed; review the public-field allowlist before export.")
        schema = reader.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='professors'").fetchone()[0]
        if not re.match(r"CREATE TABLE (?:IF NOT EXISTS )?professors\s*\(", schema, re.I):
            raise ValueError("Unexpected researcher schema.")
        names = ",".join(f'"{column}"' for column in PUBLIC_COLUMNS)
        rows = reader.execute(f"SELECT {names} FROM professors ORDER BY id").fetchall()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(destination)) as writer:
            writer.execute(schema)
            writer.executemany(f"INSERT INTO professors ({names}) VALUES ({','.join('?' for _ in PUBLIC_COLUMNS)})", rows)
            writer.execute("CREATE UNIQUE INDEX uq_professors_name_university_nocase ON professors(name COLLATE NOCASE, university COLLATE NOCASE)")
            writer.commit()
            if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Seed integrity check failed.")
            tables = {row[0] for row in writer.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"professors", "sqlite_sequence"}:
                raise ValueError("Unexpected tables in public seed.")
            if writer.execute(f"SELECT {names} FROM professors ORDER BY id").fetchall() != rows:
                raise ValueError("Researcher row preservation check failed.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {"rows": len(rows), "columns": list(PUBLIC_COLUMNS), "tables": sorted(tables),
            "private_tables_copied": False, "researcher_values_preserved": True,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = Path(args.report).absolute()
    if report.exists() or report.is_symlink() or report.resolve() in {Path(args.source).resolve(), Path(args.destination).resolve()}:
        parser.error("Choose a new report path separate from both databases.")
    result = export(args.source, args.destination)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print("New public-only researcher seed created; private runtime was not copied.")

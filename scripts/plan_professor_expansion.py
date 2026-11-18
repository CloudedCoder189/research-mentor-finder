"""Read-only source comparison and in-memory insert rehearsal; never writes source DB."""
import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = ("name", "university", "university_slug", "city", "state", "department",
          "department_category", "title", "research_interests", "email", "profile_url",
          "data_source_url", "field", "subfield", "discipline", "source_type",
          "verification_status", "verification_issues")


def normalized(value):
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def validate(records):
    for record in records:
        if any(not isinstance(record.get(key), str) or not record[key].strip() for key in FIELDS):
            raise ValueError("Missing required reviewed field.")
        for key in ("profile_url", "data_source_url", "location_source_url"):
            url = urlsplit(record.get(key, ""))
            if url.scheme != "https" or not (url.hostname or "").endswith(".edu") or url.username or url.password:
                raise ValueError("Reviewed university HTTPS sources are required.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.edu", record["email"]):
            raise ValueError("A published academic email is required.")
        if record["verification_status"] != "Review":
            raise ValueError("Candidates must retain their pending formal-audit status.")


def rehearsal(source, records):
    """Backup to RAM under a read transaction, then insert only public fields."""
    validate(records)
    source = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original, closing(sqlite3.connect(":memory:")) as staged:
        original.backup(staged)
        existing = list(staged.execute("SELECT id,name,university,email,profile_url FROM professors"))
        before = list(staged.execute("SELECT * FROM professors ORDER BY id"))
        # Conservatively flag a same-name match across institutions for relocation review.
        names = {normalized(row[1]) for row in existing}
        emails = {row[3].casefold() for row in existing}
        urls = {row[4].rstrip("/").casefold() for row in existing}
        conflicts = []
        for record in records:
            name, email, url = normalized(record["name"]), record["email"].casefold(), record["profile_url"].rstrip("/").casefold()
            if name in names or email in emails or url in urls:
                conflicts.append(record["name"])
            names.add(name)
            emails.add(email)
            urls.add(url)
        if conflicts:
            raise ValueError("Potential duplicate or changed affiliation requires review: " + ", ".join(conflicts))
        private_tables = {row[0] for row in staged.execute("SELECT name FROM sqlite_master WHERE type='table'")} - {"professors", "sqlite_sequence"}
        private_before = {table: list(staged.execute('SELECT * FROM "' + table.replace('"', '""') + '"')) for table in private_tables}
        sql = f"INSERT INTO professors ({','.join(FIELDS)}) VALUES ({','.join('?' for _ in FIELDS)})"
        with staged:
            for record in records:
                staged.execute(sql, tuple(record[field] for field in FIELDS))
        ids = [row[0] for row in existing]
        after_existing = list(staged.execute("SELECT * FROM professors WHERE id <= ? ORDER BY id", (max(ids, default=0),)))
        if after_existing != before:
            raise ValueError("Existing researcher rows changed in rehearsal.")
        for table, rows in private_before.items():
            if list(staged.execute('SELECT * FROM "' + table.replace('"', '""') + '"')) != rows:
                raise ValueError("Private tables changed in rehearsal.")
        added = staged.execute("SELECT COUNT(*) FROM professors").fetchone()[0] - len(existing)
        if added != len(records):
            raise ValueError("Unexpected insert count.")
        return {"source_rows": len(existing), "candidate_rows": added,
                "rehearsal_total": len(existing) + added,
                "existing_researchers_unchanged": True, "private_tables_unchanged": True,
                "new_states": sorted({record["state"] for record in records}),
                "source_database_written": False, "rehearsal_storage": "RAM only",
                "paid_api_calls": 0,
                "limitations": ["Does not establish agreement with current hosted rows unless that database is the input.",
                                "No IDs reserved, no hosted insertion, formal audits and AI enrichment pending."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    candidate_file = Path(args.candidates)
    result = rehearsal(args.source, json.loads(candidate_file.read_text(encoding="utf-8"))["records"])
    result["candidate_sha256"] = hashlib.sha256(candidate_file.read_bytes()).hexdigest()
    Path(args.report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Read-only rehearsal: {result['candidate_rows']} inserts; {result['source_rows']} existing public rows preserved. Nothing imported.")

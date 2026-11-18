"""Insert reviewed public records only; require a fresh managed encrypted backup.

Run only against the explicitly intended database. No scraping, AI calls,
private-row exports, existing-record updates, or backup cleanup are performed.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from api.retention import Store
from scripts.plan_professor_expansion import FIELDS, normalized, rehearsal, validate


def _check_duplicates(conn, records):
    rows = conn.execute("SELECT name,email,profile_url FROM professors").fetchall()
    names = {normalized(row[0]) for row in rows}
    emails = {(row[1] or "").casefold() for row in rows}
    urls = {(row[2] or "").rstrip("/").casefold() for row in rows}
    for row in records:
        name, email, url = normalized(row["name"]), row["email"].casefold(), row["profile_url"].rstrip("/").casefold()
        if name in names or email in emails or url in urls:
            raise ValueError("Potential duplicate requires review; nothing imported.")
        names.add(name)
        emails.add(email)
        urls.add(url)


def _private_state(conn):
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'") if row[0] not in {"professors", "sqlite_sequence", "app_metadata"}]
    # Keep all values in memory; the report contains no account information.
    return {name: conn.execute('SELECT * FROM "' + name.replace('"', '""') + '" ORDER BY rowid').fetchall() for name in tables}


def import_records(records, *, expected_database):
    validate(records)
    if not records:
        raise ValueError("An empty batch is not an import.")
    supplied = Path(expected_database).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (supplied, *supplied.parents)):
        raise ValueError("Linked database targets are forbidden.")
    target = supplied.resolve(strict=True)
    if target != Path(database.DB_PATH).resolve():
        raise ValueError("Database identity does not match the explicit target.")
    rehearsal(target, records)  # Validate before creating any backup.
    store = Store()
    if not store.maintain(force_backup=True, cleanup=False):
        raise ValueError("A fresh encrypted backup is required.")
    with closing(sqlite3.connect(target, timeout=30)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _check_duplicates(conn, records)  # Recheck after acquiring the writer lock.
            before = conn.execute("SELECT * FROM professors ORDER BY id").fetchall()
            maximum = max((row[0] for row in before), default=0)
            private = _private_state(conn)
            sql = f"INSERT INTO professors ({','.join(FIELDS)}) VALUES ({','.join('?' for _ in FIELDS)})"
            for record in records:
                conn.execute(sql, tuple(record[field] for field in FIELDS))
            if conn.execute("SELECT * FROM professors WHERE id <= ? ORDER BY id", (maximum,)).fetchall() != before:
                raise ValueError("Existing researcher preservation failed.")
            if _private_state(conn) != private:
                raise ValueError("Private data preservation failed.")
            if conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] != len(before) + len(records):
                raise ValueError("Import count mismatch.")
            database._bump_data_revision(conn)
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Database integrity failed.")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    return {"inserted": len(records), "total": len(before) + len(records), "existing_researchers_unchanged": True, "private_tables_unchanged": True, "fresh_encrypted_backup": True, "backup_sessions_excluded": True, "offsite_backup_confirmed": False, "paid_api_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    content = Path(args.candidates).read_bytes()
    if hashlib.sha256(content).hexdigest() != args.expected_sha256:
        raise SystemExit("Candidate checksum mismatch; nothing imported.")
    result = import_records(json.loads(content)["records"], expected_database=args.expected_database)
    result["candidate_sha256"] = args.expected_sha256
    Path(args.report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Inserted {result['inserted']} reviewed public records; existing researchers and private tables preserved.")

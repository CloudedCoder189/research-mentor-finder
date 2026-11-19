"""Preserve scoped release-review evidence; never exposes private row contents."""
from pathlib import Path
import os
import hashlib
import json
import sqlite3
import sys
import difflib

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/release-readiness-2026-10-05"
ORIGINAL = Path(os.environ.get("RMF_ORIGINAL_ROOT", ROOT / "test-runtime" / "original")).expanduser().resolve()
FILES = ["api/main.py", "api/auth/config.py", "api/production_config.py",
         "services/categorization.py", "frontend/app/privacy/page.tsx", "tests/test_release_readiness.py"]


def fingerprints():
    database = ROOT / "test-runtime/real-acceptance-20261004.db"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        hashes = {}
        for table in tables:
            rows = connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"').fetchall()
            encoded = json.dumps(sorted(rows, key=repr), ensure_ascii=True, default=str).encode()
            hashes[table] = {"rows": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}
    original_db = ORIGINAL / "data/professors.db"
    return {"working_tables": hashes, "original_sha256": hashlib.sha256(original_db.read_bytes()).hexdigest(),
            "original_mtime_ns": original_db.stat().st_mtime_ns}


def setup():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    before = EVIDENCE / "before.json"
    if before.exists():
        raise RuntimeError("Existing preservation checkpoint must not be overwritten")
    before.write_text(json.dumps(fingerprints(), indent=2), encoding="utf-8")
    text = (ROOT / "frontend/scripts/research_recovery_acceptance.mjs").read_text(encoding="utf-8")
    text = text.replace('"research-recovery-2026-10-05"', '"release-readiness-2026-10-05"')
    text = text.replace('"research-recovery-browser-20261005.db"', '"release-readiness-browser-20261005.db"')
    text = text.replace('"research-recovery-gmail-disabled"', '"release-readiness-gmail-disabled"')
    (ROOT / "frontend/scripts/release_readiness_acceptance.mjs").write_text(text, encoding="utf-8")
    source = ROOT / "test-runtime/real-acceptance-20261004.db"
    destination = ROOT / "test-runtime/release-readiness-browser-20261005.db"
    if destination.exists():
        raise RuntimeError("Disposable destination already exists")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def finish():
    before = json.loads((EVIDENCE / "before.json").read_text(encoding="utf-8"))
    after = fingerprints()
    changed = [name for name in set(before["working_tables"]) | set(after["working_tables"])
               if before["working_tables"].get(name) != after["working_tables"].get(name)]
    original_same = all(before[key] == after[key] for key in ("original_sha256", "original_mtime_ns"))
    if not original_same or set(changed) - {"app_migrations"}:
        raise RuntimeError("Database preservation check failed")
    (EVIDENCE / "preservation.json").write_text(json.dumps({
        "passed": True, "changed_tables": changed,
        "exception": "app_migrations hash changed; initialization refreshes the phase-6 marker timestamp. No pre-start per-row metadata snapshot was captured.",
        **after}, indent=2), encoding="utf-8")
    patches = []
    for name in FILES:
        old = (ORIGINAL / name).read_text(encoding="utf-8").splitlines(True) if (ORIGINAL / name).exists() else []
        new = (ROOT / name).read_text(encoding="utf-8").splitlines(True)
        patches.extend(difflib.unified_diff(old, new, fromfile="original/" + name, tofile="working/" + name))
    (EVIDENCE / "code-changes.patch").write_text("".join(patches), encoding="utf-8")
    for file in EVIDENCE.rglob("*"):
        if file.is_file() and file.suffix in {".json", ".xml", ".txt", ".log", ".md", ".patch"}:
            text = file.read_text(encoding="utf-8")
            file.write_text(text.replace("nirmi", "&lt;user&gt;" if file.suffix == ".xml" else "<user>"), encoding="utf-8")
    print("Original database, academic rows, and all private-data tables unchanged; startup migration metadata hash changed.")


if __name__ == "__main__":
    {"setup": setup, "finish": finish}[sys.argv[1]]()

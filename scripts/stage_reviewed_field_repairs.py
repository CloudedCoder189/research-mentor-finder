"""Apply a reviewed public-field manifest only to a new, private staging copy.

No application imports, migrations, network calls, or provider calls. The
acceptance database and original database are opened read-only or fingerprinted.
The staging database is never selected by the running application.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from scripts.real_acceptance_snapshot import ROOT, SOURCE, DEST, EVIDENCE, fingerprint, professors
from services.categorization import categorize_with_keywords, categories_to_text
from services.taxonomy import infer_taxonomy
from services.university_registry import infer_department_category

MANIFEST = ROOT / "evidence/data-audit-2026-10-04/proposed-field-repairs.csv"
STAGE = ROOT / "test-runtime/reviewed-field-repairs-20261005.db"
REPORT = ROOT / "evidence/ucla-repair-2026-10-05/staged-repairs.json"
ALLOWED_FIELDS = {"name", "department", "title", "research_interests", "profile_url", "data_source_url", "website_url"}
DERIVED_FIELDS = {
    "ai_categories": "", "ai_summary": "", "embedding_json": "",
    "embedding_model": "", "embedding_source_hash": "",
    "ai_enriched_at": "Not publicly available",
    "verification_status": "Not checked",
    "verification_issues": "Reviewed academic-field correction; re-run verification audit",
    "verified_at": "Not publicly available",
}


def apply_reviewed_repairs(connection: sqlite3.Connection, repairs: list[dict]) -> list[dict]:
    """Guard every old value before making an atomic batch of updates."""
    grouped: dict[int, dict] = {}
    for repair in repairs:
        field = repair["field"]
        if field not in ALLOWED_FIELDS or repair["status"] != "proposed_not_applied":
            raise ValueError("Manifest contains an unreviewed or unsupported field")
        record_id = int(repair["id"])
        if record_id not in grouped:
            cursor = connection.execute("SELECT * FROM professors WHERE id = ?", (record_id,))
            values = cursor.fetchone()
            if values is None:
                raise ValueError(f"Missing record {record_id}")
            row = dict(zip((column[0] for column in cursor.description), values))
            grouped[record_id] = {"row": row, "changes": {}, "sources": []}
        item = grouped[record_id]
        if item["row"]["name"] != repair["name"] or item["row"][field] != repair["old"]:
            raise ValueError(f"Manifest no longer matches record {record_id}, field {field}")
        if field in item["changes"] or repair["proposed"] == repair["old"]:
            raise ValueError("Duplicate or ineffective manifest entry")
        item["changes"][field] = repair["proposed"]
        item["sources"].append(repair["source_url"])

    result = []
    with connection:
        for record_id, item in grouped.items():
            row = item["row"] | item["changes"]
            updates = item["changes"] | DERIVED_FIELDS
            if "website_url" in item["changes"]:
                updates.update(website_status="Not checked", website_issue="Website changed; run targeted link check",
                               website_checked_at="Not publicly available", website_final_url="Not publicly available")
            categories = row["categories"]
            if "research_interests" in item["changes"]:
                categories = categories_to_text(categorize_with_keywords(row["research_interests"]))
                updates["categories"] = categories
            updates["department_category"] = infer_department_category(row["department"], row["research_interests"])
            taxonomy = infer_taxonomy(university=row["university"], department=row["department"], categories=categories, ai_categories="")
            updates.update(zip(("school_or_college", "discipline", "field", "subfield"), taxonomy))
            assignments = ", ".join(f"{field} = ?" for field in updates)
            connection.execute(f"UPDATE professors SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (*updates.values(), record_id))
            result.append({"id": record_id, "name": row["name"], "fields": item["changes"], "source_urls": sorted(set(item["sources"]))})
    return result


def main() -> None:
    if STAGE.exists():
        raise SystemExit("Refusing to overwrite an existing staging database")
    baseline = json.loads((EVIDENCE / "snapshot.json").read_text(encoding="utf-8"))
    original_before = fingerprint(SOURCE)
    if original_before != baseline["source_before"]:
        raise SystemExit("Original database no longer matches the accepted baseline")
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        repairs = list(csv.DictReader(handle))
    with sqlite3.connect(DEST.as_uri() + "?mode=ro", uri=True) as source:
        before = professors(source)
        if before != baseline["professors"]:
            raise SystemExit("Acceptance professor data changed since review")
        columns = [row[1] for row in source.execute("PRAGMA table_info(professors)")]
        old_rows = dict((row[0], tuple(row)) for row in source.execute("SELECT * FROM professors ORDER BY id"))
        with sqlite3.connect(STAGE) as staged:
            source.backup(staged)
            assert professors(staged) == before
            applied = apply_reviewed_repairs(staged, repairs)
            new_rows = dict((row[0], tuple(row)) for row in staged.execute("SELECT * FROM professors ORDER BY id"))
            changed_ids = sorted(record_id for record_id in old_rows if old_rows[record_id] != new_rows[record_id])
            assert set(new_rows) == set(old_rows)
            assert changed_ids == sorted(record["id"] for record in applied)
            allowed_changes = ALLOWED_FIELDS | set(DERIVED_FIELDS) | {"categories", "department_category", "school_or_college", "discipline", "field", "subfield", "updated_at", "website_status", "website_issue", "website_checked_at", "website_final_url"}
            changed_columns = {}
            for record_id in changed_ids:
                changed_columns[str(record_id)] = [column for column, old, new in zip(columns, old_rows[record_id], new_rows[record_id]) if old != new]
                assert set(changed_columns[str(record_id)]) <= allowed_changes
            assert staged.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            after = professors(staged)
            remaining_titles = staged.execute("SELECT count(*) FROM professors WHERE title = 'Expert Directory'").fetchone()[0]
        assert professors(source) == before
    assert fingerprint(SOURCE) == original_before
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "scope": "Private staging copy only; running application still uses acceptance database",
        "staging_relative_path": str(STAGE.relative_to(ROOT)), "manifest_field_count": len(repairs),
        "before": before, "after": after, "applied": applied, "changed_columns": changed_columns,
        "remaining_expert_directory_titles": remaining_titles,
        "original_matches_accepted_fingerprint": True, "acceptance_professor_rows_unchanged": True,
        "paid_calls": 0, "reverification_performed": False, "reembedding_performed": False,
        "kai_wei_chang_rank": "Unresolved source conflict; title left unchanged",
    }, indent=2), encoding="utf-8")
    print(json.dumps({"staged_records": len(applied), "reviewed_fields": len(repairs), "missing_embeddings": after["missing_embeddings"], "remaining_bad_titles": remaining_titles}))


if __name__ == "__main__":
    main()

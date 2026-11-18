"""Stage source-reviewed UCLA corrections in a new private database; no network."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3

from bs4 import BeautifulSoup

from scripts.real_acceptance_snapshot import ROOT, SOURCE, DEST, EVIDENCE as BASELINE, fingerprint, professors
from scripts.review_ucla_sources import CAPTURES, EVIDENCE
from scripts.stage_reviewed_field_repairs import apply_reviewed_repairs
from scrapers.ucla import parse_ucla_profile_html, _profile_name_matches

PREVIOUS = ROOT / "test-runtime/reviewed-field-repairs-20261005.db"
STAGE = ROOT / "test-runtime/ucla-expanded-repairs-20261005.db"


def table_hashes(connection):
    result = {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name <> 'professors' ORDER BY name"):
        escaped = name.replace('"', '""')
        rows = connection.execute(f'SELECT * FROM "{escaped}"').fetchall()
        # Only hashes/counts may leave this function; no private row values.
        result[name] = {"rows": len(rows), "sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()}
    return result


def main():
    if STAGE.exists():
        raise SystemExit("Refusing to overwrite an existing expanded stage")
    baseline = json.loads((BASELINE / "snapshot.json").read_text(encoding="utf-8"))
    assert fingerprint(SOURCE) == baseline["source_before"]
    with sqlite3.connect(DEST.as_uri() + "?mode=ro", uri=True) as accepted:
        assert professors(accepted) == baseline["professors"]
    prior_report = json.loads((ROOT / "evidence/ucla-repair-2026-10-05/staged-repairs.json").read_text(encoding="utf-8"))
    reviews = []
    repairs = []
    with sqlite3.connect(PREVIOUS.as_uri() + "?mode=ro", uri=True) as previous:
        before = professors(previous)
        assert before == prior_report["after"]
        private_before = table_hashes(previous)
        cursor = previous.execute("SELECT * FROM professors WHERE id BETWEEN 123 AND 173 ORDER BY id")
        columns = [column[0] for column in cursor.description]
        records = [dict(zip(columns, row)) for row in cursor.fetchall() if row[columns.index("university")] == "University of California, Los Angeles"]
        # Exactly the 50 records that originally carried Expert Directory.
        with sqlite3.connect(DEST.as_uri() + "?mode=ro", uri=True) as accepted:
            target_ids = {row[0] for row in accepted.execute("SELECT id FROM professors WHERE title = 'Expert Directory'")}
        records = [row for row in records if row["id"] in target_ids]
        assert len(records) == 50
        for record in records:
            record_id = record["id"]
            metadata = json.loads((CAPTURES / f"{record_id}.json").read_text(encoding="utf-8"))
            raw = (CAPTURES / f"{record_id}.html").read_bytes()
            assert metadata["status"] == 200 and hashlib.sha256(raw).hexdigest() == metadata["sha256"]
            soup = BeautifulSoup(raw, "html.parser")
            identity = soup.select_one(".seas-profile-identity")
            name = identity.find("h1").get_text(" ", strip=True)
            assert _profile_name_matches(name, record["name"], record["profile_url"])
            titles = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-title")]
            departments = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-chip--dept")]
            assert len(titles) == 1 and departments
            details = parse_ucla_profile_html(raw.decode("utf-8", errors="replace"), metadata["response_url"], record["name"])
            assert details.title == titles[0]
            assert details.department == "; ".join(dict.fromkeys(departments))
            corroboration = []
            if record_id == 123:
                secondary = json.loads((CAPTURES / "123-secondary.json").read_text(encoding="utf-8"))
                secondary_raw = (CAPTURES / "123-secondary.html").read_bytes()
                assert secondary["status"] == 200 and hashlib.sha256(secondary_raw).hexdigest() == secondary["sha256"]
                secondary_soup = BeautifulSoup(secondary_raw, "html.parser")
                assert secondary_soup.find("h1").get_text(" ", strip=True) == "Kai-Wei Chang"
                assert "Professor, UCLA Computer Science" in secondary_soup.get_text(" ", strip=True)
                corroboration = [secondary["response_url"]]
            desired = {"title": details.title, "department": details.department}
            if name != record["name"]:
                desired["name"] = name
            if metadata["response_url"] != record["profile_url"]:
                desired.update(profile_url=metadata["response_url"], data_source_url=metadata["response_url"])
            # Accept personal links supplied by the official profile; absence of
            # a link is not evidence that a previously known website disappeared.
            if details.website_url != "Not publicly available":
                desired["website_url"] = details.website_url
            if record_id in {152, 162}:
                assert record["research_interests"].startswith("UCLA CS research areas:")
                assert details.research_interests != "Not publicly available"
                desired["research_interests"] = details.research_interests + "; " + record["research_interests"]
            sources = [metadata["response_url"]] + corroboration
            for field, proposed in desired.items():
                if record[field] != proposed:
                    repairs.append({"id": record_id, "name": record["name"], "field": field,
                                    "old": record[field], "proposed": proposed,
                                    "source_url": metadata["response_url"], "status": "proposed_not_applied"})
            reviews.append({"id": record_id, "name": name, "title": details.title,
                            "departments": departments, "source_urls": sources,
                            "sha256": metadata["sha256"], "retrieved_at_utc": metadata["retrieved_at_utc"],
                            "future_start_caution": "Starting November 1, 2027" in details.title,
                            "scope": "Appointment/departments and explicitly corrected fields; separate automated identity/link audit required"})
        with (EVIDENCE / "expanded-field-repairs.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("id", "name", "field", "old", "proposed", "source_url", "status"))
            writer.writeheader()
            writer.writerows(repairs)
        old_ids = {row[0] for row in previous.execute("SELECT id FROM professors")}
        with sqlite3.connect(STAGE) as staged:
            previous.backup(staged)
            assert professors(staged) == before
            applied = apply_reviewed_repairs(staged, repairs)
            after = professors(staged)
            assert after["rows"] == before["rows"] == 2063
            assert old_ids == {row[0] for row in staged.execute("SELECT id FROM professors")}
            assert staged.execute("SELECT count(*) FROM professors WHERE title = 'Expert Directory'").fetchone()[0] == 0
            assert staged.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert table_hashes(staged) == private_before
            # Compare complete public professor rows without exporting contact data.
            changed = []
            before_rows = previous.execute("SELECT * FROM professors ORDER BY id").fetchall()
            after_rows = staged.execute("SELECT * FROM professors ORDER BY id").fetchall()
            for old, new in zip(before_rows, after_rows):
                if old != new:
                    assert old[0] == new[0]
                    changed.append(old[0])
            assert sorted(changed) == sorted(item["id"] for item in applied)
        assert professors(previous) == before
    assert fingerprint(SOURCE) == baseline["source_before"]
    with sqlite3.connect(DEST.as_uri() + "?mode=ro", uri=True) as accepted:
        assert professors(accepted) == baseline["professors"]
    report = {"scope": "Expanded staging copy only; original, first stage and active acceptance data unchanged",
              "staging_relative_path": str(STAGE.relative_to(ROOT)), "reviewed_ucla_records": len(reviews),
              "new_field_changes": len(repairs), "new_changed_records": len(applied), "before": before, "after": after,
              "applied": applied, "source_reviews": reviews, "all_non_professor_tables_unchanged": True,
              "original_matches_baseline": True, "active_professor_rows_match_baseline": True,
              "remaining_expert_directory_titles": 0, "paid_calls": 0,
              "ai_regeneration": "Pending a new spending authorization", "verification": "Pending automated identity/link audit"}
    (EVIDENCE / "expanded-staging.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("reviewed_ucla_records", "new_field_changes", "new_changed_records", "remaining_expert_directory_titles", "after")}))


if __name__ == "__main__":
    main()

from pathlib import Path

import database
from services import audit_repair


def _record(name, university, email, *, website=database.NOT_AVAILABLE, profile="https://example.edu/person", research="Machine learning"):
    return {
        "name": name,
        "university": university,
        "department": "Computer Science",
        "title": "Professor",
        "research_interests": research,
        "email": email,
        "website_url": website,
        "profile_url": profile,
        "categories": "Machine Learning",
        "source_type": "Test",
    }


def test_v94_repair_is_backed_up_non_destructive_and_idempotent(tmp_path: Path):
    original_database_path = database.DB_PATH
    original_repair_path = audit_repair.DB_PATH
    db_path = tmp_path / "professors.db"
    database.DB_PATH = db_path
    audit_repair.DB_PATH = db_path
    try:
        database.initialize_database()
        database.upsert_professors(
            [
                _record("UCI Person", audit_repair.UCI, "uci@uci.edu"),
                _record("Cal Poly Person", audit_repair.CAL_POLY, "poly@calpoly.edu"),
                _record(
                    "Matthew Farrens",
                    audit_repair.UC_DAVIS,
                    "farrens@ucdavis.edu",
                    website="https://example.org/farrens-lab",
                    profile="https://cs.ucdavis.edu/directory/matthew-farrens",
                ),
                _record(
                    "UCSB Person",
                    audit_repair.UC_SANTA_BARBARA,
                    "ucsb@ucsb.edu",
                    profile=database.NOT_AVAILABLE,
                ),
                _record(
                    "UCSC Person",
                    "University of California, Santa Cruz",
                    "ucsc@ucsc.edu",
                    research="Machine learning and vision Email ucsc@ucsc.edu Office 101",
                ),
            ]
        )
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE professors SET ai_summary = 'Paid summary', ai_categories = 'AI',
                    embedding_json = '[0.1]', embedding_model = 'test',
                    embedding_source_hash = 'hash', ai_enriched_at = '2026-01-01'
                """
            )
            # Simulate a row imported by the older connector before startup
            # sanitization was added.
            connection.execute(
                """
                UPDATE professors
                SET research_interests = 'Machine learning and vision Email ucsc@ucsc.edu Office 101'
                WHERE name = 'UCSC Person'
                """
            )

        result = audit_repair.run_v94_repair()
        assert Path(str(result["backup_path"])).exists()
        records = {row["name"]: row for row in database.fetch_professors()}
        assert "UCI Person" in records
        assert "Cal Poly Person" in records
        assert records["Matthew Farrens"]["website_url"] == "https://example.org/farrens-lab"
        assert records["Matthew Farrens"]["website_status"] == "Not checked"
        assert records["UCSB Person"]["profile_url"] == audit_repair.UCSB_DIRECTORY_URL
        assert "@" not in records["UCSC Person"]["research_interests"]
        assert records["UCSC Person"]["embedding_json"] == ""
        assert records["Matthew Farrens"]["embedding_json"] == "[0.1]"
        assert result["uci_marked_for_refresh"] == 1
        assert result["calpoly_marked_for_refresh"] == 1

        second = audit_repair.run_v94_repair()
        assert second["already_applied"] is True
        assert second["backup_path"] == "Not created"
    finally:
        database.DB_PATH = original_database_path
        audit_repair.DB_PATH = original_repair_path

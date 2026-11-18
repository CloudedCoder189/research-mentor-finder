from pathlib import Path

import database


BASE = {
    "name": "V8 Test Person",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Assistant Professor",
    "research_interests": "Machine learning for healthcare",
    "email": "v8test@stanford.edu",
    "website_url": "https://example.org/lab",
    "profile_url": "https://profiles.stanford.edu/v8-test",
    "categories": "Machine Learning, Healthcare AI",
    "source_type": "Test",
}


def _use_db(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    return original


def test_v8_backfills_location_and_department_metadata(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.upsert_professors([BASE])
        record = database.fetch_professors()[0]
        assert record["university_slug"] == "stanford"
        assert record["city"] == "Stanford"
        assert record["state"] == "California"
        assert record["department_category"] == "Computer Science"
        assert record["data_source_url"] == BASE["profile_url"]
        assert record["last_checked_at"]
    finally:
        database.DB_PATH = original


def test_unchanged_refresh_preserves_verification_and_embedding(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.upsert_professors([BASE])
        record = database.fetch_professors()[0]
        database.update_verification_results(
            [{
                "professor_id": record["id"],
                "status": "Verified",
                "issues": "No issues found",
                "verified_at": "2026-07-23T00:00:00+00:00",
            }]
        )
        database.update_ai_enrichment(
            [{
                "id": record["id"],
                "ai_categories": "Machine Learning",
                "ai_summary": "Studies machine learning for health.",
                "embedding_json": "[1.0,0.0]",
                "embedding_model": "test",
                "embedding_source_hash": "hash",
                "ai_enriched_at": "2026-07-23T00:00:00+00:00",
            }]
        )
        database.upsert_professors([BASE])
        unchanged = database.fetch_professors()[0]
        assert unchanged["verification_status"] == "Verified"
        assert unchanged["embedding_json"] == "[1.0,0.0]"
    finally:
        database.DB_PATH = original


def test_changed_refresh_invalidates_only_changed_record(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.upsert_professors([BASE])
        record = database.fetch_professors()[0]
        database.update_verification_results(
            [{
                "professor_id": record["id"],
                "status": "Verified",
                "issues": "No issues found",
                "verified_at": "2026-07-23T00:00:00+00:00",
            }]
        )
        changed = dict(BASE)
        changed["research_interests"] = "Machine learning, healthcare, and robotics"
        database.upsert_professors([changed])
        updated = database.fetch_professors()[0]
        assert updated["verification_status"] == "Not checked"
        assert "Record changed" in updated["verification_issues"]
        assert updated["embedding_json"] == ""
    finally:
        database.DB_PATH = original


def test_query_embedding_cache_round_trip_and_hit_count(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.save_query_embedding("AI for health", "model-a", [1.0, 2.0])
        assert database.get_cached_query_embedding(" ai  for   health ", "model-a") == [1.0, 2.0]
        assert database.query_cache_count() == 1
        with database.connect() as connection:
            row = connection.execute(
                "SELECT hit_count FROM query_embedding_cache"
            ).fetchone()
        assert int(row["hit_count"]) == 1
    finally:
        database.DB_PATH = original


def test_daily_usage_limit_is_atomic_and_resets_by_name(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        first = database.consume_daily_usage("search", 2)
        second = database.consume_daily_usage("search", 2)
        third = database.consume_daily_usage("search", 2)
        other = database.consume_daily_usage("other", 1)
        assert first["allowed"] is True
        assert second["allowed"] is True
        assert third["allowed"] is False
        assert third["used"] == 2
        assert other["allowed"] is True
    finally:
        database.DB_PATH = original


def test_zero_daily_limit_means_unlimited(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        result = database.consume_daily_usage("search", 0)
        assert result["allowed"] is True
        assert result["remaining"] == -1
    finally:
        database.DB_PATH = original


def test_v8_migrates_a_v7_style_database_before_creating_new_indexes(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        with database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE professors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    university TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT 'Not publicly available',
                    title TEXT NOT NULL DEFAULT 'Not publicly available',
                    research_interests TEXT NOT NULL DEFAULT 'Not publicly available',
                    email TEXT NOT NULL UNIQUE,
                    website_url TEXT NOT NULL DEFAULT 'Not publicly available',
                    profile_url TEXT NOT NULL DEFAULT 'Not publicly available',
                    categories TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'University website',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        database.initialize_database()
        with database.connect() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(professors)")}
            indexes = {row["name"] for row in connection.execute("PRAGMA index_list(professors)")}
        assert {"state", "city", "department_category", "last_checked_at"}.issubset(columns)
        assert "idx_professors_location" in indexes
    finally:
        database.DB_PATH = original


def test_v9_website_link_status_round_trip_and_reset_on_url_change(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.upsert_professors([BASE])
        record = database.fetch_professors()[0]
        assert record["website_status"] == "Not checked"
        database.update_website_link_results(
            [{
                "professor_id": record["id"],
                "status": "Verified",
                "issue": "Website matched professor name",
                "checked_at": "2026-07-23T12:00:00+00:00",
                "final_url": BASE["website_url"],
            }]
        )
        verified = database.fetch_professors()[0]
        assert verified["website_status"] == "Verified"
        assert database.website_link_counts() == {"Verified": 1}

        database.upsert_professors([BASE])
        unchanged = database.fetch_professors()[0]
        assert unchanged["website_status"] == "Verified"

        changed = dict(BASE)
        changed["website_url"] = "https://example.org/new-lab"
        database.upsert_professors([changed])
        reset = database.fetch_professors()[0]
        assert reset["website_status"] == "Not checked"
        assert "Website changed" in reset["website_issue"]
    finally:
        database.DB_PATH = original


def test_v9_migration_adds_website_link_columns(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        with database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE professors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    university TEXT NOT NULL,
                    department TEXT NOT NULL DEFAULT 'Not publicly available',
                    title TEXT NOT NULL DEFAULT 'Not publicly available',
                    research_interests TEXT NOT NULL DEFAULT 'Not publicly available',
                    email TEXT NOT NULL UNIQUE,
                    website_url TEXT NOT NULL DEFAULT 'Not publicly available',
                    profile_url TEXT NOT NULL DEFAULT 'Not publicly available',
                    categories TEXT NOT NULL DEFAULT '',
                    source_type TEXT NOT NULL DEFAULT 'University website',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        database.initialize_database()
        with database.connect() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(professors)")}
        assert {
            "website_status",
            "website_issue",
            "website_checked_at",
            "website_final_url",
        }.issubset(columns)
    finally:
        database.DB_PATH = original


def test_website_only_refresh_preserves_ai_index_but_resets_link_and_record_audits(tmp_path: Path):
    original = _use_db(tmp_path)
    try:
        database.initialize_database()
        database.upsert_professors([BASE])
        record = database.fetch_professors()[0]
        database.update_ai_enrichment([
            {
                "id": record["id"],
                "ai_categories": "Machine Learning",
                "ai_summary": "Studies machine learning for health.",
                "embedding_json": "[1.0,0.0]",
                "embedding_model": "test",
                "embedding_source_hash": "hash",
                "ai_enriched_at": "2026-07-23T00:00:00+00:00",
            }
        ])
        database.update_verification_results([
            {
                "professor_id": record["id"],
                "status": "Verified",
                "issues": "No issues found",
                "verified_at": "2026-07-23T00:00:00+00:00",
            }
        ])
        database.update_website_link_results([
            {
                "professor_id": record["id"],
                "status": "Verified",
                "issue": "Website matched professor name",
                "checked_at": "2026-07-23T12:00:00+00:00",
                "final_url": BASE["website_url"],
            }
        ])

        changed = dict(BASE)
        changed["website_url"] = "https://example.org/new-lab"
        database.upsert_professors([changed])
        updated = database.fetch_professors()[0]

        assert updated["embedding_json"] == "[1.0,0.0]"
        assert updated["ai_summary"] == "Studies machine learning for health."
        assert updated["verification_status"] == "Not checked"
        assert updated["website_status"] == "Not checked"
    finally:
        database.DB_PATH = original

import json
from pathlib import Path

import database
from services.ai_enrichment import cosine_similarity, parse_embedding, source_hash
from services.search import rank_professors


def test_cosine_similarity_and_embedding_parser() -> None:
    assert parse_embedding("[1,0,0]") == [1.0, 0.0, 0.0]
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_hybrid_search_uses_stored_semantic_embedding() -> None:
    records = [
        {
            "name": "Semantic Match",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Decision systems for environmental resilience",
            "categories": "Climate & Sustainability",
            "ai_summary": "Uses computational methods to improve environmental resilience.",
            "embedding_json": json.dumps([1.0, 0.0]),
        },
        {
            "name": "Different Meaning",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Machine learning compilers",
            "categories": "Machine Learning, Systems",
            "embedding_json": json.dumps([0.0, 1.0]),
        },
    ]

    for record in records:
        record["embedding_source_hash"] = source_hash(record)

    ranked = rank_professors(
        records,
        "technology for climate resilience",
        limit=2,
        query_embedding=[1.0, 0.0],
    )
    assert ranked[0]["name"] == "Semantic Match"
    assert ranked[0]["search_mode"] == "AI semantic + keyword"
    assert float(ranked[0]["semantic_score"]) > 90


def test_database_ai_index_is_preserved_until_source_changes(tmp_path: Path) -> None:
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        record = {
            "name": "AI Indexed Person",
            "university": "Example University",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Machine learning",
            "email": "person@example.edu",
            "website_url": "https://example.edu/lab",
            "profile_url": "https://example.edu/profile",
            "categories": "Machine Learning",
            "source_type": "Test",
        }
        database.upsert_professors([record])
        professor = database.fetch_professors()[0]
        database.update_ai_enrichment(
            [
                {
                    "id": professor["id"],
                    "ai_categories": "Artificial Intelligence, Machine Learning",
                    "ai_summary": "Studies machine learning.",
                    "embedding_json": "[1.0,0.0]",
                    "embedding_model": "test-model",
                    "embedding_source_hash": "hash",
                    "ai_enriched_at": "2026-07-22T00:00:00+00:00",
                }
            ]
        )

        database.upsert_professors([record])
        unchanged = database.fetch_professors()[0]
        assert unchanged["embedding_json"] == "[1.0,0.0]"

        changed = dict(record)
        changed["research_interests"] = "Machine learning and robotics"
        database.upsert_professors([changed])
        refreshed = database.fetch_professors()[0]
        assert refreshed["embedding_json"] == ""
        assert refreshed["ai_summary"] == ""
    finally:
        database.DB_PATH = original_path


def test_openai_enrichment_can_be_batched_with_mock_client(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace
    import services.ai_enrichment as ai

    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"

    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "records": [
                            {
                                "id": 1,
                                "categories": ["Machine Learning", "Healthcare AI"],
                                "summary": "Applies machine learning to health data.",
                            }
                        ]
                    }
                )
            )

    class FakeEmbeddings:
        def create(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[1.0, float(index)])
                    for index, _ in enumerate(kwargs["input"])
                ]
            )

    fake_client = SimpleNamespace(responses=FakeResponses(), embeddings=FakeEmbeddings())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai, "_new_client", lambda: fake_client)

    try:
        database.initialize_database()
        database.upsert_professors(
            [
                {
                    "name": "Health ML Person",
                    "university": "Example University",
                    "department": "Computer Science",
                    "title": "Professor",
                    "research_interests": "Machine learning for health data",
                    "email": "health@example.edu",
                    "website_url": "https://example.edu/lab",
                    "profile_url": "https://example.edu/profile",
                    "categories": "Machine Learning, Healthcare AI",
                    "source_type": "Test",
                }
            ]
        )
        records = database.fetch_professors()
        assert records[0]["id"] == 1
        result = ai.enrich_records_with_openai(records)
        saved = database.fetch_professors()[0]
        assert result["saved"] == 1
        assert saved["ai_summary"] == "Applies machine learning to health data."
        assert saved["embedding_json"]
    finally:
        database.DB_PATH = original_path


def test_ai_indexing_checkpoints_completed_embedding_batches(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace
    import pytest
    import services.ai_enrichment as ai

    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"

    class FakeResponses:
        def create(self, **kwargs):
            payload = json.loads(kwargs["input"].split("Records: ", 1)[1])
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "records": [
                            {
                                "id": item["id"],
                                "categories": ["Machine Learning"],
                                "summary": "Studies machine learning.",
                            }
                            for item in payload
                        ]
                    }
                )
            )

    class FailingEmbeddings:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("temporary embedding failure")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[1.0, float(index)])
                    for index, _ in enumerate(kwargs["input"])
                ]
            )

    fake_client = SimpleNamespace(responses=FakeResponses(), embeddings=FailingEmbeddings())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ai, "_new_client", lambda: fake_client)

    try:
        database.initialize_database()
        database.upsert_professors(
            [
                {
                    "name": f"Professor {index}",
                    "university": "Example University",
                    "department": "Computer Science",
                    "title": "Professor",
                    "research_interests": f"Machine learning topic {index}",
                    "email": f"professor{index}@example.edu",
                    "website_url": f"https://example.edu/lab/{index}",
                    "profile_url": f"https://example.edu/profile/{index}",
                    "categories": "Machine Learning",
                    "source_type": "Test",
                }
                for index in range(20)
            ]
        )

        with pytest.raises(ai.AIIndexingError) as error:
            ai.enrich_records_with_openai(database.fetch_professors())

        assert error.value.saved == 16
        indexed = [row for row in database.fetch_professors() if row["embedding_json"]]
        assert len(indexed) == 16
    finally:
        database.DB_PATH = original_path

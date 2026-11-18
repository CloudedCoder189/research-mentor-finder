from pathlib import Path
from types import SimpleNamespace

import database
import services.ai_enrichment as ai


def test_query_embedding_uses_persistent_cache(monkeypatch, tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"

    class FakeEmbeddings:
        calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.2, 0.8])])

    embeddings = FakeEmbeddings()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: SimpleNamespace(embeddings=embeddings),
    )
    try:
        first, first_source = ai.query_embedding_with_source("robot learning")
        second, second_source = ai.query_embedding_with_source(
            " robot   learning ", allow_api=False
        )
        assert first == second == (0.2, 0.8)
        assert first_source == "OpenAI"
        assert second_source == "persistent cache"
        assert embeddings.calls == 1
    finally:
        database.DB_PATH = original


def test_query_embedding_cache_only_mode_raises_when_missing(monkeypatch, tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    try:
        try:
            ai.query_embedding_with_source("never cached", allow_api=False)
        except RuntimeError as exc:
            assert "No cached" in str(exc)
        else:
            raise AssertionError("Expected a cache-miss RuntimeError")
    finally:
        database.DB_PATH = original

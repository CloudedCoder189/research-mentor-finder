"""Public-content caching must preserve matching and reflect record edits."""
from services.search import record_concepts, score_professor


def test_updated_public_source_does_not_reuse_previous_record_topics():
    record = {"id": 1, "research_interests": "robotics"}
    assert "Robotics" in record_concepts(record)
    record["research_interests"] = "quantum computing"
    assert "Robotics" not in record_concepts(record)
    assert "Quantum Computing" in record_concepts(record)
    assert score_professor(record, "quantum computing")[0] >= 95


def test_callers_cannot_mutate_cached_categories():
    record = {"research_interests": "robotics"}
    original = record_concepts(record)
    original.clear()
    assert "Robotics" in record_concepts(record)


def test_private_fields_cannot_change_public_content_cache_key():
    from services.search import _record_concepts_cached, _record_search_text
    _record_concepts_cached.cache_clear()
    _record_search_text.cache_clear()
    record = {"research_interests": "robotics", "notes": "Synthetic private note"}
    expected = score_professor(record, "robotics")
    before = _record_concepts_cached.cache_info()
    record["notes"] = "Different synthetic private note"
    assert score_professor(record, "robotics") == expected
    assert _record_concepts_cached.cache_info().hits == before.hits + 1
    assert _record_concepts_cached.cache_info().maxsize == 4096

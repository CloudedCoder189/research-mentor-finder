from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from database import (
    get_cached_query_embedding,
    save_query_embedding,
    update_ai_enrichment,
)
from services.categorization import CATEGORY_KEYWORDS

ProgressCallback = Callable[[str], None]


class AIIndexingError(RuntimeError):
    """Raised after preserving any completed AI-index batches."""

    def __init__(self, message: str, *, saved: int, attempted: int) -> None:
        super().__init__(message)
        self.saved = saved
        self.attempted = attempted


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TEXT_MODEL = "gpt-5-mini"


def openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def embedding_model_name() -> str:
    return os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()


def text_model_name() -> str:
    return os.getenv("OPENAI_TEXT_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_TEXT_MODEL)).strip()


def build_embedding_text(record: dict[str, Any]) -> str:
    """Build the academic text that represents one professor for semantic search."""

    parts = [
        f"Department: {record.get('department', '')}",
        f"Title: {record.get('title', '')}",
        f"Published research interests: {record.get('research_interests', '')}",
        f"Rule-based topics: {record.get('categories', '')}",
        f"AI topics: {record.get('ai_categories', '')}",
        f"Research summary: {record.get('ai_summary', '')}",
    ]
    return "\n".join(part.strip() for part in parts if str(part).strip())[:12000]


def source_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(build_embedding_text(record).encode("utf-8")).hexdigest()


def parse_embedding(value: Any) -> list[float] | None:
    if isinstance(value, list):
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError):
            return None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [float(item) for item in parsed]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return None


def cosine_similarity(first: Sequence[float], second: Sequence[float]) -> float:
    if not first or not second or len(first) != len(second):
        return 0.0
    dot = sum(a * b for a, b in zip(first, second))
    norm_first = math.sqrt(sum(value * value for value in first))
    norm_second = math.sqrt(sum(value * value for value in second))
    if norm_first == 0 or norm_second == 0:
        return 0.0
    return dot / (norm_first * norm_second)


def _extract_json(text: str) -> Any:
    cleaned = str(text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [index for index in (cleaned.find("{"), cleaned.find("[")) if index >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def _fallback_summary(record: dict[str, Any]) -> str:
    interests = " ".join(str(record.get("research_interests", "")).split())
    if not interests or interests == "Not publicly available":
        return "Research details were not sufficiently described on the indexed academic page."
    if len(interests) <= 260:
        return interests
    return interests[:257].rstrip(" ,;:") + "..."


def _local_topics(record: dict[str, Any]) -> list[str]:
    values = [
        value.strip()
        for value in str(record.get("categories", "")).split(",")
        if value.strip()
    ]
    return values[:8]


def _new_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        max_retries=2,
        timeout=45.0,
    )


def source_supported_topics(categories: list[str], record: dict[str, Any]) -> list[str]:
    """Reject high-risk topic claims without evidence in the supplied source."""
    text = " ".join(str(record.get(key, "")) for key in ("department", "title", "research_interests"))
    ai = bool(re.search(r"\b(?:AI|artificial intelligence|machine learning|deep learning|reinforcement learning|neural networks?|large language models?|LLMs?)\b", text, re.I))
    patterns = {
        "Machine Learning": r"\b(?:machine learning|statistical learning|deep learning|reinforcement learning|neural networks?)\b",
        "Reinforcement Learning": r"\breinforcement learning\b",
        "Large Language Models": r"\b(?:large language models?|LLMs?)\b",
        "Computational Biology": r"\b(?:biology|biological|genomics?|genes?|genetics?|proteins?|bioinformatics|cells?)\b",
    }
    supported = []
    for category in categories:
        if category in patterns and not re.search(patterns[category], text, re.I):
            continue
        if category in {"Artificial Intelligence", "Human-Centered AI", "Healthcare AI"} and not ai:
            continue
        if category == "Healthcare AI" and not re.search(r"\b(?:health|healthcare|medical|biomedical|clinical|medicine)\b", text, re.I):
            continue
        if category == "Human-Centered AI" and not re.search(r"\b(?:human|humans|people|interaction|user|users)\b", text, re.I):
            continue
        supported.append(category)
    return supported


def _enrich_text_batch(client: Any, records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    allowed = list(CATEGORY_KEYWORDS)
    payload = [
        {
            "id": int(record["id"]),
            "department": str(record.get("department", "")),
            "title": str(record.get("title", "")),
            "research_interests": str(record.get("research_interests", "")),
            "current_topics": _local_topics(record),
        }
        for record in records
    ]
    response = client.responses.create(
        model=text_model_name(),
        store=False,
        input=(
            "You standardize public academic research descriptions for a professor search tool. "
            "Use only the supplied information. Do not infer availability, recruiting, or willingness "
            "to work with students. Return valid JSON only in this shape: "
            '{"records":[{"id":1,"categories":["Machine Learning"],'
            '"summary":"One factual sentence."}]}. '
            "Choose at most eight categories per record, only from this allowed list. Return an empty categories list when no category fits. Do not force physical engineering or materials research into computing or biology categories. Do not label work as AI or machine learning unless supported by the supplied description: "
            f"{json.dumps(allowed)}. Summaries must be factual, plain language, no more than 35 words. "
            f"Records: {json.dumps(payload, ensure_ascii=False)}"
        ),
    )
    parsed = _extract_json(response.output_text)
    items = parsed.get("records", []) if isinstance(parsed, dict) else parsed
    allowed_set = set(allowed)
    source_records = {int(record["id"]): record for record in records}
    results: dict[int, dict[str, Any]] = {}
    if not isinstance(items, list):
        return results
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            professor_id = int(item.get("id", 0))
        except (TypeError, ValueError):
            continue
        if professor_id not in source_records:
            continue
        categories = [
            str(category).strip()
            for category in item.get("categories", [])
            if str(category).strip() in allowed_set
        ]
        summary = " ".join(str(item.get("summary", "")).split())[:500]
        results[professor_id] = {
            "categories": source_supported_topics(list(dict.fromkeys(categories))[:8], source_records[professor_id]),
            "summary": summary,
        }
    return results


def _embedding_batch(
    client: Any,
    texts: list[str],
) -> list[list[float]]:
    """Create one ordered embedding batch. The caller checkpoints each batch."""

    response = client.embeddings.create(model=embedding_model_name(), input=texts)
    ordered = sorted(response.data, key=lambda item: int(item.index))
    vectors = [list(map(float, item.embedding)) for item in ordered]
    if len(vectors) != len(texts):
        raise RuntimeError("OpenAI returned an unexpected number of embeddings")
    return vectors


def enrich_records_with_openai(
    records: Iterable[dict[str, Any]],
    *,
    generate_topics_and_summaries: bool = True,
    only_missing: bool = True,
    max_records: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Create cached AI metadata and embeddings for saved professor records.

    The function performs the expensive work only from the admin interface. Public
    searches use the stored vectors and make at most one query-embedding request.
    """

    if not openai_available():
        raise RuntimeError("OPENAI_API_KEY is not configured in .env or deployment secrets")

    candidates = [
        dict(record)
        for record in records
        if str(record.get("source_type", "")) != "Demo record"
    ]
    if only_missing:
        candidates = [record for record in candidates if not str(record.get("embedding_json", "")).strip()]
    if max_records is not None:
        candidates = candidates[:max_records]
    if not candidates:
        return {
            "attempted": 0,
            "saved": 0,
            "text_enriched": 0,
            "embedded": 0,
            "text_errors": [],
        }

    def update(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    client = _new_client()
    enrichment: dict[int, dict[str, Any]] = {}
    text_errors: list[str] = []

    if generate_topics_and_summaries:
        chunk_size = 8
        for start in range(0, len(candidates), chunk_size):
            chunk = candidates[start : start + chunk_size]
            update(
                f"Generating topic labels and summaries for records "
                f"{start + 1}-{min(start + chunk_size, len(candidates))} of {len(candidates)}..."
            )
            try:
                enrichment.update(_enrich_text_batch(client, chunk))
            except Exception as exc:  # Embedding generation can still continue.
                text_errors.append(str(exc))

    prepared: list[dict[str, Any]] = []
    for record in candidates:
        professor_id = int(record["id"])
        ai_item = enrichment.get(professor_id, {})
        if "categories" in ai_item:
            categories = ai_item["categories"]
        else:
            categories = [
                value.strip()
                for value in str(record.get("ai_categories", "")).split(",")
                if value.strip()
            ] or _local_topics(record)
        summary = str(ai_item.get("summary") or record.get("ai_summary") or _fallback_summary(record)).strip()
        enriched_record = dict(record)
        enriched_record["ai_categories"] = ", ".join(categories)
        enriched_record["ai_summary"] = summary
        prepared.append(enriched_record)

    total = len(prepared)
    # Keep requests small enough for ordinary local connections and save each
    # successful group immediately. A later API/network error can no longer
    # discard all earlier work from a large indexing run.
    embedding_batch_size = 16
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    saved = 0
    embedded = 0

    for start in range(0, total, embedding_batch_size):
        batch_records = prepared[start : start + embedding_batch_size]
        batch_end = min(start + embedding_batch_size, total)
        update(f"Creating and saving embeddings for records {start + 1}-{batch_end} of {total}...")
        batch_texts = [build_embedding_text(record) for record in batch_records]
        try:
            vectors = _embedding_batch(client, batch_texts)
        except Exception as exc:
            raise AIIndexingError(
                f"AI indexing stopped after safely saving {saved} of {total} record(s). "
                "Run the same missing-only job again after checking the terminal error; "
                "already saved records will be skipped. "
                f"Cause: {type(exc).__name__}: {exc}",
                saved=saved,
                attempted=total,
            ) from exc

        database_rows = []
        for record, vector in zip(batch_records, vectors):
            enriched_record = dict(record)
            enriched_record["embedding_json"] = json.dumps(vector, separators=(",", ":"))
            enriched_record["embedding_model"] = embedding_model_name()
            enriched_record["embedding_source_hash"] = source_hash(enriched_record)
            enriched_record["ai_enriched_at"] = timestamp
            database_rows.append(enriched_record)

        saved_now = update_ai_enrichment(database_rows)
        saved += saved_now
        embedded += len(vectors)

    update("AI search index is ready.")
    return {
        "attempted": len(candidates),
        "saved": saved,
        "text_enriched": len(enrichment),
        "embedded": embedded,
        "embedding_model": embedding_model_name(),
        "text_model": text_model_name(),
        "text_errors": text_errors,
    }


def query_embedding_with_source(
    query: str,
    model: str | None = None,
    *,
    allow_api: bool = True,
) -> tuple[tuple[float, ...], str]:
    """Return a query embedding and whether it came from SQLite or OpenAI."""

    selected_model = model or embedding_model_name()
    normalized = " ".join(str(query).split())
    if not normalized:
        return (), "empty"

    cached = get_cached_query_embedding(normalized, selected_model)
    if cached:
        return tuple(cached), "persistent cache"

    if not allow_api:
        raise RuntimeError("No cached semantic-search vector is available for this query")
    if not openai_available():
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = _new_client()
    response = client.embeddings.create(
        model=selected_model,
        input=[normalized],
    )
    vector = tuple(float(value) for value in response.data[0].embedding)
    save_query_embedding(normalized, selected_model, vector)
    return vector, "OpenAI"


def query_embedding(query: str, model: str | None = None) -> tuple[float, ...]:
    vector, _source = query_embedding_with_source(query, model)
    return vector

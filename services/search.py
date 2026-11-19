from __future__ import annotations

import re
from functools import lru_cache
from collections.abc import Iterable, Sequence

from services.ai_enrichment import cosine_similarity, parse_embedding, source_hash
from services.categorization import AI_SUBFIELDS, CATEGORY_KEYWORDS, categorize_with_keywords
from services.topic_matching import normalize, contains_term

STOP_WORDS = {
    "a", "an", "and", "are", "at", "for", "from", "in", "into", "is", "near",
    "of", "on", "or", "professor", "professors", "research", "researching", "the",
    "to", "who", "with", "find", "me", "people", "person", "california", "related",
    "area", "areas", "topic", "topics", "work", "working",
}

QUERY_ALIASES: dict[str, str] = {
    "quantum computing": "Quantum Computing",
    "quantum computation": "Quantum Computing",
    "climate and the environment": "Climate & Sustainability",
    "astronomy and astrophysics": "Astronomy & Astrophysics",
    "astronomy": "Astronomy & Astrophysics",
    "astrophysics": "Astronomy & Astrophysics",
    "cs": "Computer Science",
    "computer science": "Computer Science",
    "computing": "Computer Science",
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "rl": "Reinforcement Learning",
    "reinforcement learning": "Reinforcement Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "language models": "Large Language Models",
    "language model": "Large Language Models",
    "llm": "Large Language Models",
    "llms": "Large Language Models",
    "generative ai": "Generative AI",
    "genai": "Generative AI",
    "cv": "Computer Vision",
    "computer vision": "Computer Vision",
    "robotics": "Robotics",
    "robots": "Robotics",
    "hci": "Human-Computer Interaction",
    "human computer interaction": "Human-Computer Interaction",
    "human-computer interaction": "Human-Computer Interaction",
    "cybersecurity": "Security & Privacy",
    "security": "Security & Privacy",
    "privacy": "Security & Privacy",
    "data science": "Data Science",
    "systems": "Systems",
    "theory": "Theory",
    "graphics": "Graphics",
    "climate": "Climate & Sustainability",
    "climate change": "Climate & Sustainability",
    "sustainability": "Climate & Sustainability",
    "healthcare": "Healthcare AI",
    "medicine": "Healthcare AI",
    "computational biology": "Computational Biology",
    "cognitive science": "Cognitive Science",
    "speech": "Speech",
    "information retrieval": "Information Retrieval",
    "ai safety": "AI Safety",
    "responsible ai": "AI Safety",
}

RELATED: dict[str, dict[str, float]] = {
    "Computer Science": {
        "Artificial Intelligence": 0.88,
        "Machine Learning": 0.88,
        "Natural Language Processing": 0.86,
        "Computer Vision": 0.86,
        "Robotics": 0.86,
        "Systems": 0.86,
        "Theory": 0.86,
        "Security & Privacy": 0.86,
        "Data Science": 0.86,
        "Graphics": 0.86,
        "Human-Computer Interaction": 0.86,
        "Computational Biology": 0.82,
    },
    "Artificial Intelligence": {category: 0.86 for category in AI_SUBFIELDS},
    "Machine Learning": {
        "Deep Learning": 0.94,
        "Reinforcement Learning": 0.90,
        "Probabilistic Modeling": 0.82,
        "Computer Vision": 0.72,
        "Natural Language Processing": 0.72,
        "Large Language Models": 0.78,
        "Generative AI": 0.78,
        "Robotics": 0.66,
    },
    "Deep Learning": {"Machine Learning": 0.82, "Computer Vision": 0.70, "Large Language Models": 0.70},
    "Reinforcement Learning": {"Machine Learning": 0.82, "Robotics": 0.72, "Autonomous Systems": 0.66},
    "Natural Language Processing": {"Large Language Models": 0.90, "Speech": 0.68, "Information Retrieval": 0.65},
    "Large Language Models": {"Natural Language Processing": 0.90, "Generative AI": 0.82, "Machine Learning": 0.62},
    "Computer Vision": {"Deep Learning": 0.68, "Machine Learning": 0.58, "Graphics": 0.48},
    "Robotics": {"Autonomous Systems": 0.86, "Reinforcement Learning": 0.72, "Machine Learning": 0.55},
    "AI Safety": {"Security & Privacy": 0.64, "Human-Centered AI": 0.58, "Artificial Intelligence": 0.60},
    "Climate & Sustainability": {"Data Science": 0.42, "Machine Learning": 0.35},
    "Healthcare AI": {"Computational Biology": 0.58, "Machine Learning": 0.42, "Data Science": 0.38},
}


def tokenize(text: str) -> list[str]:
    return [
        token for token in normalize(text).split()
        if len(token) > 1 and token not in STOP_WORDS
    ]


def query_concepts(query: str) -> list[str]:
    normalized = normalize(query)
    concepts: list[str] = []

    # Consume specific phrases before shorter aliases inside them.
    remaining = normalized
    for alias, category in sorted(QUERY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        alias_normalized = normalize(alias)
        if alias == "computing" and remaining.strip() != "computing":
            continue
        pattern = rf"\b{re.escape(alias_normalized)}\b"
        if re.search(pattern, remaining):
            concepts.append(category)
            remaining = re.sub(pattern, " ", remaining)

    for category in categorize_with_keywords(remaining):
        if category != "Other Computing Research":
            concepts.append(category)

    concepts = list(dict.fromkeys(concepts))
    explicit_ai = bool(re.search(r"\b(?:ai|artificial intelligence)\b", normalized))
    explicit_ml = bool(re.search(r"\b(?:ml|machine learning)\b", normalized))
    if not explicit_ai and any(item in AI_SUBFIELDS - {"Artificial Intelligence"} for item in concepts):
        concepts = [item for item in concepts if item != "Artificial Intelligence"]
    if not explicit_ml and any(item in {"Deep Learning", "Reinforcement Learning"} for item in concepts):
        concepts = [item for item in concepts if item != "Machine Learning"]
    return concepts


_CONCEPT_FIELDS = ("department", "research_interests", "categories", "ai_categories", "ai_summary", "title")
_SEARCH_FIELDS = ("department", "research_interests", "categories", "title")


@lru_cache(maxsize=4096)
def _record_concepts_cached(values: tuple[str, ...]) -> tuple[str, ...]:
    # Cache only public researcher content. Edits change the content key; no
    # student profile, query, account ID or private note enters this cache.
    record = dict(zip(_CONCEPT_FIELDS, values))
    categories = [
        value.strip()
        for field in ("categories", "ai_categories")
        for value in str(record.get(field, "")).split(",")
        if value.strip()
    ]
    source_text = " ".join(
        [
            str(record.get("department", "")),
            str(record.get("research_interests", "")),
            str(record.get("categories", "")),
            str(record.get("ai_categories", "")),
            str(record.get("ai_summary", "")),
            str(record.get("title", "")),
        ]
    )
    inferred = categorize_with_keywords(source_text)
    normalized_source = normalize(source_text)
    for alias, category in QUERY_ALIASES.items():
        if contains_term(normalized_source, normalize(alias)):
            categories.append(category)
    if "computer science" in normalize(source_text) or "computing" in normalize(source_text):
        categories.append("Computer Science")
    return tuple(
        dict.fromkeys(
            categories + [item for item in inferred if item != "Other Computing Research"]
        )
    )



def record_concepts(record: dict[str, str]) -> list[str]:
    # Return a fresh list so callers cannot modify the shared cached value.
    return list(_record_concepts_cached(tuple(str(record.get(field, "")) for field in _CONCEPT_FIELDS)))


@lru_cache(maxsize=4096)
def _record_search_text(values: tuple[str, ...]) -> tuple[str, frozenset[str]]:
    searchable = normalize(" ".join(values))
    return searchable, frozenset(tokenize(searchable))


def _concept_match(query_concept: str, available: set[str]) -> tuple[float, str | None]:
    if query_concept in available:
        return 1.0, query_concept

    best_score = 0.0
    best_category: str | None = None
    for category, score in RELATED.get(query_concept, {}).items():
        if category in available and score > best_score:
            best_score = score
            best_category = category

    return best_score, best_category


def score_professor(record: dict[str, str], query: str) -> tuple[float, list[str]]:
    return _score_prepared(record, normalize(query), query_concepts(query), set(tokenize(query)))


def _score_prepared(record: dict[str, str], normalized_query: str, concepts: Sequence[str],
                    query_tokens: set[str]) -> tuple[float, list[str]]:
    if not normalized_query:
        return 0.0, []
    searchable, record_tokens = _record_search_text(tuple(str(record.get(field, "")) for field in _SEARCH_FIELDS))
    available = set(record_concepts(record))
    matched_categories: list[str] = []

    if concepts:
        concept_scores: list[float] = []
        for concept in concepts:
            match_score, matched = _concept_match(concept, available)
            concept_scores.append(match_score)
            if matched:
                matched_categories.append(matched)
        concept_score = sum(concept_scores) / len(concept_scores)
    else:
        concept_score = 0.0

    lexical_score = len(query_tokens & record_tokens) / max(len(query_tokens), 1)
    exact_phrase = 1.0 if re.search(rf"\b{re.escape(normalized_query)}\b", searchable) else 0.0

    if concepts:
        raw = concept_score * 0.80 + lexical_score * 0.12 + exact_phrase * 0.08
    else:
        raw = lexical_score * 0.78 + exact_phrase * 0.22

    # Exact ontology matches should look exact to the user rather than artificially low.
    if concepts and all(concept in available for concept in concepts):
        raw = max(raw, 0.96 if exact_phrase == 0 else 1.0)

    raw = min(1.0, raw)
    return round(raw * 100, 1), list(dict.fromkeys(matched_categories))


def _semantic_percent(cosine: float) -> float:
    """Convert cosine similarity into a readable, conservative 0-100 score."""

    # Academic query/document cosine values usually occupy a narrower range than
    # 0-1. This mapping avoids showing weak semantic neighbors as near-perfect.
    return round(max(0.0, min(100.0, (cosine - 0.18) / 0.62 * 100)), 1)


def rank_professors(
    professors: Iterable[dict[str, str]],
    query: str,
    limit: int | None = 25,
    *,
    query_embedding: Sequence[float] | None = None,
) -> list[dict[str, str | float]]:
    """Rank by keyword relevance or a hybrid of keywords and stored embeddings."""

    ranked: list[dict[str, str | float]] = []
    normalized_query = normalize(query)
    concepts = query_concepts(query)
    query_tokens = set(tokenize(query))
    for professor in professors:
        keyword_score, matches = _score_prepared(professor, normalized_query, concepts, query_tokens)
        final_score = keyword_score
        semantic_score = 0.0
        semantic_used = False

        if query_embedding:
            professor_embedding = parse_embedding(professor.get("embedding_json", ""))
            if (
                professor_embedding
                and len(professor_embedding) == len(query_embedding)
                and professor.get("embedding_source_hash") == source_hash(professor)
            ):
                semantic_used = True
                semantic_score = _semantic_percent(
                    cosine_similarity(query_embedding, professor_embedding)
                )
                hybrid = semantic_score * 0.72 + keyword_score * 0.28
                # Preserve exact ontology matches such as AI -> Artificial Intelligence.
                if keyword_score >= 90:
                    hybrid = max(hybrid, keyword_score)
                final_score = round(min(100.0, hybrid), 1)

        if final_score < 20:
            continue

        item: dict[str, str | float] = dict(professor)
        item["match_score"] = final_score
        item["keyword_score"] = keyword_score
        item["semantic_score"] = semantic_score
        item["search_mode"] = "AI semantic + keyword" if semantic_used else "Keyword"
        item["match_reason"] = build_match_reason(
            professor,
            query,
            matches,
            final_score,
            semantic_used=semantic_used,
        )
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            -float(item["match_score"]),
            -float(item.get("semantic_score", 0.0)),
            str(item["name"]).lower(),
        )
    )
    if limit is None or limit <= 0:
        return ranked
    return ranked[:limit]


def build_match_reason(
    record: dict[str, str],
    query: str,
    matches: list[str],
    score: float,
    *,
    semantic_used: bool = False,
) -> str:
    categories = record_concepts(record)
    related = [category for category in categories if category not in matches]
    strength = "Strong match" if score >= 80 else "Related match" if score >= 55 else "Possible match"
    query_label = query.strip()
    summary = str(record.get("ai_summary", "")).strip()

    if semantic_used and summary:
        topic_text = ", ".join((matches or categories)[:3])
        suffix = f" Published topics include {topic_text}." if topic_text else ""
        return f"{strength} for “{query_label}” based on semantic similarity: {summary}{suffix}"

    if matches:
        closest = ", ".join(matches[:3])
        if related:
            return (
                f"{strength} for “{query_label}”: the closest published topics are {closest}; "
                f"other listed areas include {', '.join(related[:2])}."
            )
        return f"{strength} for “{query_label}”: the closest published topics are {closest}."

    interests = str(record.get("research_interests", "Not publicly available"))
    if semantic_used:
        return f"{strength} for “{query_label}” based on the meaning of the published research summary: {interests}."
    return f"{strength} based on the published research summary: {interests}."

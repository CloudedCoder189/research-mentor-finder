"""Personalized recommendation core.

Reuses the existing keyword/semantic ranking infrastructure to provide an
explainable, deterministic research-fit score for a locally-stored student
profile. The primary signal is research-interest fit; skills, projects,
coursework and location act as transparent secondary signals.

Weights are explicit constants so the score stays explainable and is never
presented as a likelihood of a professor replying.
"""

from __future__ import annotations

import re
from typing import Any

from services.search import normalize, rank_professors
from services.ui_helpers import topic_values
from services.topic_matching import contains_term, term_variants

# Transparent component weights (sum = 100).
INTEREST_WEIGHT = 55
SKILL_WEIGHT = 15
PROJECT_WEIGHT = 10
COURSEWORK_WEIGHT = 10
LOCATION_WEIGHT = 10

MIN_FIT_SCORE = 30
LABEL_STRONG = "Strong research match"
LABEL_GOOD = "Good research match"
LABEL_POTENTIAL = "Potential match"

ANYWHERE_LOCATIONS = {"anywhere", "any"}

MAX_REASONS = 4
MAX_OVERLAP_REASONS = 2
MAX_SKILL_NAMES = 2
# Location is the weakest signal, so it only fills an otherwise short list.
LOCATION_FILL_LIMIT = 3


def build_profile_query(profile: dict[str, Any]) -> str:
    """Build the recommendation query from the student profile fields."""
    interests = _string_list(profile.get("interests"))
    interest_text = str(profile.get("interest_text") or "").strip()
    skills = _string_list(profile.get("skills"))
    experience = _string_list(profile.get("experience"))
    coursework = _string_list(profile.get("coursework"))

    parts = []
    parts.extend(interests)
    if interest_text:
        parts.append(interest_text)
    parts.extend(skills)
    parts.extend(experience)
    parts.extend(coursework)

    deduped: list[str] = []
    for part in parts:
        cleaned = " ".join(str(part).split())
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return ", ".join(deduped)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [" ".join(str(item).split()).strip() for item in value if str(item or "").strip()]


def _normalized_corpus(record: dict) -> str:
    return normalize(
        " ".join(
            [
                str(record.get("research_interests", "")),
                str(record.get("ai_summary", "")),
                str(record.get("categories", "")),
                str(record.get("ai_categories", "")),
                str(record.get("department", "")),
                str(record.get("title", "")),
                str(record.get("field", "")),
            ]
        )
    )


def _normalized_research_text(record: dict) -> str:
    """Normalized published research prose.

    Narrower than :func:`_normalized_corpus`, which also includes department,
    title and field. Reason text uses this so a weak signal (a skill that only
    matches the department name) is not presented as research fit.
    """
    return normalize(
        " ".join(
            [
                str(record.get("research_interests", "")),
                str(record.get("ai_summary", "")),
            ]
        )
    )


def _normalized_topics(record: dict) -> dict[str, str]:
    """Map normalized topic -> original topic text for verbatim display."""
    mapping: dict[str, str] = {}
    for topic in topic_values(record, limit=100):
        normalized = normalize(topic)
        if normalized and normalized not in mapping:
            mapping[normalized] = topic
    return mapping


def _hits(
    terms: list[str], corpus: str, topic_map: dict[str, str]
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for term in terms:
        matched = next((variant for variant in term_variants(term) if contains_term(corpus, variant)), None)
        if matched:
            topic = topic_map.get(matched)
            hits.append({"term": term, "topic": topic or ""})
    return hits


def _preferred_locations(profile: dict[str, Any]) -> set[str]:
    preferences = profile.get("preferences") or {}
    locations = preferences.get("locations") or []
    values = set()
    for location in locations:
        cleaned = normalize(str(location))
        if not cleaned:
            continue
        if cleaned in ANYWHERE_LOCATIONS:
            values.add("Anywhere")
        else:
            values.add(str(location).strip().title())
    return values


def recommendation_signals(
    record: dict, profile: dict[str, Any]
) -> tuple[dict[str, float], list[dict[str, str]]]:
    """Compute transparent component scores and the grounded hit signals."""
    corpus = _normalized_corpus(record)
    topic_map = _normalized_topics(record)
    record_state = str(record.get("state", "")).strip().title()

    interests = _string_list(profile.get("interests"))
    skills = _string_list(profile.get("skills"))
    experience = _string_list(profile.get("experience"))
    coursework = _string_list(profile.get("coursework"))

    interest_hits = _hits(interests, corpus, topic_map)
    # A title/department mention is not evidence of a research tool or skill.
    skill_hits = _hits(skills, _normalized_research_text(record), topic_map)
    project_hits = _hits(experience, corpus, topic_map)
    coursework_hits = _hits(coursework, corpus, topic_map)

    interest_component = min(1.0, len(interest_hits) / max(1, len(interests)))
    skill_component = min(1.0, len(skill_hits) / max(1, len(skills)))
    project_component = min(1.0, len(project_hits) / max(1, len(experience)))
    coursework_component = min(1.0, len(coursework_hits) / max(1, len(coursework)))

    preferred = _preferred_locations(profile)
    location_hit = bool(preferred) and (
        "Anywhere" in preferred or record_state in preferred
    )

    components = {
        "interest": round(interest_component * INTEREST_WEIGHT, 1),
        "skills": round(skill_component * SKILL_WEIGHT, 1),
        "projects": round(project_component * PROJECT_WEIGHT, 1),
        "coursework": round(coursework_component * COURSEWORK_WEIGHT, 1),
        "location": round(LOCATION_WEIGHT, 1) if location_hit else 0.0,
    }

    signals: list[dict[str, str]] = []
    for entry in interest_hits:
        signals.append(
            {
                "source": "interests",
                "label": "Research-interest fit",
                "detail": entry["term"],
                "topic": entry["topic"],
            }
        )
    for entry in skill_hits:
        signals.append(
            {
                "source": "skills",
                "label": "Skill overlap",
                "detail": entry["term"],
                "topic": entry["topic"],
            }
        )
    for entry in project_hits:
        signals.append(
            {
                "source": "projects",
                "label": "Project / experience overlap",
                "detail": entry["term"],
                "topic": entry["topic"],
            }
        )
    for entry in coursework_hits:
        signals.append(
            {
                "source": "coursework",
                "label": "Coursework foundation",
                "detail": entry["term"],
                "topic": entry["topic"],
            }
        )
    if location_hit:
        signals.append(
            {
                "source": "location",
                "label": "Location preference",
                "detail": record_state,
                "topic": "",
            }
        )

    return components, signals


def _snippet(record: dict, fallback: str, focus: str = "") -> str:
    for key in ("research_interests", "ai_summary"):
        text = " ".join(str(record.get(key, "")).split()).strip()
        if text:
            position = text.casefold().find(focus.casefold()) if focus else -1
            start = max(0, position - 45) if position >= 0 else 0
            # Keep the matched phrase visible, using only the recorded source text.
            if start:
                boundary = text.find(" ", start)
                if boundary >= 0 and boundary < position:
                    start = boundary + 1
            excerpt = text[start:start + max(140, len(focus) + 45)]
            return ("…" if start else "") + excerpt + ("…" if start + len(excerpt) < len(text) else "")
    return fallback


def _professor_name(record: dict) -> str:
    name = str(record.get("name", "")).strip()
    if not name:
        return "Professor"
    name = name.split(",")[0].strip()
    tokens = [
        token
        for token in re.split(r"\s+", name)
        if token not in {"Dr", "Dr.", "Professor", "Prof.", "Prof"}
    ]
    if not tokens:
        return "Professor"
    return f"Professor {tokens[-1]}"


def _overlap_reason(record: dict, entry: dict[str, str]) -> str:
    professor = _professor_name(record)
    if entry["topic"]:
        return (
            f"Your interest in {entry['detail']} overlaps with {professor}'s "
            f"work on {entry['topic']}."
        )
    snippet = _snippet(record, "the published research summary", entry["detail"])
    return (
        f"Your interest in {entry['detail']} lines up with the research summary "
        f"for {professor}: {snippet}."
    )


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _skill_reason(
    record: dict, entries: list[dict[str, str]], topic: str
) -> str:
    """Frame skills as student preparation, never as a claim about the lab."""
    professor = _professor_name(record)
    names = _join_names([entry["detail"] for entry in entries[:MAX_SKILL_NAMES]])
    if topic:
        return (
            f"Your {names} experience is relevant preparation for "
            f"{professor}'s work on {topic}."
        )
    return f"Your {names} experience is relevant preparation for this research area."


def _project_reason(record: dict, entry: dict[str, str]) -> str:
    professor = _professor_name(record)
    if entry["topic"]:
        return (
            f"Your “{entry['detail']}” project or experience is directly "
            f"relevant to {professor}'s work on {entry['topic']}."
        )
    return (
        f"Your “{entry['detail']}” project or experience is directly relevant "
        f"to {professor}'s published research."
    )


def _coursework_reason(record: dict, entry: dict[str, str]) -> str:
    professor = _professor_name(record)
    if entry["topic"]:
        return (
            f"Your {entry['detail']} coursework adds background for "
            f"{professor}'s work on {entry['topic']}."
        )
    return f"Your {entry['detail']} coursework adds background for this research area."


def _location_reason(record: dict) -> str:
    university = str(record.get("university", "")).strip()
    state = str(record.get("state", "")).strip()
    if university and state:
        return f"{university} is in {state}, which matches your preferred region."
    if university:
        return f"{university} matches your preferred location."
    if state:
        return f"This position is based in {state}, which matches your preferred region."
    return ""


def _fallback_reason(record: dict) -> str:
    """Honest last resort so a returned match never explains nothing."""
    professor = _professor_name(record)
    place = str(record.get("university") or record.get("field") or "").strip()
    if place:
        return (
            f"Your stored profile shows limited overlap with {professor}'s work "
            f"at {place}, so this is a lower-confidence fit."
        )
    return f"Your stored profile shows limited overlap with {professor}'s work."


def _entry_keys(entry: dict[str, str]) -> list[str]:
    """Normalized identifiers a reason would spend: the topic and the raw term."""
    keys: list[str] = []
    for value in (entry.get("topic", ""), entry.get("detail", "")):
        normalized = normalize(value)
        if normalized and normalized not in keys:
            keys.append(normalized)
    return keys


def _in_research_text(record: dict, entry: dict[str, str]) -> bool:
    """True when the signal is grounded in published research, not just metadata.

    A matched topic is already a verified professor field, so it stands on its
    own. Otherwise the raw term must appear in the published research prose,
    which rejects signals that only matched department, title or field.
    """
    if entry.get("topic"):
        return True
    return any(contains_term(_normalized_research_text(record), variant)
               for variant in term_variants(entry.get("detail", "")))


def _reasons_for(
    record: dict,
    components: dict[str, float],
    signals: list[dict[str, str]],
    profile: dict[str, Any],
) -> list[str]:
    """Build distinct, grounded reasons in fit-priority order.

    Each bullet must add information that no earlier bullet already spent, so a
    topic matched by an interest is never repeated by coursework, skills or
    location. Weak signals are dropped instead of padding the list.
    """
    reasons: list[str] = []
    seen_text: set[str] = set()
    claimed: set[str] = set()

    def add(text: str, *, force: bool = False) -> bool:
        if not text:
            return False
        if len(reasons) >= MAX_REASONS and not force:
            return False
        key = normalize(text)
        if key in seen_text:
            return False
        seen_text.add(key)
        reasons.append(text)
        return True

    def is_new(entry: dict[str, str]) -> bool:
        keys = _entry_keys(entry)
        return bool(keys) and any(key not in claimed for key in keys)

    def claim(entry: dict[str, str]) -> None:
        claimed.update(_entry_keys(entry))

    by_source: dict[str, list[dict[str, str]]] = {}
    for signal in signals:
        by_source.setdefault(signal["source"], []).append(signal)

    # 1. Research overlap: the most specific signal, capped at two topics.
    for entry in by_source.get("interests", []):
        if len(reasons) >= MAX_OVERLAP_REASONS:
            break
        if not is_new(entry):
            continue
        if add(_overlap_reason(record, entry)):
            claim(entry)

    # 2. Skills / technical fit: student preparation, and only for skills that
    #    actually appear in the published research text.
    skill_entries = [
        entry
        for entry in by_source.get("skills", [])
        if _in_research_text(record, entry) and is_new(entry)
    ]
    if skill_entries:
        topic = ""
        for entry in skill_entries:
            if entry["topic"] and normalize(entry["topic"]) not in claimed:
                topic = entry["topic"]
                break
        if add(_skill_reason(record, skill_entries, topic)):
            for entry in skill_entries:
                claim(entry)

    # 3. Projects / experience, then 4. coursework, each only when the matched
    #    signal is not already explained by research overlap or another bullet.
    for source, builder in (
        ("projects", _project_reason),
        ("coursework", _coursework_reason),
    ):
        if len(reasons) >= MAX_REASONS:
            break
        for entry in by_source.get(source, [])[:1]:
            if not _in_research_text(record, entry) or not is_new(entry):
                continue
            if add(builder(record, entry)):
                claim(entry)
            break

    # 5. Location last, and only when it materially matches a stated region.
    preferred = _preferred_locations(profile)
    if (
        components.get("location", 0) > 0
        and len(reasons) < LOCATION_FILL_LIMIT
        and preferred
        and preferred != {"Anywhere"}
    ):
        add(_location_reason(record))

    if not reasons:
        add(_fallback_reason(record), force=True)
    return reasons



def label_for_score(score: float) -> str:
    if score >= 70:
        return LABEL_STRONG
    if score >= 50:
        return LABEL_GOOD
    return LABEL_POTENTIAL


def score_for_profile(record: dict, profile: dict[str, Any]) -> dict[str, Any]:
    """Return the explainable match for one professor against a profile."""
    components, signals = recommendation_signals(record, profile)
    score = round(
        sum(components.get(key, 0.0) for key in components), 1
    )
    reasons = _reasons_for(record, components, signals, profile)
    return {
        "research_fit_score": score,
        "components": components,
        "signals": signals,
        "reasons": reasons,
        "label": label_for_score(score),
    }


def recommend_from_profile(
    records: list[dict],
    profile: dict[str, Any],
    *,
    limit: int = 20,
    offset: int = 0,
    query_embedding: list[float] | tuple[float, ...] | None = None,
) -> tuple[list[dict], str, bool, int]:
    """Rank professor matches for a profile with transparent ordering.

    Returns (scored_rows, query, semantic_used, total).
    """
    query = build_profile_query(profile)
    semantic_used = query_embedding is not None

    base_by_id: dict[int, float] = {}
    if records:
        ranked = rank_professors(
            records,
            query,
            limit=None,
            query_embedding=query_embedding,
        )
        for item in ranked:
            base_by_id[int(item.get("id", 0))] = float(item.get("match_score", 0.0))

    scored: list[dict] = []
    for record in records:
        match = score_for_profile(record, profile)
        if match["research_fit_score"] < MIN_FIT_SCORE:
            continue
        record_id = int(record.get("id", 0))
        scored.append(
            {
                "record": record,
                "match": match,
                "base_score": base_by_id.get(record_id, 0.0),
            }
        )

    scored.sort(
        key=lambda item: (
            -item["match"]["research_fit_score"],
            -item["base_score"],
            str(item["record"].get("name", "")).lower(),
        )
    )

    total = len(scored)
    page = scored[offset : offset + limit]
    return page, query, semantic_used, total

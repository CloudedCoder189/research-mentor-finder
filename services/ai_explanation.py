"""Optional AI explanation layer for the top research-fit recommendations.

This module is explanation-only. It never scores, reorders, filters or selects
professors: ranking stays in :mod:`services.recommendations` and the caller
decides which record is explained. Every failure path returns ``None`` so the
caller falls back to the deterministic reasons.

Privacy: the model context is built from an explicit allowlist of stored student
and professor fields. Emails, private notes, Gmail data, outreach history, saved
state and auth material are never included. Prompts are not persisted and not
logged; only the returned bullets are cached, keyed by a hash of the context.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from services.ai_enrichment import _extract_json, openai_available, text_model_name
from services.ui_helpers import topic_values
from services.recommendations import score_for_profile

# Bump when the prompt or validation rules change so cached entries are ignored.
PROMPT_VERSION = "research-fit-explanation-v2-selection"

MAX_REASONS = 4
MAX_REASON_CHARS = 260
REQUEST_TIMEOUT_SECONDS = 20.0
# Includes hidden reasoning tokens as well as the visible JSON explanation.
MAX_OUTPUT_TOKENS = 1024
# Only the highest deterministic matches may ever get AI wording, so a page of
# hundreds of professors can never trigger hundreds of model calls.
MAX_RANKED_FOR_AI = 20

CACHE_TTL_SECONDS = 60 * 60 * 24
MAX_CACHE_ENTRIES = 256

DISABLED_VALUES = {"0", "false", "off", "no"}

SYSTEM_PROMPT = (
    "You are explaining a research-match recommendation.\n"
    "Use ONLY the structured data provided.\n"
    "Do not infer unstated facts.\n"
    "Do not invent professor technologies, publications, lab methods, or "
    "student experience.\n"
    "Return concise grounded reasons.\n"
    "If a fact is not in the provided data, do not use it."
)

USER_INSTRUCTIONS = (
    "Explain, in plain second person, why this professor matches this student. "
    "Rules:\n"
    "- Use only facts present in the context below.\n"
    "- Never claim the professor uses a specific technology, language, method, "
    "lab, or publication unless the context states it.\n"
    "- Describe the student's own preparation (interests, skills, coursework, "
    "projects) as preparation, not as a fact about the professor.\n"
    "- Never claim the student is qualified, accepted, likely to get a "
    "response, or likely to get a position.\n"
    "- Never state a numeric match score.\n"
    "- Prefer this order when the data supports it: research overlap, student "
    "preparation, relevant project or experience, location or preference.\n"
    "- Location or preference is lower priority than research fit.\n"
    "- Return between 1 and 4 short bullets. Do not pad the list.\n"
    '- Select from Allowed reasons below. Copy the selected reasons EXACTLY. '
    'Do not add, rewrite, or combine facts.\n'
    '- Return only JSON shaped like {"reasons": ["...", "..."]}.\n'
    "If the evidence is thin, say so modestly instead of overstating the match."
)

# Reasons must be recognizably connected to the supplied context. These words are
# connective tissue used by grounded explanations, so they do not count as
# evidence on their own.
_CONNECTIVE_TOKENS = {
    "align", "aligns", "aligned", "area", "areas", "background", "based",
    "broader", "complements", "connect", "connected", "coursework",
    "experience", "focus", "focuses", "gives", "interest", "interests",
    "mainly", "match", "matches", "overlap", "overlaps", "preparation",
    "preference", "preferences", "project", "projects", "region", "relevant",
    "research", "shared", "student", "supports", "work", "works",
}

_STOP_TOKENS = {
    "and", "are", "for", "from", "has", "have", "into", "not", "that", "the",
    "their", "them", "they", "this", "was", "were", "will", "with", "you",
    "your",
}

# Claims the model must never make.
_FORBIDDEN_PHRASES = (
    "likely to reply",
    "likely to respond",
    "likely to get a reply",
    "guarantee",
    "guaranteed",
    "will reply",
    "will respond",
    "accepted into",
    "accept you",
    "get a position",
    "get the position",
    "offer you a position",
    "highly qualified",
    "qualified for this",
    "perfect match",
    "best candidate",
    "sure thing",
    "definitely reply",
    "no doubt",
)

_TECHNOLOGY_PATTERN = re.compile(
    r"\b(?:uses?|using|works? with|employs?|built with|trained with)\s+"
    r"(python|pytorch|tensorflow|jax|keras|sklearn|scikit|matlab|numpy|opencv|"
    r"ros|cuda|c\+\+|r\b|java|javascript|swift|llama|gpt)\b"
)

_SCORE_PATTERN = re.compile(
    r"\b\d{1,3}\s?(?:%|percent)\b|\b\d+\s*/\s*\d+\b|\bmatch score\b|\bfit score\b",
    re.IGNORECASE,
)

_cache: dict[str, tuple[float, list[str]]] = {}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_list(values: Any, limit: int) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    items: list[str] = []
    for value in values:
        text = _clean(value, 160)
        if text and text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def ai_explanations_enabled() -> bool:
    """AI explanations are opt-out and always require a server-side API key."""
    flag = os.getenv("AI_EXPLANATIONS", "").strip().lower()
    if flag in DISABLED_VALUES:
        return False
    return openai_available()


def build_context(record: dict, profile: dict) -> dict[str, Any]:
    """Allowlisted student/professor context. Nothing else is sent to the model."""
    preferences = profile.get("preferences") or {}
    return {
        "student": {
            "interests": _clean_list(profile.get("interests"), 6),
            "interest_text": _clean(profile.get("interest_text"), 600),
            "skills": _clean_list(profile.get("skills"), 6),
            "coursework": _clean_list(profile.get("coursework"), 6),
            "projects_and_experience": _clean_list(profile.get("experience"), 6),
            "preferred_locations": _clean_list(preferences.get("locations"), 4),
            "remote_ok": bool(preferences.get("remote_ok")),
        },
        "professor": {
            "name": _clean(record.get("name"), 120),
            "university": _clean(record.get("university"), 120),
            "department": _clean(record.get("department"), 120),
            "title": _clean(record.get("title"), 80),
            "verified_topics": _clean_list(topic_values(record, limit=8), 8),
            "research_interests": _clean(record.get("research_interests"), 600),
            "stored_summary": _clean(record.get("ai_summary"), 600),
            "location": _clean(
                " ".join(
                    part
                    for part in (
                        _clean(record.get("city"), 80),
                        _clean(record.get("state"), 60),
                    )
                    if part
                ),
                140,
            ),
        },
    }


def build_prompt(context: dict, allowed_reasons: list[str] | None = None) -> str:
    return (
        f"{USER_INSTRUCTIONS}\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}\n\n"
        f"Allowed reasons:\n{json.dumps(allowed_reasons or [], ensure_ascii=False)}"
    )


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9+ ]", " ", str(text).lower())
    return {
        token
        for token in normalized.split()
        if len(token) > 3 and token not in _STOP_TOKENS
    }


def _is_grounded(reason: str, context_tokens: set[str], context_text: str) -> bool:
    lowered = reason.lower()
    if any(phrase in lowered for phrase in _FORBIDDEN_PHRASES):
        return False
    if _SCORE_PATTERN.search(reason):
        return False
    match = _TECHNOLOGY_PATTERN.search(lowered)
    if match and match.group(1).lower() not in context_text.lower():
        return False
    evidence = _tokens(reason)
    if not evidence:
        return False
    return any(
        token in context_tokens or token in _CONNECTIVE_TOKENS
        for token in evidence
    )


def validate_reasons(payload: Any, context: dict, allowed_reasons: list[str] | None = None) -> list[str] | None:
    """Only return exact server-derived reasons; generated factual claims fail closed."""
    if isinstance(payload, dict):
        payload = payload.get("reasons")
    if not isinstance(payload, list) or not payload:
        return None

    context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
    context_tokens = _tokens(context_text)
    reasons: list[str] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, str):
            return None
        text = " ".join(item.split())
        if not text or len(text) > MAX_REASON_CHARS:
            return None
        if text not in (allowed_reasons or []):
            return None
        if not _is_grounded(text, context_tokens, context_text):
            return None
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        reasons.append(text if text.endswith((".", "!", "?")) else f"{text}.")

    if not reasons:
        return None
    return reasons[:MAX_REASONS]


def cache_key(record: dict, profile: dict, context: dict, model: str) -> str:
    """Hash of identity + content, so any profile or professor change misses."""
    payload = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "professor_id": record.get("id"),
            "context": context,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cached_reasons(key: str) -> list[str] | None:
    entry = _cache.get(key)
    if not entry:
        return None
    stored_at, reasons = entry
    if time.time() - stored_at > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return list(reasons)


def store_reasons(key: str, reasons: list[str]) -> None:
    if len(_cache) >= MAX_CACHE_ENTRIES:
        oldest = sorted(_cache.items(), key=lambda item: item[1][0])[: len(_cache) // 4 or 1]
        for stale_key, _ in oldest:
            _cache.pop(stale_key, None)
    _cache[key] = (time.time(), list(reasons))


def clear_cache() -> None:
    _cache.clear()


def cache_size() -> int:
    return len(_cache)


def _new_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        max_retries=0,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def generate_reasons(record: dict, profile: dict) -> tuple[list[str] | None, str]:
    """Return ``(reasons, status)``. ``reasons`` is ``None`` for every fallback."""
    if not ai_explanations_enabled():
        if not openai_available():
            return None, "no_api_key"
        return None, "disabled"

    model = text_model_name()
    context = build_context(record, profile)
    allowed_reasons = score_for_profile(record, profile)["reasons"]
    if not allowed_reasons:
        return None, "no_evidence"
    key = cache_key(record, profile, context, model)

    hit = cached_reasons(key)
    if hit is not None:
        return hit, "cached"

    if not context["student"]["interests"]:
        return None, "no_evidence"

    try:
        client = _new_client()
        model_options = {}
        if model == "gpt-5-mini" or model.startswith("gpt-5-mini-2025-"):
            model_options["reasoning"] = {"effort": "minimal"}
        response = client.responses.create(
            model=model,
            store=False,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            instructions=SYSTEM_PROMPT,
            input=build_prompt(context, allowed_reasons),
            **model_options,
        )
        output_text = getattr(response, "output_text", "") or ""
    except TimeoutError:
        return None, "timeout"
    except Exception as error:  # noqa: BLE001 - any failure falls back
        name = type(error).__name__.lower()
        if "timeout" in name or "timeout" in str(error).lower():
            return None, "timeout"
        return None, "error"

    try:
        parsed = _extract_json(output_text)
    except Exception:  # noqa: BLE001 - malformed JSON falls back
        return None, "invalid"

    reasons = validate_reasons(parsed, context, allowed_reasons)
    if not reasons:
        return None, "invalid"

    store_reasons(key, reasons)
    return reasons, "ai"

"""Mocked tests for the optional, explanation-only AI layer.

No real AI calls are made: every provider interaction goes through a fake client
or a monkeypatched ``generate_reasons``. The tests pin the four guarantees of the
feature: AI never changes ranking, output is grounded/validated, every failure
falls back to the deterministic reasons, and private data never reaches the
model.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import api.services as api_services
import services.ai_explanation as ai
from api.routes import recommendations as routes
from api.schemas.recommendations import RecommendationResponse
from api.services import ExplainRequest, StudentProfileInput
from services.recommendations import recommend_from_profile, score_for_profile

VISION_RECORD = {
    "id": 11,
    "name": "Dr. Devi Chandraker",
    "university": "UC San Diego",
    "city": "La Jolla",
    "state": "California",
    "research_interests": (
        "Computer vision and robotics for visual recognition, using Python for "
        "computational research on large-scale image datasets"
    ),
    "ai_summary": (
        "Develops visual-recognition models for autonomous navigation and "
        "robotic manipulation."
    ),
    "categories": "Computer Vision, Robotics",
    "ai_categories": "Machine Learning",
    "department": "Computer Science and Engineering",
    "title": "Professor",
    "field": "Computer Science",
}

OTHER_RECORD = {
    "id": 12,
    "name": "Dr. Alan Fox",
    "university": "U Washington",
    "city": "Seattle",
    "state": "Washington",
    "research_interests": "Data structures and algorithms for compilers",
    "ai_summary": "Studies program analysis and compiler optimization.",
    "categories": "Systems",
    "ai_categories": "Programming Languages",
    "department": "Computer Science",
    "title": "Professor",
    "field": "Computer Science",
}

PROFILE = {
    "interests": ["Computer vision"],
    "interest_text": "",
    "skills": ["Python"],
    "experience": ["Built a visual recognition project"],
    "coursework": ["Machine Learning"],
    "preferences": {"locations": ["California"], "remote_ok": True},
}

GROUNDED_REASONS = score_for_profile(VISION_RECORD, PROFILE)["reasons"][:2]


@pytest.fixture(autouse=True)
def _isolate_cache():
    ai.clear_cache()
    yield
    ai.clear_cache()


def _fake_client(*, text: str | None = None, error: Exception | None = None, calls=None):
    class FakeResponses:
        def create(self, **kwargs):
            if calls is not None:
                calls.append(kwargs)
            if error is not None:
                raise error
            return SimpleNamespace(output_text=text)

    return SimpleNamespace(responses=FakeResponses())


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("AI_EXPLANATIONS", raising=False)


def _profile_input(interests: list[str] | None = None) -> StudentProfileInput:
    payload = {**PROFILE, "interests": interests or PROFILE["interests"]}
    return StudentProfileInput(**payload)


# --- valid output is used -------------------------------------------------


def test_valid_grounded_response_is_used(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(text=json.dumps({"reasons": GROUNDED_REASONS})),
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert status == "ai"
    assert reasons == GROUNDED_REASONS


@pytest.mark.parametrize("model", ["gpt-5-mini", "gpt-5-mini-2025-08-07", "gpt-4.1-mini"])
def test_provider_output_is_bounded_without_unsupported_reasoning(monkeypatch, model):
    _enable(monkeypatch)
    monkeypatch.setenv("OPENAI_TEXT_MODEL", model)
    calls = []
    monkeypatch.setattr(ai, "_new_client", lambda: _fake_client(
        text=json.dumps({"reasons": GROUNDED_REASONS}), calls=calls))
    assert ai.generate_reasons(VISION_RECORD, PROFILE)[1] == "ai"
    assert calls[0]["max_output_tokens"] == 1024
    assert calls[0]["store"] is False
    if model.startswith("gpt-5-mini"):
        assert calls[0]["reasoning"] == {"effort": "minimal"}
    else:
        assert "reasoning" not in calls[0]


def test_reasons_are_limited_to_four(monkeypatch) -> None:
    _enable(monkeypatch)
    many = GROUNDED_REASONS * 3
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(text=json.dumps({"reasons": many})),
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert status == "ai"
    assert reasons is not None
    assert 1 <= len(reasons) <= 4


# --- malformed / invalid output falls back --------------------------------


def test_malformed_json_falls_back(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai, "_new_client", lambda: _fake_client(text="not json at all")
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "invalid"


@pytest.mark.parametrize(
    "payload",
    [
        {"reasons": []},
        {"reasons": "Computer vision overlap"},
        {"reasons": [123]},
        {},
    ],
)
def test_invalid_shape_falls_back(monkeypatch, payload) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai, "_new_client", lambda: _fake_client(text=json.dumps(payload))
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "invalid"


def test_forbidden_claims_are_rejected(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(
            text=json.dumps(
                {
                    "reasons": [
                        "You are likely to get a reply from Professor Chandraker."
                    ]
                }
            )
        ),
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "invalid"


def test_invented_technology_is_rejected(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(
            text=json.dumps(
                {"reasons": ["Professor Chandraker uses PyTorch for Computer vision."]}
            )
        ),
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "invalid"


def test_mixed_valid_and_invalid_reasons_fall_back() -> None:
    context = ai.build_context(VISION_RECORD, PROFILE)
    payload = {
        "reasons": [
            GROUNDED_REASONS[0],
            "You are guaranteed an offer from this professor.",
        ]
    }
    assert ai.validate_reasons(payload, context, GROUNDED_REASONS) is None


# --- provider failures fall back ------------------------------------------


def test_timeout_falls_back(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai, "_new_client", lambda: _fake_client(error=TimeoutError("slow"))
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "timeout"


def test_provider_error_falls_back(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(
        ai, "_new_client", lambda: _fake_client(error=RuntimeError("boom"))
    )

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "error"


def test_no_api_key_falls_back(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "no_api_key"


def test_disabled_flag_falls_back(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setenv("AI_EXPLANATIONS", "0")

    reasons, status = ai.generate_reasons(VISION_RECORD, PROFILE)

    assert reasons is None
    assert status == "disabled"


# --- cache ----------------------------------------------------------------


def test_cache_prevents_duplicate_provider_calls(monkeypatch) -> None:
    _enable(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(text=json.dumps({"reasons": GROUNDED_REASONS}), calls=calls),
    )

    first, first_status = ai.generate_reasons(VISION_RECORD, PROFILE)
    second, second_status = ai.generate_reasons(VISION_RECORD, dict(PROFILE))

    assert first == second == GROUNDED_REASONS
    assert first_status == "ai"
    assert second_status == "cached"
    assert len(calls) == 1


def test_profile_change_invalidates_cache(monkeypatch) -> None:
    _enable(monkeypatch)
    calls: list = []
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(text=json.dumps({"reasons": GROUNDED_REASONS}), calls=calls),
    )

    ai.generate_reasons(VISION_RECORD, PROFILE)
    changed = {**PROFILE, "skills": ["Python", "Robotics"]}
    ai.generate_reasons(VISION_RECORD, changed)

    assert len(calls) == 2


# --- privacy / grounding --------------------------------------------------


def test_context_excludes_private_and_unlisted_data() -> None:
    record = {
        **VISION_RECORD,
        "email": "private@example.edu",
        "notes": "SECRET-PROF-NOTE",
        "outreach_status": "Sent",
        "gmail_body": "SECRET-GMAIL-BODY",
    }
    profile = {
        **PROFILE,
        "private_notes": "SECRET-STUDENT-NOTE",
        "email_body": "SECRET-EMAIL",
        "auth_token": "SECRET-TOKEN",
        "outreach_history": ["SECRET-OUTREACH"],
    }

    context = ai.build_context(record, profile)
    serialized = json.dumps(context, ensure_ascii=False)

    for secret in (
        "private@example.edu",
        "SECRET-PROF-NOTE",
        "SECRET-GMAIL-BODY",
        "SECRET-STUDENT-NOTE",
        "SECRET-EMAIL",
        "SECRET-TOKEN",
        "SECRET-OUTREACH",
    ):
        assert secret not in serialized
    assert set(context) == {"student", "professor"}

    prompt = ai.build_prompt(context)
    assert "SECRET-TOKEN" not in prompt
    assert "SECRET-GMAIL-BODY" not in prompt


def test_validate_reasons_requires_context_evidence() -> None:
    context = ai.build_context(VISION_RECORD, PROFILE)
    # Grounded reason passes.
    assert ai.validate_reasons({"reasons": [GROUNDED_REASONS[0]]}, context, GROUNDED_REASONS)
    # A reason whose only distinctive words are nowhere in the context is dropped.
    assert (
        ai.validate_reasons(
            {"reasons": ["Quantum astrology predicts gravitational anomalies."]},
            context, GROUNDED_REASONS,
        )
        is None
    )


# --- ranking / order are untouched ----------------------------------------


def test_ai_explanations_do_not_change_ranking(monkeypatch) -> None:
    records = [OTHER_RECORD, VISION_RECORD]
    before = recommend_from_profile(records, PROFILE, limit=10)
    baseline = [
        (item["record"]["id"], item["match"]["research_fit_score"]) for item in before[0]
    ]
    assert baseline[0][0] == VISION_RECORD["id"]

    _enable(monkeypatch)
    monkeypatch.setattr(
        ai,
        "_new_client",
        lambda: _fake_client(text=json.dumps({"reasons": GROUNDED_REASONS})),
    )
    ai.generate_reasons(VISION_RECORD, PROFILE)

    after = recommend_from_profile(records, PROFILE, limit=10)
    assert [
        (item["record"]["id"], item["match"]["research_fit_score"]) for item in after[0]
    ] == baseline


def test_explain_record_keeps_deterministic_match_while_adding_ai(monkeypatch) -> None:
    _enable(monkeypatch)
    monkeypatch.setattr(api_services, "fetch_professors", lambda *a, **k: [VISION_RECORD])
    monkeypatch.setattr(
        api_services,
        "generate_reasons",
        lambda record, profile: (list(GROUNDED_REASONS), "ai"),
    )

    baseline = score_for_profile(VISION_RECORD, PROFILE)

    without_ai = api_services.explain_record(
        VISION_RECORD["id"], _profile_input(), include_ai=False
    )
    assert without_ai is not None
    assert without_ai.results[0].match.ai_explanation is None

    with_ai = api_services.explain_record(
        VISION_RECORD["id"], _profile_input(), include_ai=True
    )
    assert with_ai is not None
    match = with_ai.results[0].match
    assert match.research_fit_score == baseline["research_fit_score"]
    assert match.reasons == baseline["reasons"]
    assert match.ai_explanation is not None
    assert match.ai_explanation.source == "ai"
    assert match.ai_explanation.reasons == list(GROUNDED_REASONS)


def test_explanation_only_generated_for_requested_professor(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(api_services, "fetch_professors", lambda *a, **k: [VISION_RECORD])
    monkeypatch.setattr(
        api_services,
        "generate_reasons",
        lambda record, profile: (
            calls.append(record["id"]) or list(GROUNDED_REASONS),
            "ai",
        ),
    )
    profile = _profile_input()

    api_services.explain_record(VISION_RECORD["id"], profile, include_ai=False)
    assert calls == []

    api_services.explain_record(VISION_RECORD["id"], profile, include_ai=True)
    assert calls == [VISION_RECORD["id"]]


def test_ai_generation_is_skipped_for_a_record_outside_top_matches(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(api_services, "MAX_RANKED_FOR_AI", 1)
    monkeypatch.setattr(
        api_services,
        "generate_reasons",
        lambda record, profile: (calls.append(record["id"]) or [], "error"),
    )

    # The weak match is eligible for explanation but sits outside the top page.
    match = score_for_profile(OTHER_RECORD, PROFILE)
    api_services._attach_ai_explanation(
        OTHER_RECORD, PROFILE, match, [VISION_RECORD, OTHER_RECORD]
    )

    assert calls == []
    assert match["ai_explanation"]["status"] == "not_top_matches"
    assert match["ai_explanation"]["reasons"] == []


# --- route forwards the opt-in flag ---------------------------------------


def test_explain_route_forwards_include_ai(monkeypatch) -> None:
    from starlette.requests import Request
    http_request = Request({"type": "http", "headers": []})
    monkeypatch.setattr(routes, "require_user_and_csrf", lambda *args: SimpleNamespace(user_id="test"))
    monkeypatch.setattr(routes, "reserve_explanation", lambda *args: None)
    captured: dict = {}

    def fake_explain(professor_id, profile, include_ai=False):
        captured["include_ai"] = include_ai
        return RecommendationResponse(
            generated_at="now", query="q", mode="Explain", total=0, offset=0, limit=1
        )

    monkeypatch.setattr(routes, "explain_record", fake_explain)

    routes.explain(
        ExplainRequest(profile=_profile_input(), researcher_id=11, include_ai=True), http_request
    )
    assert captured["include_ai"] is True

    routes.explain(ExplainRequest(profile=_profile_input(), researcher_id=11), http_request)
    assert captured["include_ai"] is False

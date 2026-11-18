"""Explanation quality tests for the "Why you match" reasons.

Ranking, persistence, auth, search, Gmail and outreach are out of scope here.
These tests pin the presentation contract only: every bullet must be grounded in
stored student profile data or verified professor fields, must add information no
earlier bullet already spent, and must be ordered by fit priority.
"""

from __future__ import annotations

import re

from services.recommendations import score_for_profile

VISION_RECORD = {
    "id": 11,
    "name": "Dr. Devi Chandraker",
    "university": "UC San Diego",
    "city": "La Jolla",
    "state": "California",
    "research_interests": (
        "Computer vision and robotics for visual recognition, using Python for "
        "large-scale image datasets"
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


def _profile(**overrides) -> dict:
    profile = {
        "interests": ["Computer vision"],
        "interest_text": "",
        "skills": [],
        "experience": [],
        "coursework": [],
        "preferences": {"locations": [], "remote_ok": False},
    }
    profile.update(overrides)
    return profile


def _reasons(record: dict, profile: dict) -> list[str]:
    return score_for_profile(record, profile)["reasons"]


def test_research_overlap_leads_with_specific_topics() -> None:
    reasons = _reasons(VISION_RECORD, _profile(interests=["Computer vision", "Robotics"]))
    assert len(reasons) >= 2, reasons
    assert reasons[0] == (
        "Your interest in Computer vision overlaps with Professor Chandraker's "
        "work on Computer Vision."
    )
    assert reasons[1] == (
        "Your interest in Robotics overlaps with Professor Chandraker's work on Robotics."
    )
    # The collapsed card renders reasons[0], so it must stay a short summary.
    assert len(reasons[0].split()) <= 20


def test_duplicate_signals_are_suppressed() -> None:
    """The same topic matched by interest, coursework and skills is explained once."""
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision", "computer vision"],
            coursework=["Computer Vision"],
            skills=["Python"],
        ),
    )
    joined = " ".join(reasons)
    assert joined.count("Computer Vision") == 1, reasons
    # Coursework repeated the interest topic, so it must not become a bullet.
    assert not any(reason.startswith("Your Computer Vision coursework") for reason in reasons)


def test_unrelated_skills_are_not_shown() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            skills=["Java", "COBOL"],
        ),
    )
    joined = " ".join(reasons)
    assert "Java" not in joined
    assert "COBOL" not in joined
    assert len(reasons) == 1, reasons


def test_skill_match_never_claims_professor_uses_the_skill() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(interests=["Computer vision"], skills=["Python"]),
    )
    skill_reasons = [reason for reason in reasons if "Python" in reason]
    assert len(skill_reasons) == 1, reasons
    skill_reason = skill_reasons[0]
    assert skill_reason.startswith("Your Python experience is relevant preparation")
    for claim in ("uses Python", "works in Python", "with Python", "Python expert"):
        assert claim not in skill_reason


def test_skill_matched_only_by_department_is_not_a_reason() -> None:
    """A skill that only matches the department name is not a research relationship."""
    record = {
        **VISION_RECORD,
        "research_interests": "Protein structure prediction",
        "ai_summary": "Computational study of protein folding and dynamics.",
        "department": "Biology",
    }
    reasons = _reasons(
        record,
        _profile(interests=["Protein structure prediction"], skills=["Biology"]),
    )
    assert "Biology" not in " ".join(reasons), reasons
    assert len(reasons) == 1, reasons


def test_relevant_project_appears() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            experience=["visual recognition"],
        ),
    )
    project_reasons = [reason for reason in reasons if "visual recognition" in reason]
    assert len(project_reasons) == 1, reasons
    assert project_reasons[0] == (
        "Your “visual recognition” project or experience is directly relevant "
        "to Professor Chandraker's published research."
    )


def test_relevant_project_can_carry_its_own_topic() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            experience=["Machine Learning"],
        ),
    )
    assert reasons[-1] == (
        "Your “Machine Learning” project or experience is directly relevant "
        "to Professor Chandraker's work on Machine Learning."
    )


def test_project_duplicate_of_research_overlap_is_suppressed() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            experience=["Computer Vision"],
        ),
    )
    assert len(reasons) == 1, reasons


def test_location_is_lower_priority_than_research_overlap() -> None:
    profile = _profile(
        interests=["Computer vision", "Robotics"],
        preferences={"locations": ["California"], "remote_ok": True},
    )
    reasons = _reasons(VISION_RECORD, profile)
    location_reasons = [reason for reason in reasons if "matches your preferred region" in reason]
    assert len(location_reasons) == 1, reasons
    assert location_reasons[0] == (
        "UC San Diego is in California, which matches your preferred region."
    )
    assert reasons[-1] == location_reasons[0]
    # Research overlap comes first.
    assert "overlaps with Professor Chandraker" in reasons[0]


def test_location_dropped_when_three_research_reasons_exist() -> None:
    """Location only fills an otherwise short list; it never displaces research fit."""
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision", "Robotics"],
            skills=["Python"],
            preferences={"locations": ["California"], "remote_ok": True},
        ),
    )
    assert len(reasons) == 3, reasons
    assert not any("matches your preferred region" in reason for reason in reasons)


def test_location_dropped_when_reasons_hit_the_cap() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision", "Robotics"],
            skills=["Python"],
            coursework=["visual recognition"],
            preferences={"locations": ["California"], "remote_ok": True},
        ),
    )
    assert len(reasons) == 4, reasons
    assert not any("matches your preferred region" in reason for reason in reasons)


def test_anywhere_preference_is_not_a_location_reason() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            preferences={"locations": ["Anywhere"], "remote_ok": True},
        ),
    )
    assert not any("preferred region" in reason for reason in reasons), reasons


def test_single_strong_reason_is_not_padded() -> None:
    reasons = _reasons(
        VISION_RECORD,
        _profile(
            interests=["Computer vision"],
            skills=["COBOL"],
            coursework=["Underwater basket weaving"],
            preferences={"locations": ["Maine"], "remote_ok": False},
        ),
    )
    assert reasons == [
        "Your interest in Computer vision overlaps with Professor Chandraker's "
        "work on Computer Vision."
    ]


def test_only_grounded_data_appears_in_reasons() -> None:
    profile = _profile(
        interests=["Computer vision"],
        skills=["Python"],
        experience=["Built a visual-recognition project"],
        coursework=["Machine Learning"],
        preferences={"locations": ["California"], "remote_ok": True},
    )
    reasons = _reasons(VISION_RECORD, profile)

    profile_text = " ".join(
        [
            *profile["interests"],
            *profile["skills"],
            *profile["experience"],
            *profile["coursework"],
        ]
    ).casefold()
    record_text = " ".join(
        str(value)
        for key, value in VISION_RECORD.items()
        if isinstance(value, str)
    ).casefold()

    # No fabricated technologies, labs, publications or methods.
    for invented in ("tensorflow", "pytorch", "ros", "nvidia", "google", "ieee"):
        assert invented not in " ".join(reasons).casefold()
    # Professor name comes from the record, and every quoted item is stored.
    assert "Chandraker" in " ".join(reasons)
    for reason in reasons:
        assert "“" not in reason or any(
            item in reason for item in profile["experience"]
        )
    # Terms introduced by a bullet are grounded in profile or record text.
    for reason in reasons:
        for term in ("Computer Vision", "Machine Learning", "Robotics", "Python"):
            if term in reason:
                assert term.casefold() in profile_text or term.casefold() in record_text


def test_reasons_are_deterministic() -> None:
    profile = _profile(
        interests=["Computer vision", "Robotics"],
        skills=["Python"],
        experience=["Built a visual-recognition project"],
        coursework=["Machine Learning"],
        preferences={"locations": ["California"], "remote_ok": True},
    )
    first = _reasons(VISION_RECORD, profile)
    second = _reasons(VISION_RECORD, dict(profile))
    assert first == second
    assert len(first) <= 4
    assert len({re.sub(r"\W+", "", reason) for reason in first}) == len(first)


def test_explanations_do_not_change_ranking_scores() -> None:
    """Reason text is presentation only: components and score stay signal-driven."""
    profile = _profile(
        interests=["Computer vision", "Robotics"],
        skills=["Python"],
        coursework=["Computer Vision"],
        preferences={"locations": ["California"], "remote_ok": True},
    )
    match = score_for_profile(VISION_RECORD, profile)
    assert match["components"]["interest"] == 55.0
    assert match["components"]["skills"] == 15.0
    assert match["components"]["coursework"] == 10.0
    assert match["components"]["location"] == 10.0
    assert match["research_fit_score"] == 90.0
    assert match["label"] == "Strong research match"


def test_reasons_never_empty_for_returned_match() -> None:
    match = score_for_profile(VISION_RECORD, _profile(interests=["Robotics"]))
    assert match["reasons"]
    assert all(reason.strip().endswith(".") for reason in match["reasons"])

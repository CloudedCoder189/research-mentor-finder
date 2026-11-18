"""Positive/negative relevance cases discovered during the demo review."""
import pytest

from services.recommendations import score_for_profile
from services.search import score_professor, query_concepts


def record(text, **extra):
    return {"name": "Synthetic Researcher", "department": "Chemistry", "title": "Department Chair",
            "research_interests": text, "categories": "", "ai_categories": "", **extra}


def profile(interest, skills=None):
    return {"interests": [interest], "skills": skills or [], "preferences": {}}


def test_short_terms_do_not_match_inside_unrelated_words():
    chemistry = record("Chemistry and molecular materials")
    match = score_for_profile(chemistry, profile("Chemistry", ["R"]))
    assert match["components"]["skills"] == 0
    assert match["research_fit_score"] == 55
    assert score_for_profile(chemistry, profile("AI"))["components"]["interest"] == 0


def test_plural_project_noun_is_supported_without_partial_word_hits():
    match = score_for_profile(record("CNN image classifiers"), {
        **profile("Chemistry"), "experience": ["CNN image classifier"]})
    assert match["components"]["projects"] == 10


def test_department_only_skill_does_not_raise_fit_score():
    match = score_for_profile(record("Protein structure prediction", department="Biology"),
                              profile("Protein structure prediction", ["Biology"]))
    assert match["components"]["skills"] == 0


@pytest.mark.parametrize(("skill", "text", "expected"), [
    ("R", "Statistical analysis using R", 15),
    ("C++", "Robotics using C++", 15),
    ("C", "Robotics using C++", 0),
    ("Java", "JavaScript interfaces", 0),
    ("Python", "Python models", 15),
])
def test_programming_language_boundaries(skill, text, expected):
    assert score_for_profile(record(text), profile("Robotics", [skill]))["components"]["skills"] == expected


@pytest.mark.parametrize(("interest", "positive", "negative"), [
    ("Climate and the environment", "Climate adaptation and sustainability", "Operating systems"),
    ("Astronomy and astrophysics", "Astrophysics and stellar evolution", "Molecular chemistry"),
    ("Computer systems", "Distributed systems and computer architecture", "Immune systems"),
    ("Renewable energy", "Solar energy conversion", "Energy in language models"),
    ("AI", "Artificial intelligence methods", "Department Chair"),
])
def test_supported_interest_aliases_are_specific(interest, positive, negative):
    assert score_for_profile(record(positive), profile(interest))["components"]["interest"] == 55
    assert score_for_profile(record(negative), profile(interest))["components"]["interest"] == 0


def test_quantum_search_does_not_become_generic_computer_science():
    unrelated = record("Web accessibility and interfaces", department="Computer Science", categories="Human-Computer Interaction")
    relevant = record("Quantum computation and qubit error correction", department="Computer Science")
    assert query_concepts("Quantum computing") == ["Quantum Computing"]
    assert score_professor(unrelated, "Quantum computing")[0] == 0
    assert score_professor(relevant, "Quantum computing")[0] >= 95


def test_unknown_computing_modifier_is_not_an_exact_cs_match():
    unrelated = record("Web accessibility", department="Computer Science")
    assert score_professor(unrelated, "neuromorphic computing")[0] < 30

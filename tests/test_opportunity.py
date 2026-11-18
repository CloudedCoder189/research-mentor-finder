from services.opportunity import assess_outreach_potential


def test_explicit_undergraduate_research_is_strong():
    record = {
        "title": "Assistant Professor",
        "research_interests": "Machine learning",
        "website_url": "https://example.edu/lab",
        "profile_url": "https://example.edu/person",
    }
    result = assess_outreach_potential(
        record,
        source_text="Our lab has undergraduate research opportunities and open positions.",
        source_url="https://example.edu/lab/join",
    )
    assert result.level == "Strong"
    assert "open positions" in result.signals.lower() or "undergraduate" in result.signals.lower()


def test_lab_director_is_moderate_without_opening_claim():
    record = {
        "title": "Professor",
        "research_interests": "Robotics",
        "website_url": "https://example.edu/lab",
        "profile_url": "https://example.edu/person",
    }
    result = assess_outreach_potential(
        record,
        source_text="She is the founding director of the Robotics Research Lab.",
    )
    assert result.level == "Moderate"
    assert "leads" in result.signals.lower()


def test_research_title_is_moderate_but_does_not_claim_acceptance():
    record = {
        "title": "Associate Professor",
        "research_interests": "Natural language processing",
        "website_url": "Not publicly available",
        "profile_url": "https://example.edu/person",
    }
    result = assess_outreach_potential(record)
    assert result.level == "Moderate"
    assert "research-active" in result.signals.lower()

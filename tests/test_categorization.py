from services.categorization import categorize_with_keywords


def test_reinforcement_learning_gets_ml_and_ai_labels():
    categories = categorize_with_keywords("Reinforcement Learning and Interactive Learning")
    assert "Reinforcement Learning" in categories
    assert "Machine Learning" in categories
    assert "Artificial Intelligence" in categories


def test_cognitive_science_is_not_other():
    categories = categorize_with_keywords("Cognitive Science and Probabilistic Programming")
    assert "Cognitive Science" in categories
    assert "Other Computing Research" not in categories

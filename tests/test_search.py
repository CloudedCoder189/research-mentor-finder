from services.search import rank_professors, score_professor


def test_machine_learning_record_scores_above_unrelated_record() -> None:
    relevant = {
        "name": "Relevant",
        "department": "Computer Science",
        "title": "Professor",
        "research_interests": "Machine learning and deep learning for climate forecasting",
        "categories": "Artificial Intelligence, Machine Learning, Deep Learning, Climate & Sustainability",
    }
    unrelated = {
        "name": "Unrelated",
        "department": "History",
        "title": "Professor",
        "research_interests": "Ancient Mediterranean history",
        "categories": "History",
    }

    relevant_score, _ = score_professor(relevant, "machine learning")
    unrelated_score, _ = score_professor(unrelated, "machine learning")
    assert relevant_score >= 95
    assert relevant_score > unrelated_score


def test_broad_ai_matches_ai_subfields_strongly() -> None:
    robotics = {
        "name": "Robotics Person",
        "department": "Computer Science",
        "title": "Professor",
        "research_interests": "Robot learning and autonomous systems",
        "categories": "Robotics, Autonomous Systems, Artificial Intelligence",
    }
    score, matches = score_professor(robotics, "AI")
    assert score >= 85
    assert matches


def test_combined_query_rewards_both_topics() -> None:
    combined = {
        "name": "Climate ML",
        "department": "Computer Science",
        "title": "Professor",
        "research_interests": "Machine learning for climate and sustainability",
        "categories": "Artificial Intelligence, Machine Learning, Climate & Sustainability",
    }
    only_ml = {
        "name": "Only ML",
        "department": "Computer Science",
        "title": "Professor",
        "research_interests": "Machine learning systems",
        "categories": "Artificial Intelligence, Machine Learning, Systems",
    }
    combined_score, _ = score_professor(combined, "AI for climate change")
    only_score, _ = score_professor(only_ml, "AI for climate change")
    assert combined_score > only_score


def test_ranking_respects_limit() -> None:
    records = [
        {
            "name": f"Professor {number}",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Artificial intelligence and machine learning",
            "categories": "Artificial Intelligence, Machine Learning",
        }
        for number in range(10)
    ]
    assert len(rank_professors(records, "AI", limit=3)) == 3


def test_computer_science_alias_matches_cs_department():
    record = {
        "name": "Example Researcher",
        "university": "Example University",
        "department": "Computer Science and Engineering",
        "title": "Faculty",
        "research_interests": "Distributed systems",
        "categories": "Systems",
        "email": "example@example.edu",
    }
    score, matches = score_professor(record, "cs")
    assert score >= 90
    assert "Computer Science" in matches


def test_rank_professors_can_return_all_matches():
    records = [
        {
            "name": f"Professor {index}",
            "university": "Example University",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Machine learning and artificial intelligence",
            "categories": "Machine Learning, Artificial Intelligence",
            "ai_categories": "",
            "ai_summary": "",
            "embedding_json": "",
        }
        for index in range(40)
    ]
    results = rank_professors(records, "machine learning", limit=None)
    assert len(results) == 40

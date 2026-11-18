from api.schemas.recommendations import recommendation_match_dto


def test_evidence_keeps_profile_term_separate_from_matched_topic():
    match = recommendation_match_dto({"signals": [{"source": "interests", "label": "Research interest", "detail": "Robotics", "topic": "Robot learning"}]})
    signal = match.signals[0]
    assert signal.detail == "Robotics"
    assert signal.topic == "Robot learning"


def test_missing_topic_is_unknown_instead_of_invented_evidence():
    match = recommendation_match_dto({"signals": [{"source": "location", "label": "Location preference", "detail": "WA"}]})
    assert match.signals[0].topic == ""

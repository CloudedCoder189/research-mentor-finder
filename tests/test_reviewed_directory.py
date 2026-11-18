import copy
from services.reviewed_directory import discovery_candidate, reviewed_record
from api import services
from api.schemas.researcher import profile_dto, summary_dto


def claire():
    return dict(id=746, name="Claire Ralph", university="California Institute of Technology",
                title="Director, Career Achievement, Leadership, and Exploration",
                research_interests="skip to main content Positions Available Open About submenu",
                ai_summary="Career leadership", embedding_json="[1,2]", categories="Robotics",
                opportunity_level="Moderate", opportunity_signals="Mentoring", verification_status="Verified")


def test_cleaning_preserves_original_and_does_not_invent_research():
    original = claire(); before = copy.deepcopy(original)
    result = reviewed_record(original)
    assert original == before
    assert "Lecturer" in result["title"]
    assert result["research_interests"] == "Not publicly available"
    assert result["embedding_json"] == result["ai_summary"] == result["categories"] == ""
    assert result["opportunity_level"] == "Basic"
    assert result["verification_status"] == "Review"
    assert reviewed_record(result) == result


def test_identity_guards_and_future_source_correction():
    unrelated = {**claire(), "name": "Another person"}
    assert reviewed_record(unrelated) == unrelated
    corrected = {**claire(), "research_interests": "Computer science education", "ai_summary": "Education research"}
    result = reviewed_record(corrected)
    assert result["research_interests"] == corrected["research_interests"]
    assert result["ai_summary"] == corrected["ai_summary"]


def test_unavailable_source_is_not_upgraded_to_verified():
    record = {**claire(), "id": 745, "name": "Jinghao Cao", "verification_status": "Failed"}
    result = reviewed_record(record)
    assert result["verification_status"] == "Failed"
    assert result["research_interests"] == "Not publicly available"
    assert "Current affiliation" in result["verification_issues"]


def test_marketing_exclusion_keeps_academic_staff_and_updated_roles():
    marketing = dict(id=1515, name="Emily Wadkins", university="Oregon State University", title="Marketing and Communications Manager")
    assert not discovery_candidate(marketing)
    assert discovery_candidate({**marketing, "title": "Research Professor"})
    assert discovery_candidate(claire())


def test_profile_and_saved_summaries_never_publish_navigation():
    assert "Lecturer" in profile_dto(claire()).researcher.title
    assert summary_dto(claire()).topics == []
    assert "skip to main content" not in summary_dto(claire()).research_interests


def test_discovery_uses_reviewed_records_and_excludes_marketing(monkeypatch):
    marketing = dict(id=1515, name="Emily Wadkins", university="Oregon State University", title="Marketing and Communications Manager")
    monkeypatch.setattr(services, "fetch_professors", lambda *a, **k: [claire(), marketing])
    monkeypatch.setattr(services, "apply_filters", lambda rows, **k: rows)
    result = services._load_and_filter(university=None)
    assert [r["id"] for r in result] == [746]
    assert result[0]["embedding_json"] == ""

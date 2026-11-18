from services.admin_auth import hash_password, password_matches
from services.audit_scope import select_audit_records
from services.ui_helpers import (
    outreach_filter_matches,
    resolve_search_query,
    topic_values,
    verification_filter_matches,
)
from services.university_registry import infer_department_category, metadata_for, slugify


RECORDS = [
    {"id": 1, "name": "A", "university": "U1", "verification_status": "Not checked"},
    {"id": 2, "name": "B", "university": "U1", "verification_status": "Failed"},
    {"id": 3, "name": "C", "university": "U2", "verification_status": "Review"},
    {"id": 4, "name": "D", "university": "U2", "verification_status": "Verified"},
]


def test_incremental_audit_scopes():
    assert [r["id"] for r in select_audit_records(RECORDS, "New or changed records")] == [1]
    assert [r["id"] for r in select_audit_records(RECORDS, "Failed records only")] == [2]
    assert [r["id"] for r in select_audit_records(RECORDS, "Review records only")] == [3]
    assert [r["id"] for r in select_audit_records(RECORDS, "One university", university="U2")] == [3, 4]
    assert [r["id"] for r in select_audit_records(RECORDS, "Selected professors", selected_ids={2, 4})] == [2, 4]


def test_audit_scope_limit_prioritizes_failed_records():
    chosen = select_audit_records(RECORDS, "All records", limit=2)
    assert [r["id"] for r in chosen] == [2, 1]


def test_admin_password_plain_and_hash():
    digest = hash_password("secret")
    assert password_matches("secret", plain="secret")
    assert password_matches("secret", sha256_hash=digest)
    assert not password_matches("wrong", plain="secret")
    assert not password_matches("wrong", sha256_hash=digest)


def test_university_registry_and_department_inference():
    metadata = metadata_for("University of Southern California")
    assert metadata.city == "Los Angeles"
    assert metadata.state == "California"
    assert slugify("Example State University") == "example-state-university"
    assert infer_department_category("Biomedical Data Science") == "Data Science & Statistics"
    assert infer_department_category("Psychology", "computational neuroscience") == "Cognitive Science & Psychology"


def test_ui_filter_helpers_and_topics():
    record = {
        "verification_status": "Review",
        "opportunity_level": "Moderate",
        "ai_categories": "Machine Learning, Healthcare AI",
        "categories": "Artificial Intelligence, Machine Learning",
    }
    assert verification_filter_matches(record, "Verified or review")
    assert not verification_filter_matches(record, "Verified only")
    assert outreach_filter_matches(record, "Moderate or strong")
    assert not outreach_filter_matches(record, "Strong only")
    assert topic_values(record) == ["Machine Learning", "Healthcare AI", "Artificial Intelligence"]


def test_filter_candidates_combines_public_filters():
    from services.ui_helpers import filter_candidates

    records = [
        {
            "id": 1,
            "state": "California",
            "department_category": "Computer Science",
            "ai_categories": "Machine Learning, Healthcare AI",
            "categories": "Artificial Intelligence",
            "opportunity_level": "Moderate",
            "verification_status": "Verified",
        },
        {
            "id": 2,
            "state": "New York",
            "department_category": "Other Research Area",
            "ai_categories": "Theory",
            "categories": "Theory",
            "opportunity_level": "Basic",
            "verification_status": "Review",
        },
    ]
    filtered = filter_candidates(
        records,
        state_filter="California",
        department_filter="Computer Science",
        topic_filters=["Healthcare AI"],
        outreach_filter="Moderate or strong",
        verification_filter="Verified only",
    )
    assert [record["id"] for record in filtered] == [1]


def test_resolve_search_query_uses_typed_text_first():
    assert resolve_search_query("  AI for healthcare  ", ["Artificial Intelligence"]) == "AI for healthcare"


def test_resolve_search_query_uses_selected_topics_when_text_is_empty():
    assert resolve_search_query("", ["Artificial Intelligence", "Machine Learning"]) == "Artificial Intelligence, Machine Learning"
    assert resolve_search_query("   ", ["Artificial Intelligence", "Artificial Intelligence"]) == "Artificial Intelligence"
    assert resolve_search_query("", []) == ""

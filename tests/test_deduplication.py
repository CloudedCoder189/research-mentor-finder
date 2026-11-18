from services.deduplication import deduplicate


def test_duplicate_email_is_removed() -> None:
    records = [
        {"name": "Dr. A", "university": "Example U", "email": "a@example.edu"},
        {"name": "Dr. A", "university": "Example U", "email": "A@example.edu"},
    ]
    assert len(deduplicate(records)) == 1

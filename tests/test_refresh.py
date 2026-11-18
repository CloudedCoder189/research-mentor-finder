from services import refresh as refresh_service


def test_refresh_all_combines_summaries_and_reports_empty(monkeypatch):
    monkeypatch.setattr(
        refresh_service,
        "UNIVERSITY_SCRAPERS",
        {"University A": object, "University B": object},
    )

    def fake_refresh(university, **kwargs):
        if university == "University A":
            return {
                "university": university,
                "scraped": 8,
                "unique": 7,
                "saved": 7,
            }
        return {
            "university": university,
            "scraped": 0,
            "unique": 0,
            "saved": 0,
        }

    monkeypatch.setattr(refresh_service, "refresh_university", fake_refresh)
    summary = refresh_service.refresh_all_universities(max_profiles_per_university=20)

    assert summary["universities_attempted"] == 2
    assert summary["saved"] == 7
    assert summary["completed"] == 1
    assert summary["empty"] == 1
    assert summary["failed"] == 0
    assert len(summary["results"]) == 2


def test_refresh_all_continues_after_one_university_fails(monkeypatch):
    monkeypatch.setattr(
        refresh_service,
        "UNIVERSITY_SCRAPERS",
        {"Broken University": object, "Working University": object},
    )

    attempted = []

    def fake_refresh(university, **kwargs):
        attempted.append(university)
        if university == "Broken University":
            raise RuntimeError("layout changed")
        return {
            "university": university,
            "scraped": 4,
            "unique": 4,
            "saved": 4,
        }

    monkeypatch.setattr(refresh_service, "refresh_university", fake_refresh)
    summary = refresh_service.refresh_all_universities()

    assert attempted == ["Broken University", "Working University"]
    assert summary["failed"] == 1
    assert summary["completed"] == 1
    assert summary["saved"] == 4
    assert summary["results"][0]["status"] == "Failed"
    assert summary["results"][1]["status"] == "Completed"


def _fake_record(index: int, university: str):
    from scrapers.base import ScrapedProfessor

    return ScrapedProfessor(
        name=f"Professor {index}",
        university=university,
        department="Computer Science",
        title="Professor",
        research_interests="Machine learning",
        email=f"person{index}@example.edu",
        profile_url=f"https://example.edu/people/{index}",
    )


def test_full_authoritative_refresh_prunes_only_after_safe_roster(monkeypatch):
    university = "Example University"

    class FakeScraper:
        authoritative_roster = True
        minimum_authoritative_records = 2

        def __init__(self, max_profiles=None, progress_callback=None):
            self.max_profiles = max_profiles
            self.last_error = ""

        def safe_scrape(self):
            return [_fake_record(index, university) for index in range(3)]

    monkeypatch.setattr(refresh_service, "UNIVERSITY_SCRAPERS", {university: FakeScraper})
    monkeypatch.setattr(refresh_service, "delete_demo_records", lambda: None)
    monkeypatch.setattr(refresh_service, "upsert_professors", lambda rows: len(rows))
    calls = []
    monkeypatch.setattr(
        refresh_service,
        "prune_university_records",
        lambda name, emails: calls.append((name, list(emails))) or 4,
    )

    summary = refresh_service.refresh_university(university, max_profiles=None)
    assert summary["saved"] == 3
    assert summary["pruned"] == 4
    assert calls and calls[0][0] == university
    assert len(calls[0][1]) == 3


def test_small_authoritative_refresh_never_prunes(monkeypatch):
    university = "Example University"

    class FakeScraper:
        authoritative_roster = True
        minimum_authoritative_records = 2

        def __init__(self, max_profiles=None, progress_callback=None):
            self.last_error = ""

        def safe_scrape(self):
            return [_fake_record(index, university) for index in range(2)]

    monkeypatch.setattr(refresh_service, "UNIVERSITY_SCRAPERS", {university: FakeScraper})
    monkeypatch.setattr(refresh_service, "delete_demo_records", lambda: None)
    monkeypatch.setattr(refresh_service, "upsert_professors", lambda rows: len(rows))
    monkeypatch.setattr(
        refresh_service,
        "prune_university_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not prune")),
    )

    summary = refresh_service.refresh_university(university, max_profiles=2)
    assert summary["saved"] == 2
    assert summary["pruned"] == 0


def test_short_full_roster_skips_destructive_cleanup(monkeypatch):
    university = "Example University"

    class FakeScraper:
        authoritative_roster = True
        minimum_authoritative_records = 5

        def __init__(self, max_profiles=None, progress_callback=None):
            self.last_error = ""

        def safe_scrape(self):
            return [_fake_record(index, university) for index in range(2)]

    monkeypatch.setattr(refresh_service, "UNIVERSITY_SCRAPERS", {university: FakeScraper})
    monkeypatch.setattr(refresh_service, "delete_demo_records", lambda: None)
    monkeypatch.setattr(refresh_service, "upsert_professors", lambda rows: len(rows))
    monkeypatch.setattr(
        refresh_service,
        "prune_university_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not prune")),
    )

    summary = refresh_service.refresh_university(university, max_profiles=None)
    assert summary["pruned"] == 0
    assert "cleanup was skipped" in summary["error"].casefold()

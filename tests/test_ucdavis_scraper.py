from scrapers.ucdavis import (
    UCDavisDirectoryEntry,
    parse_ucdavis_faculty_directory_html,
    parse_ucdavis_profile_html,
)


def test_uc_davis_sitefarm_directory_parser_uses_profile_links():
    html = """
    <div class='views-row'><h3><a href='/directory/hao-chen'>Hao Chen</a></h3>
    <ul><li>Professor</li><li>Computer Science</li>
    <li><a href='mailto:chen@ucdavis.edu'>chen@ucdavis.edu</a></li>
    <li><a href='https://web.cs.ucdavis.edu/~chen/'>Personal Site</a></li></ul></div>
    <div class='views-row'><h3><a href='/directory/muhao-chen'>Muhao Chen</a></h3>
    <p>Associate Professor</p><a href='mailto:muhchen@ucdavis.edu'>Email</a></div>
    """
    rows = parse_ucdavis_faculty_directory_html(html)
    assert [row.name for row in rows] == ["Hao Chen", "Muhao Chen"]
    assert rows[0].email == "chen@ucdavis.edu"
    assert rows[0].profile_url.endswith("/directory/hao-chen")
    assert rows[0].website_url == "https://web.cs.ucdavis.edu/~chen/"


def test_uc_davis_profile_parser_extracts_position_bio_email_and_site():
    html = """
    <main><h1>Hao Chen</h1>
    <h2>Position Title</h2><div>Professor</div><ul><li>Computer Science</li></ul>
    <a href='mailto:chen@ucdavis.edu'>chen@ucdavis.edu</a>
    <a href='https://web.cs.ucdavis.edu/~chen/'>Personal Site</a>
    <h2>Bio</h2><h5>Security, machine learning, software engineering</h5>
    <p>His group applies statistical machine learning to security and program analysis.</p>
    <h2>Tags</h2></main>
    """
    fallback = UCDavisDirectoryEntry("Hao Chen", "https://cs.ucdavis.edu/directory/hao-chen")
    row, research, _ = parse_ucdavis_profile_html(html, fallback.profile_url, fallback)
    assert row.title == "Professor"
    assert row.email == "chen@ucdavis.edu"
    assert row.website_url == "https://web.cs.ucdavis.edu/~chen/"
    assert "machine learning" in research.casefold()


def test_uc_davis_directory_reader_falls_back_after_403(monkeypatch):
    import requests
    from bs4 import BeautifulSoup
    from scrapers.ucdavis import DIRECTORY_FALLBACK_URL, FACULTY_URL, UCDavisScraper

    scraper = UCDavisScraper(max_profiles=10, request_delay=0)
    calls = []

    def fake_get_soup(url):
        calls.append(url)
        if url.startswith(FACULTY_URL):
            response = requests.Response()
            response.status_code = 403
            response.url = url
            raise requests.HTTPError("forbidden", response=response)
        return BeautifulSoup("<html><body>fallback</body></html>", "html.parser")

    def fake_browser_get_soup(url):
        # The browser-compatible retry is also rejected, so the scraper moves
        # to the official fallback base instead of hitting the real network.
        response = requests.Response()
        response.status_code = 403
        response.url = url
        raise requests.HTTPError("forbidden", response=response)

    monkeypatch.setattr(scraper, "get_soup", fake_get_soup)
    monkeypatch.setattr(scraper, "_browser_get_soup", fake_browser_get_soup)
    soup, source_url = scraper._read_directory_page(0)
    assert soup.get_text(strip=True) == "fallback"
    assert calls == [FACULTY_URL, DIRECTORY_FALLBACK_URL]
    assert source_url == DIRECTORY_FALLBACK_URL


def test_uc_davis_directory_reader_reuses_working_fallback(monkeypatch):
    from bs4 import BeautifulSoup
    from scrapers.ucdavis import DIRECTORY_FALLBACK_URL, UCDavisScraper

    scraper = UCDavisScraper(max_profiles=10, request_delay=0)
    scraper._working_directory_base = DIRECTORY_FALLBACK_URL
    calls = []

    def fake_get_soup(url):
        calls.append(url)
        return BeautifulSoup("<html><body>page</body></html>", "html.parser")

    monkeypatch.setattr(scraper, "get_soup", fake_get_soup)
    _, source_url = scraper._read_directory_page(2)
    assert calls == [f"{DIRECTORY_FALLBACK_URL}?page=2"]
    assert source_url == f"{DIRECTORY_FALLBACK_URL}?page=2"


def test_uc_davis_403_uses_browser_transport(monkeypatch):
    import requests
    from bs4 import BeautifulSoup
    import scrapers.ucdavis as module
    from scrapers.ucdavis import UCDavisScraper

    scraper = UCDavisScraper(request_delay=0)

    response = requests.Response()
    response.status_code = 403
    response.url = scraper.directory_url

    def blocked(_url):
        raise requests.HTTPError("forbidden", response=response)

    monkeypatch.setattr(scraper, "get_soup", blocked)
    monkeypatch.setattr(
        scraper,
        "_browser_get_soup",
        lambda _url: BeautifulSoup("<html><body>browser ok</body></html>", "html.parser"),
    )
    soup = scraper._resilient_get_soup(scraper.directory_url)
    assert soup.get_text(strip=True) == "browser ok"


def test_ucdavis_scraper_does_not_send_invalid_from_header(monkeypatch):
    from scrapers.ucdavis import UCDavisScraper

    monkeypatch.setenv("SCRAPER_CONTACT_EMAIL", "contact-not-configured")
    scraper = UCDavisScraper(request_delay=0, max_profiles=1)
    assert "From" not in scraper.session.headers


def _cloudflare_encode(email: str, key: int = 0x31) -> str:
    return f"{key:02x}" + "".join(f"{ord(char) ^ key:02x}" for char in email)


def test_uc_davis_directory_parser_decodes_cloudflare_email():
    encoded = _cloudflare_encode("chen@ucdavis.edu")
    html = f"""
    <div class='views-row'><h3><a href='/directory/hao-chen'>Hao Chen</a></h3>
    <ul><li>Professor</li><li>Computer Science</li>
    <li><a href='/cdn-cgi/l/email-protection#{encoded}' data-cfemail='{encoded}'>
    [email protected]</a></li></ul></div>
    """
    rows = parse_ucdavis_faculty_directory_html(html)
    assert len(rows) == 1
    assert rows[0].email == "chen@ucdavis.edu"


def test_uc_davis_profile_parser_decodes_cloudflare_email():
    encoded = _cloudflare_encode("chen@ucdavis.edu")
    html = f"""
    <main><h1>Hao Chen</h1>
    <h2>Position Title</h2><div>Professor</div><ul><li>Computer Science</li></ul>
    <a href='/cdn-cgi/l/email-protection#{encoded}' data-cfemail='{encoded}'>
    [email protected]</a>
    <h2>Bio</h2><p>Research in security and machine learning.</p></main>
    """
    fallback = UCDavisDirectoryEntry("Hao Chen", "https://cs.ucdavis.edu/directory/hao-chen")
    row, _, _ = parse_ucdavis_profile_html(html, fallback.profile_url, fallback)
    assert row.email == "chen@ucdavis.edu"



def test_uc_davis_browser_failure_does_not_poison_official_fallback(monkeypatch):
    import requests
    from bs4 import BeautifulSoup
    from scrapers.ucdavis import DIRECTORY_FALLBACK_URL, FACULTY_URL, UCDavisScraper

    scraper = UCDavisScraper(max_profiles=10, request_delay=0)
    normal_calls = []
    browser_calls = []

    def forbidden(url):
        normal_calls.append(url)
        if url == DIRECTORY_FALLBACK_URL:
            return BeautifulSoup("<html><body>directory fallback</body></html>", "html.parser")
        response = requests.Response()
        response.status_code = 403
        response.url = url
        raise requests.HTTPError("forbidden", response=response)

    def browser_forbidden(url):
        browser_calls.append(url)
        raise requests.RequestException("browser 403")

    monkeypatch.setattr(scraper, "get_soup", forbidden)
    monkeypatch.setattr(scraper, "_browser_get_soup", browser_forbidden)

    soup, source_url = scraper._read_directory_page(0)
    assert soup.get_text(strip=True) == "directory fallback"
    assert source_url == DIRECTORY_FALLBACK_URL
    assert normal_calls == [FACULTY_URL, DIRECTORY_FALLBACK_URL]
    assert browser_calls == [FACULTY_URL]


def test_uc_davis_unfiltered_directory_ignores_non_active_sections():
    html = """
    <h3>Faculty</h3>
    <div><h3><a href='/directory/active-person'>Active Person</a></h3>
    <p>Professor</p><a href='mailto:active@ucdavis.edu'>Email</a></div>
    <h3>Adjunct Faculty</h3>
    <div><h3><a href='/directory/adjunct-person'>Adjunct Person</a></h3>
    <p>Adjunct Professor</p><a href='mailto:adjunct@ucdavis.edu'>Email</a></div>
    <h3>Emeriti Faculty</h3>
    <div><h3><a href='/directory/emeritus-person'>Emeritus Person</a></h3>
    <p>Professor Emeritus</p><a href='mailto:emeritus@ucdavis.edu'>Email</a></div>
    """
    rows = parse_ucdavis_faculty_directory_html(html, "https://cs.ucdavis.edu/directory")
    assert [row.name for row in rows] == ["Active Person"]


def test_uc_davis_official_snapshot_has_current_43_unique_faculty():
    from scrapers.ucdavis_snapshot import UC_DAVIS_FACULTY_SNAPSHOT, snapshot_key

    assert len(UC_DAVIS_FACULTY_SNAPSHOT) == 43
    assert len({snapshot_key(item.name) for item in UC_DAVIS_FACULTY_SNAPSHOT}) == 43
    assert len({item.email.casefold() for item in UC_DAVIS_FACULTY_SNAPSHOT}) == 43
    assert all("@" in item.email for item in UC_DAVIS_FACULTY_SNAPSHOT)


def test_uc_davis_scraper_uses_snapshot_when_live_sources_are_blocked(monkeypatch):
    import requests
    import database
    from scrapers.ucdavis import UCDavisScraper

    scraper = UCDavisScraper(request_delay=0)
    monkeypatch.setattr(
        scraper,
        "_discover_profiles",
        lambda: (_ for _ in ()).throw(requests.RequestException("all official routes returned 403")),
    )
    monkeypatch.setattr(database, "fetch_professors", lambda _university=None: [])

    records = scraper.scrape()
    assert len(records) == 43
    assert records[0].university == "University of California, Davis"
    assert records[0].source_type.startswith("Official UC Davis Computer Science faculty roster snapshot")
    assert "snapshot dated 2026-07-25" in scraper.last_error
    assert "stale-record deletion remains disabled" in scraper.last_error


def test_uc_davis_snapshot_preserves_existing_rich_fields(monkeypatch):
    import database
    from scrapers.ucdavis import UCDavisScraper

    existing = [{
        "name": "Hao Chen",
        "email": "chen@ucdavis.edu",
        "research_interests": "Security, machine learning, and software engineering",
        "website_url": "https://web.cs.ucdavis.edu/~hchen/",
    }]
    monkeypatch.setattr(database, "fetch_professors", lambda _university=None: existing)
    scraper = UCDavisScraper(request_delay=0, max_profiles=2)

    records = scraper._snapshot_records("HTTP 403")
    hao = next(record for record in records if record.name == "Hao Chen")
    assert hao.research_interests == "Security, machine learning, and software engineering"
    assert hao.website_url == "https://web.cs.ucdavis.edu/~hchen/"
    assert len(records) == 2


def test_uc_davis_partial_live_success_merges_to_complete_snapshot(monkeypatch):
    import requests
    import database
    from scrapers.ucdavis import UCDavisDirectoryEntry, UCDavisScraper
    from scrapers.ucdavis_snapshot import UC_DAVIS_FACULTY_SNAPSHOT

    partial_entries = [
        UCDavisDirectoryEntry(
            name=item.name,
            profile_url=item.profile_url,
            title=item.title,
            email=item.email,
            website_url=item.website_url,
        )
        for item in UC_DAVIS_FACULTY_SNAPSHOT[:31]
    ]
    scraper = UCDavisScraper(request_delay=0)
    monkeypatch.setattr(scraper, "_discover_profiles", lambda: partial_entries)
    monkeypatch.setattr(
        scraper,
        "_resilient_get_soup",
        lambda _url: (_ for _ in ()).throw(requests.RequestException("profile blocked")),
    )
    monkeypatch.setattr(database, "fetch_professors", lambda _university=None: [])

    records = scraper.scrape()

    assert len(records) == 43
    assert len({record.email.casefold() for record in records}) == 43
    assert any(record.name == "Yang Zhou" for record in records)
    assert "live access produced 31 of 43" in scraper.last_error
    assert "stale-record deletion remains disabled" in scraper.last_error


def test_uc_davis_snapshot_uses_current_routes_for_recent_faculty():
    from scrapers.ucdavis_snapshot import UC_DAVIS_FACULTY_SNAPSHOT, snapshot_key

    rows = {snapshot_key(row.name): row for row in UC_DAVIS_FACULTY_SNAPSHOT}
    expected = {
        "alexandergamerogarrido": "https://cs.ucdavis.edu/directory/alexander-gamero-garrido-0",
        "amandaraybuck": "https://cs.ucdavis.edu/people/amanda-raybuck",
        "jasperlee": "https://cs.ucdavis.edu/people/jasper-lee",
        "lifuhuang": "https://cs.ucdavis.edu/people/lifu-huang",
        "taptipalit": "https://cs.ucdavis.edu/people/tapti-palit",
        "zhezhao": "https://cs.ucdavis.edu/people/zhe-zhao",
        "iliastagkopoulos": "https://aifs.ucdavis.edu/about/people/ilias-tagkopoulos",
    }
    for key, url in expected.items():
        assert rows[key].profile_url == url
        assert rows[key].research_interests != "Not publicly available"


def test_uc_davis_directory_parser_accepts_people_profile_routes():
    html = """
    <h3>Faculty</h3>
    <div><h3><a href='/people/amanda-raybuck'>Amanda Raybuck</a></h3>
    <p>Assistant Professor</p><a href='mailto:araybuck@ucdavis.edu'>Email</a></div>
    """
    rows = parse_ucdavis_faculty_directory_html(html, "https://cs.ucdavis.edu/directory")
    assert len(rows) == 1
    assert rows[0].profile_url == "https://cs.ucdavis.edu/people/amanda-raybuck"


def test_uc_davis_snapshot_clears_unverifiable_ilias_website_and_uses_official_profile(monkeypatch):
    import database
    from scrapers.ucdavis import UCDavisScraper

    existing = [{
        "name": "Ilias Tagkopoulos",
        "email": "tagkopou@cs.ucdavis.edu",
        "research_interests": "Not publicly available",
        "website_url": "https://tagkopouloslab.ucdavis.edu/",
    }]
    monkeypatch.setattr(database, "fetch_professors", lambda _university=None: existing)
    scraper = UCDavisScraper(request_delay=0)
    records = scraper._snapshot_records("HTTP 403")
    ilias = next(record for record in records if record.name == "Ilias Tagkopoulos")
    assert ilias.website_url == "Not publicly available"
    assert ilias.profile_url == "https://aifs.ucdavis.edu/about/people/ilias-tagkopoulos"
    assert "machine learning" in ilias.research_interests.casefold()


def test_uc_davis_ilias_legacy_cs_page_is_cleared():
    from scrapers.ucdavis import _canonical_profile_url, _prefer_snapshot_website

    assert _prefer_snapshot_website(
        "https://www.cs.ucdavis.edu/~iliast/", "Not publicly available"
    ) == "Not publicly available"
    assert _canonical_profile_url(
        "Ilias Tagkopoulos", "https://cs.ucdavis.edu/directory/ilias-tagkopoulos"
    ) == "https://aifs.ucdavis.edu/about/people/ilias-tagkopoulos"

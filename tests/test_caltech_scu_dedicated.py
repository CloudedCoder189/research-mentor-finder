from bs4 import BeautifulSoup

from scrapers.caltech import (
    CaltechEntry,
    parse_caltech_directory_html,
    parse_caltech_profile_html,
)
from scrapers.scu import SCUEntry, parse_scu_directory_html, parse_scu_profile_html


def test_caltech_official_directory_link_shape_is_discovered():
    html = """
    <section class='faculty-list'>
      <div class='person'>
        <a href='/people/adamw'>Adam Wierman</a>
        <div>Carl F Braun Professor of Computing and Mathematical Sciences</div>
        <a href='https://users.cms.caltech.edu/~adamw/'>Research Website</a>
      </div>
      <div class='person'>
        <a href='/people/gkioxari'>Georgia Gkioxari</a>
        <div>Assistant Professor of Computing and Mathematical Sciences and Electrical Engineering</div>
        <a href='https://gkioxari.github.io'>Research Website</a>
      </div>
      <a href='/people/faculty'>Faculty</a>
    </section>
    """
    rows = parse_caltech_directory_html(html)
    assert [row.name for row in rows] == ["Adam Wierman", "Georgia Gkioxari"]
    assert rows[0].profile_url.endswith("/people/adamw")
    assert rows[0].website_url == "https://users.cms.caltech.edu/~adamw/"
    assert "Professor" in rows[0].title


def test_caltech_profile_ignores_assistant_email_and_extracts_research():
    html = """
    <main>
      <h1>Adam Wierman</h1>
      <a href='https://users.cms.caltech.edu/~adamw/'>Research Website</a>
      <p>Administrative Assistant</p>
      <p>Email: assistant@caltech.edu</p>
      <h5>Carl F Braun Professor of Computing and Mathematical Sciences</h5>
      <h4>Sustainable Computing; Online Learning; Network Economics</h4>
      <h3>Overview</h3>
      <p>Adam Wierman's research develops machine learning and optimization tools for sustainable systems.</p>
    </main>
    """
    fallback = CaltechEntry(
        "Adam Wierman",
        "https://www.cms.caltech.edu/people/adamw",
        website_url="https://users.cms.caltech.edu/~adamw/",
    )
    row, email, research, _ = parse_caltech_profile_html(html, fallback.profile_url, fallback)
    assert row.name == "Adam Wierman"
    assert row.website_url == "https://users.cms.caltech.edu/~adamw/"
    assert email == ""
    assert "machine learning" in research.casefold()


def test_scu_official_faculty_links_are_all_discovered():
    html = """
    <div class='faculty-card'>
      <a href='/engineering/faculty/ling-nam/'>Dr. Nam Ling</a>
      <p>IEEE Fellow, Wilmot J. Nicholson Family Professor</p>
    </div>
    <div class='faculty-card'>
      <a href='/engineering/faculty/ackerman-maya/'>Dr. Maya Ackerman</a>
      <p>Associate Professor</p>
    </div>
    <div class='faculty-card'>
      <span>Ms. Pam Lin</span><p>Academic Department Manager</p>
    </div>
    """
    rows = parse_scu_directory_html(html)
    assert [row.name for row in rows] == ["Maya Ackerman", "Nam Ling"]
    assert rows[0].title == "Associate Professor"
    assert rows[1].profile_url.endswith("/engineering/faculty/ling-nam/")


def test_scu_profile_extracts_public_email_research_and_website():
    html = """
    <main>
      <h1>Nam Ling</h1>
      <p>Wilmot J. Nicholson Family Professor</p>
      <p>Email: <a href='mailto:nling@scu.edu'>nling@scu.edu</a></p>
      <a href='https://videolab.example.edu'>Research Website</a>
      <h2>Research Interests</h2>
      <p>Video coding, computer vision, machine learning, and multimedia systems.</p>
    </main>
    """
    fallback = SCUEntry("Nam Ling", "https://www.scu.edu/engineering/faculty/ling-nam/")
    row, email, website, research, _ = parse_scu_profile_html(html, fallback.profile_url, fallback)
    assert row.title != "Not publicly available"
    assert email == "nling@scu.edu"
    assert website == "https://videolab.example.edu"
    assert "computer vision" in research.casefold()


def test_caltech_profile_accepts_obfuscated_faculty_email_but_not_assistant():
    html = """
    <main>
      <h1>Adam Wierman</h1>
      <h5>Carl F Braun Professor of Computing and Mathematical Sciences</h5>
      <p>Administrative Assistant: helper@caltech.edu</p>
      <p>Contact Adam: adamw at caltech dot edu</p>
      <h3>Overview</h3>
      <p>His research studies optimization and sustainable computing.</p>
    </main>
    """
    fallback = CaltechEntry("Adam Wierman", "https://www.cms.caltech.edu/people/adamw")
    row, email, research, _ = parse_caltech_profile_html(html, fallback.profile_url, fallback)
    assert row.title != "Not publicly available"
    assert email == "adamw@caltech.edu"
    assert "sustainable" in research.casefold()


def test_scu_directory_discovers_image_only_profile_link():
    html = """
    <div class='faculty-card'>
      <h3>Dr. Maya Ackerman</h3>
      <a href='/engineering/faculty/ackerman-maya/'><img alt='Maya Ackerman photo'></a>
      <p>Associate Professor</p>
    </div>
    """
    rows = parse_scu_directory_html(html)
    assert len(rows) == 1
    assert rows[0].name == "Maya Ackerman"
    assert rows[0].title == "Associate Professor"


def test_scu_official_contact_directory_supplies_professor_email():
    from scrapers.scu import parse_scu_contact_directory_html

    html = """
    <article class='person'>
      <h3>Silvia Figueira</h3>
      <p>Chair and Professor</p>
      <a href='/engineering/faculty/figueira-silvia/'>Faculty Profile</a>
      <a href='mailto:sfigueira@scu.edu'>sfigueira@scu.edu</a>
    </article>
    <article class='person'>
      <h3>Pam Lin</h3>
      <p>Academic Department Manager</p>
      <a href='mailto:computerengineering@scu.edu'>Email</a>
    </article>
    """
    rows = parse_scu_contact_directory_html(html)
    assert len(rows) == 1
    assert rows[0].name == "Silvia Figueira"
    assert rows[0].email == "sfigueira@scu.edu"
    assert rows[0].profile_url.endswith("/engineering/faculty/figueira-silvia/")


def test_scu_profile_accepts_explicit_obfuscated_email():
    html = """
    <main>
      <h1>Oana Ignat</h1>
      <p>Assistant Professor</p>
      <p>Email: oignat at scu dot edu</p>
      <p>Research Interests: natural language processing and social computing.</p>
    </main>
    """
    fallback = SCUEntry("Oana Ignat", "https://www.scu.edu/engineering/faculty/ignat-oana/")
    row, email, _, research, _ = parse_scu_profile_html(html, fallback.profile_url, fallback)
    assert row.title == "Assistant Professor"
    assert email == "oignat@scu.edu"
    assert "natural language" in research.casefold()


def test_scu_small_refresh_uses_contact_directory_for_multiple_records(monkeypatch):
    from scrapers.scu import CONTACT_DIRECTORY_URL, DIRECTORY_URL, SCUScraper

    roster = BeautifulSoup(
        """
        <div><h3>Dr. Nam Ling</h3><a href='/engineering/faculty/ling-nam/'>Profile</a><p>Professor</p></div>
        <div><h3>Dr. Maya Ackerman</h3><a href='/engineering/faculty/ackerman-maya/'>Profile</a><p>Associate Professor</p></div>
        """,
        "html.parser",
    )
    contacts = BeautifulSoup(
        """
        <article><h3>Nam Ling</h3><p>Professor</p><a href='mailto:nling@scu.edu'>Email</a></article>
        <article><h3>Maya Ackerman</h3><p>Associate Professor</p><a href='mailto:mackerman@scu.edu'>Email</a></article>
        """,
        "html.parser",
    )
    profile_html = {
        "https://www.scu.edu/engineering/faculty/ling-nam/": "<main><h1>Nam Ling</h1><p>Professor</p><p>Research Interests: video coding and computer vision.</p></main>",
        "https://www.scu.edu/engineering/faculty/ackerman-maya/": "<main><h1>Maya Ackerman</h1><p>Associate Professor</p><p>Research Interests: natural language processing.</p></main>",
    }

    def fake_get_soup(self, url):
        if url == DIRECTORY_URL:
            return roster
        if url == CONTACT_DIRECTORY_URL:
            return contacts
        return BeautifulSoup(profile_html[url], "html.parser")

    monkeypatch.setattr(SCUScraper, "get_soup", fake_get_soup)
    records = SCUScraper(request_delay=0, max_profiles=2).scrape()
    assert len(records) == 2
    assert {record.email for record in records} == {"nling@scu.edu", "mackerman@scu.edu"}


def test_caltech_small_refresh_scans_past_profiles_without_faculty_email(monkeypatch):
    from scrapers.caltech import CaltechScraper, DIRECTORY_URL

    directory = BeautifulSoup(
        """
        <div><a href='/people/alpha'>Alpha Person</a><p>Professor of Computer Science</p><a href='https://alpha.example'>Research Website</a></div>
        <div><a href='/people/beta'>Beta Researcher</a><p>Assistant Professor of Computing and Mathematical Sciences</p><a href='https://beta.example'>Research Website</a></div>
        <div><a href='/people/gamma'>Gamma Scientist</a><p>Associate Professor of Computing and Mathematical Sciences</p><a href='https://gamma.example'>Research Website</a></div>
        """,
        "html.parser",
    )
    pages = {
        "https://www.cms.caltech.edu/people/alpha": "<main><h1>Alpha Person</h1><h5>Professor of Computer Science</h5><p>assistant@caltech.edu</p></main>",
        "https://www.cms.caltech.edu/people/beta": "<main><h1>Beta Researcher</h1><h5>Assistant Professor</h5><a href='https://beta.example'>Research Website</a></main>",
        "https://www.cms.caltech.edu/people/gamma": "<main><h1>Gamma Scientist</h1><h5>Associate Professor</h5><a href='https://gamma.example'>Research Website</a></main>",
        "https://alpha.example": "<p>Administrative Assistant: assistant@caltech.edu</p>",
        "https://beta.example": "<p>Beta Researcher — beta at caltech dot edu</p><p>Research in machine learning.</p>",
        "https://gamma.example": "<p>Gamma Scientist — gamma@caltech.edu</p><p>Research in computer vision.</p>",
    }

    def fake_get_soup(self, url):
        if url == DIRECTORY_URL:
            return directory
        return BeautifulSoup(pages[url], "html.parser")

    monkeypatch.setattr(CaltechScraper, "get_soup", fake_get_soup)
    records = CaltechScraper(request_delay=0, max_profiles=2).scrape()
    assert len(records) == 2
    assert {record.email for record in records} == {"beta@caltech.edu", "gamma@caltech.edu"}


def test_caltech_browser_transport_fallback_does_not_disable_tls(monkeypatch):
    import requests
    from scrapers import caltech

    scraper = caltech.CaltechScraper(request_delay=0)
    monkeypatch.setattr(
        caltech.BaseUniversityScraper,
        "get_soup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.exceptions.SSLError("chain")),
    )

    captured = {}

    class BrowserResponse:
        status_code = 200
        text = "<html><h1>Caltech Lab</h1></html>"

    class BrowserClient:
        @staticmethod
        def get(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return BrowserResponse()

    monkeypatch.setattr(caltech, "curl_requests", BrowserClient)
    soup = scraper.get_soup("http://users.cms.caltech.edu/~example/")
    assert soup.h1.get_text(strip=True) == "Caltech Lab"
    assert captured["url"].startswith("https://")
    assert "verify" not in captured



def test_caltech_legacy_ames_site_uses_current_official_cast_profile():
    from scrapers.caltech import _prefer_https

    assert _prefer_https("http://ames.caltech.edu/") == (
        "https://cast.caltech.edu/people/aaron-ames"
    )


def test_caltech_non_requests_site_error_does_not_abort_refresh(monkeypatch):
    from bs4 import BeautifulSoup
    from scrapers.caltech import CaltechScraper, DIRECTORY_URL

    directory = BeautifulSoup(
        """
        <div><a href='/people/alpha'>Alpha Person</a><p>Professor of Computer Science</p>
        <a href='https://broken.example'>Research Website</a></div>
        <div><a href='/people/beta'>Beta Researcher</a><p>Assistant Professor of Computing and Mathematical Sciences</p>
        <a href='https://beta.example'>Research Website</a></div>
        """,
        "html.parser",
    )
    pages = {
        "https://www.cms.caltech.edu/people/alpha": "<main><h1>Alpha Person</h1><h5>Professor of Computer Science</h5></main>",
        "https://www.cms.caltech.edu/people/beta": "<main><h1>Beta Researcher</h1><h5>Assistant Professor</h5><a href='https://beta.example'>Research Website</a></main>",
        "https://beta.example": "<p>Beta Researcher — beta@caltech.edu</p><p>Machine learning research.</p>",
    }

    class BrowserTransportError(Exception):
        pass

    def fake_get_soup(self, url):
        if url == DIRECTORY_URL:
            return directory
        if url == "https://broken.example":
            raise BrowserTransportError("TLS hostname mismatch")
        return BeautifulSoup(pages[url], "html.parser")

    monkeypatch.setattr(CaltechScraper, "get_soup", fake_get_soup)
    records = CaltechScraper(request_delay=0).scrape()
    assert len(records) == 1
    assert records[0].name == "Beta Researcher"
    assert records[0].email == "beta@caltech.edu"

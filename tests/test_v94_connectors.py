from bs4 import BeautifulSoup

from scrapers.calpoly import CalPolySLOScraper, parse_calpoly_faculty_html
from scrapers.uci import DIRECTORY_URL as UCI_DIRECTORY_URL
from scrapers.uci import UCIScraper, parse_uci_directory_html


def test_uci_parser_accepts_current_query_profiles_and_excludes_later_sections():
    html = """
    <main>
      <h2>Faculty</h2>
      <article><h3>Alex Berg</h3>
        <a href='https://ics.uci.edu/?people=alex-berg'>View Alex Berg</a>
        <p>Associate Professor Computer Science</p>
        <a href='mailto:bergac@uci.edu'>bergac@uci.edu</a>
      </article>
      <article><h3>Elaheh (Eli) Bozorgzadeh</h3>
        <a href='/people/elaheh-bozorgzadeh/'>View Elaheh Bozorgzadeh</a>
        <p>Professor Computer Science</p>
        <a href='mailto:eli@ics.uci.edu'>eli@ics.uci.edu</a>
      </article>
      <article><h3>Michael Carey</h3>
        <a href='https://ics.uci.edu/?people=michael-carey'>View Michael Carey</a>
        <p>Distinguished Professor Emeritus Computer Science</p>
        <a href='mailto:mjcarey@ics.uci.edu'>mjcarey@ics.uci.edu</a>
      </article>
      <h2>Lecturers</h2>
      <article><h3>Shannon Alfaro</h3>
        <a href='https://ics.uci.edu/?people=shannon-alfaro'>View Shannon Alfaro</a>
        <p>Senior Continuing Lecturer Computer Science</p>
        <a href='mailto:alfaro@uci.edu'>alfaro@uci.edu</a>
      </article>
      <h2>Research Scientists and Associates</h2>
      <article><h3>Kareem Ahmed</h3>
        <a href='https://ics.uci.edu/?people=kareem-ahmed'>View Kareem Ahmed</a>
        <p>Postdoctoral Scholar Computer Science</p>
        <a href='mailto:ahmedky@uci.edu'>ahmedky@uci.edu</a>
      </article>
    </main>
    """
    rows = parse_uci_directory_html(html)
    assert [row.name for row in rows] == ["Alex Berg", "Elaheh (Eli) Bozorgzadeh"]
    assert rows[0].profile_url == "https://ics.uci.edu/?people=alex-berg"
    assert rows[1].profile_url.endswith("/people/elaheh-bozorgzadeh/")


def test_uci_small_refresh_saves_official_profiles(monkeypatch):
    directory = BeautifulSoup(
        """
        <h2>Faculty</h2>
        <article><h3>Alex Berg</h3><a href='https://ics.uci.edu/?people=alex-berg'>View Alex Berg</a>
          <p>Associate Professor Computer Science</p><a href='mailto:bergac@uci.edu'>Email</a></article>
        <article><h3>Judy Hoffman</h3><a href='https://ics.uci.edu/?people=judy-hoffman'>View Judy Hoffman</a>
          <p>Associate Professor Computer Science</p><a href='mailto:judy.hoffman@uci.edu'>Email</a></article>
        <h2>Lecturers</h2>
        """,
        "html.parser",
    )
    pages = {
        "https://ics.uci.edu/?people=alex-berg": """
          <main><h1>Alex Berg</h1><p>Associate Professor</p><p>bergac@uci.edu</p>
          <a href='https://acberg.com'>Website</a>
          <p>Berg's research concerns machine learning for computational visual recognition.</p></main>""",
        "https://ics.uci.edu/?people=judy-hoffman": """
          <main><h1>Judy Hoffman</h1><p>Associate Professor</p><p>judy.hoffman@uci.edu</p>
          <p>Her research studies computer vision and domain adaptation.</p></main>""",
    }

    def fake_get_soup(self, url):
        if url == UCI_DIRECTORY_URL:
            return directory
        return BeautifulSoup(pages[url], "html.parser")

    monkeypatch.setattr(UCIScraper, "get_soup", fake_get_soup)
    records = UCIScraper(request_delay=0, max_profiles=2).scrape()
    assert len(records) == 2
    assert {record.email for record in records} == {
        "bergac@uci.edu",
        "judy.hoffman@uci.edu",
    }
    assert all("?people=" in record.profile_url for record in records)
    assert any("visual recognition" in record.research_interests.casefold() for record in records)


def test_calpoly_table_excludes_lecturers_affiliates_emeriti_and_office_hours():
    html = """
    <main>
      <h2>Faculty</h2>
      <table>
        <tr><th>Name</th><th>Title</th><th>Email</th><th>Office</th><th>Research Interests</th></tr>
        <tr><td><a href='https://ayaankazerouni.github.io'>Ayaan Kazerouni</a></td>
          <td>Assistant Professor</td><td><a href='mailto:ayaank@calpoly.edu'>ayaank@calpoly.edu</a></td>
          <td>14-229</td><td>Computing Education, Software Engineering, Software Testing</td></tr>
        <tr><td>Bret Hartman</td><td>Lecturer</td><td>bahartma@calpoly.edu</td><td>14-240</td><td></td></tr>
      </table>
      <h2>Affiliated Faculty</h2>
      <table><tr><th>Name</th><th>Title</th><th>Email</th></tr>
        <tr><td>Ava Wright</td><td>Professor – Philosophy</td><td>avwright@calpoly.edu</td></tr></table>
      <h2>Active Emeriti</h2>
      <table><tr><th>Name</th><th>Title</th><th>Email</th></tr>
        <tr><td>Old Professor</td><td>Professor Emeritus</td><td>old@calpoly.edu</td></tr></table>
      <h2>Faculty Office Hours</h2>
      <table><tr><th>Name</th><th>Email</th><th>Hours</th></tr>
        <tr><td>Ayaan Kazerouni</td><td>ayaank@calpoly.edu</td><td>Monday</td></tr></table>
    </main>
    """
    rows = parse_calpoly_faculty_html(html)
    assert len(rows) == 1
    assert rows[0].name == "Ayaan Kazerouni"
    assert rows[0].email == "ayaank@calpoly.edu"
    assert rows[0].website_url == "https://ayaankazerouni.github.io"
    assert "software testing" in rows[0].research_interests.casefold()


def test_calpoly_flat_card_layout_is_supported_without_affiliate_pollution():
    html = """
    <h2>Faculty</h2>
    <article class='faculty-card'>
      <h3>Borislav Hristov</h3><p>Assistant Professor</p>
      <a href='mailto:bhristov@calpoly.edu'>bhristov@calpoly.edu</a><span>14-115H</span>
      <p>Machine Learning, AI, Bioinformatics, Data Science</p>
    </article>
    <article class='faculty-card'>
      <h3>Brian Jones</h3><p>Lecturer</p>
      <a href='mailto:btjones@calpoly.edu'>btjones@calpoly.edu</a>
    </article>
    <h2>Affiliated Faculty</h2>
    <article><h3>Jean Davidson</h3><p>Professor, Biological Sciences</p>
      <a href='mailto:jdavid06@calpoly.edu'>jdavid06@calpoly.edu</a></article>
    """
    rows = parse_calpoly_faculty_html(html)
    assert len(rows) == 1
    assert rows[0].name == "Borislav Hristov"
    assert "bioinformatics" in rows[0].research_interests.casefold()


def test_calpoly_scraper_uses_official_roster_as_profile(monkeypatch):
    page = BeautifulSoup(
        """
        <h2>Faculty</h2>
        <table><tr><th>Name</th><th>Title</th><th>Email</th><th>Research Interests</th></tr>
        <tr><td>Fahim Khan</td><td>Assistant Professor</td><td>fkhan19@calpoly.edu</td>
        <td>Computer Vision and Applied Machine Learning</td></tr></table>
        <h2>Affiliated Faculty</h2>
        """,
        "html.parser",
    )
    monkeypatch.setattr(CalPolySLOScraper, "get_soup", lambda self, _url: page)
    records = CalPolySLOScraper(request_delay=0, max_profiles=10).scrape()
    assert len(records) == 1
    assert records[0].profile_url == "https://csc.calpoly.edu/faculty/"
    assert records[0].department == "Computer Science and Software Engineering"

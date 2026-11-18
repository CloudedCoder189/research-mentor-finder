from scrapers.calpoly import CalPolySLOScraper, parse_calpoly_faculty_html
from scrapers.caltech import CaltechScraper
from scrapers.configurable import enrich_candidate_from_profile, parse_configurable_directory_html
from scrapers.scu import SCUScraper
from scrapers.sdsu import SDSUScraper
from scrapers.ucdavis import UCDavisScraper
from scrapers.uci import UCIDirectoryEntry, UCIScraper, parse_uci_directory_html, parse_uci_profile_html
from scrapers.ucsb import UCSBScraper
from scrapers.ucsc import UCSCScraper


def test_uc_davis_directory_shape():
    html = """
    <article><h3><a href='/directory/alex-professor'>Alex Professor</a></h3>
    <p>Assistant Professor</p><p>Computer Science</p>
    <a href='mailto:alex@ucdavis.edu'>alex@ucdavis.edu</a>
    <a href='https://alexlab.org'>Personal Site</a></article>
    """
    rows = parse_configurable_directory_html(html, UCDavisScraper.config)
    assert len(rows) == 1
    assert rows[0].email == "alex@ucdavis.edu"
    assert rows[0].website_url == "https://alexlab.org"


def test_uci_directory_and_profile_shape():
    html = """
    <h2>Faculty</h2>
    <div class='person'>
      <h3>Sam Researcher</h3>
      <a href='https://ics.uci.edu/?people=sam-researcher'>View Sam Researcher</a>
      <p>Associate Professor Computer Science</p>
      <a href='mailto:sam@uci.edu'>sam@uci.edu</a>
    </div>
    <h2>Lecturers</h2>
    <div><h3>Lee Lecturer</h3><a href='https://ics.uci.edu/?people=lee'>View Lee Lecturer</a>
      <p>Lecturer Computer Science</p><a href='mailto:lee@uci.edu'>lee@uci.edu</a></div>
    """
    rows = parse_uci_directory_html(html)
    assert len(rows) == 1
    assert rows[0].name == "Sam Researcher"
    assert rows[0].profile_url == "https://ics.uci.edu/?people=sam-researcher"
    profile = """
    <main><h1>Sam Researcher</h1><p>Associate Professor</p>
    <p>sam@uci.edu</p><a href='https://sam.example'>Website</a>
    <p>Sam's research focuses on machine learning systems and network optimization.</p></main>
    """
    enriched, research, website, _ = parse_uci_profile_html(
        profile, rows[0].profile_url, rows[0]
    )
    assert enriched.title == "Associate Professor"
    assert "machine learning" in research.casefold()
    assert website == "https://sam.example"


def test_ucsb_directory_shape():
    html = """
    <section><h2><a href='/people/mira-vision'>Mira Vision</a></h2>
    <p>Associate Professor</p><p>mira@ucsb.edu</p>
    <a href='https://vision-lab.example'>Lab Website</a></section>
    """
    rows = parse_configurable_directory_html(html, UCSBScraper.config)
    assert rows[0].email == "mira@ucsb.edu"
    assert rows[0].title == "Associate Professor"


def test_ucsc_directory_shape():
    html = """
    <article><h3><a href='/people/pat-systems'>Pat Systems</a></h3>
    <dl><dt>Title</dt><dd>Assistant Professor</dd><dt>Campus Email</dt><dd>pat@ucsc.edu</dd></dl></article>
    """
    rows = parse_configurable_directory_html(html, UCSCScraper.config)
    assert rows[0].email == "pat@ucsc.edu"
    assert rows[0].profile_url.endswith('/people/pat-systems')


def test_caltech_directory_can_be_enriched_from_profile():
    html = """
    <article><h3><a href='/people/lee-ai'>Lee AI</a></h3>
    <p>Assistant Professor of Computing and Mathematical Sciences</p>
    <a href='https://lee-ai.example'>Research Website</a></article>
    """
    rows = parse_configurable_directory_html(html, CaltechScraper.config)
    profile = """<main><h1>Lee AI</h1><p>Assistant Professor</p>
    <a href='mailto:lee@caltech.edu'>lee@caltech.edu</a>
    <p>Research focuses on reinforcement learning and control.</p></main>"""
    enriched = enrich_candidate_from_profile(rows[0], profile, rows[0].profile_url, CaltechScraper.config)
    assert enriched.email == "lee@caltech.edu"


def test_scu_directory_can_be_enriched_from_profile():
    html = """
    <article><h3><a href='/engineering/faculty/kim-jordan/'>Dr. Jordan Kim</a></h3>
    <p>Associate Professor</p></article>
    """
    rows = parse_configurable_directory_html(html, SCUScraper.config)
    profile = """<main><h1>Jordan Kim</h1><p>Associate Professor</p>
    <a href='mailto:jkim@scu.edu'>Email</a><a href='https://jordan-lab.example'>Website</a>
    <p>Research focuses on responsible artificial intelligence.</p></main>"""
    enriched = enrich_candidate_from_profile(rows[0], profile, rows[0].profile_url, SCUScraper.config)
    assert enriched.email == "jkim@scu.edu"
    assert enriched.website_url == "https://jordan-lab.example"


def test_cal_poly_table_shape():
    html = """
    <h2>Faculty</h2>
    <table><tr><th>Name</th><th>Title</th><th>Email</th><th>Office</th><th>Research Interests</th></tr>
    <tr><td><a href='https://users.csc.calpoly.edu/~rivera'>Riley Rivera</a></td>
    <td>Assistant Professor</td><td>rivera@calpoly.edu</td><td>14-200</td>
    <td>Computer vision, applied machine learning</td></tr></table>
    <h2>Affiliated Faculty</h2>
    <table><tr><th>Name</th><th>Title</th><th>Email</th></tr>
    <tr><td>Ava Wright</td><td>Professor of Philosophy</td><td>avwright@calpoly.edu</td></tr></table>
    """
    rows = parse_calpoly_faculty_html(html)
    assert len(rows) == 1
    assert rows[0].email == "rivera@calpoly.edu"
    assert "computer vision" in rows[0].research_interests.casefold()


def test_sdsu_directory_and_profile_shape():
    html = """
    <article><h2><a href='/people/taylor-privacy/'>Taylor Privacy, Ph.D.</a></h2>
    <p>Assistant Professor of Computer Science</p>
    <p>Differential Privacy, Privacy in Machine Learning</p></article>
    """
    rows = parse_configurable_directory_html(html, SDSUScraper.config)
    profile = """<main><h1>Taylor Privacy</h1><p>Assistant Professor of Computer Science</p>
    <a href='mailto:tprivacy@sdsu.edu'>Email</a>
    <p>Research focuses on differential privacy and machine learning.</p></main>"""
    enriched = enrich_candidate_from_profile(rows[0], profile, rows[0].profile_url, SDSUScraper.config)
    assert enriched.email == "tprivacy@sdsu.edu"

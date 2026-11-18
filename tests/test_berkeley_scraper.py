from scrapers.berkeley import (
    extract_berkeley_website_url,
    parse_berkeley_directory_html,
)


BERKELEY_FIXTURE = """
<html><body>
<div class="person">
  <h3><a href="/Faculty/Homepages/abbeel.html">Pieter Abbeel</a></h3>
  <p>Professor</p>
  <p>746 Sutardja Dai Hall; pabbeel@cs.berkeley.edu</p>
  <p>Research Interests: <a>Artificial Intelligence (AI)</a>; <a>Control, Intelligent Systems, and Robotics (CIR)</a></p>
  <p>Education: 2008, Ph.D., Computer Science</p>
</div>
<div class="person">
  <h3><a href="/Faculty/Homepages/example.html">Example Person</a></h3>
  <p>Assistant Professor</p>
  <p>example@berkeley.edu</p>
  <p>Research Interests: Machine Learning (ML); Human-Computer Interaction (HCI)</p>
  <p>Assistants: admin@berkeley.edu</p>
</div>
</body></html>
"""


def test_berkeley_parser_extracts_official_fields():
    entries = parse_berkeley_directory_html(BERKELEY_FIXTURE)
    assert len(entries) == 2
    pieter = entries[0]
    assert pieter.name == "Pieter Abbeel"
    assert pieter.title == "Professor"
    assert pieter.email == "pabbeel@cs.berkeley.edu"
    assert "Artificial Intelligence" in pieter.research_interests
    assert "Robotics" in pieter.research_interests
    assert pieter.profile_url.endswith("/Faculty/Homepages/abbeel.html")


def test_berkeley_parser_rejects_admin_email():
    entries = parse_berkeley_directory_html(BERKELEY_FIXTURE)
    example = next(entry for entry in entries if entry.name == "Example Person")
    assert example.email == "example@berkeley.edu"


BERKELEY_PROFILE_FIXTURE = """
<html><body>
  <h1>Alexandre Bayen: Faculty Home Page</h1>
  <h2>Links</h2>
  <a href="https://bayen.berkeley.edu/">Personal Homepage</a>
  <a href="/Pubs/Faculty/bayen.html">Publications</a>
  <h4>Research Centers</h4>
  <a href="https://bair.berkeley.edu/">Berkeley Artificial Intelligence Research Lab (BAIR)</a>
</body></html>
"""


def test_berkeley_profile_prefers_personal_homepage():
    url = extract_berkeley_website_url(
        BERKELEY_PROFILE_FIXTURE,
        "https://www2.eecs.berkeley.edu/Faculty/Homepages/bayen.html",
    )
    assert url == "https://bayen.berkeley.edu/"


def test_berkeley_profile_uses_lab_as_fallback():
    html = """
    <html><body>
      <a href="/Pubs/Faculty/person.html">Publications</a>
      <a href="https://examplelab.berkeley.edu/">Example Research Lab</a>
    </body></html>
    """
    url = extract_berkeley_website_url(
        html,
        "https://www2.eecs.berkeley.edu/Faculty/Homepages/person.html",
    )
    assert url == "https://examplelab.berkeley.edu/"


def test_berkeley_rejects_generic_centers_directory_as_personal_website():
    html = """
    <html><body>
      <a href="https://www2.eecs.berkeley.edu/Research/Areas/Centers/">Website</a>
    </body></html>
    """
    assert extract_berkeley_website_url(
        html,
        "https://www2.eecs.berkeley.edu/Faculty/Homepages/example.html",
    ) == "Not publicly available"

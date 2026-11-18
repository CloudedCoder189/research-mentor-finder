from scrapers.usc import parse_usc_directory_html, parse_usc_profile_html


DIRECTORY_HTML = """
<html><body>
<a href="/directory/faculty/profile/?fname=Mukund&lname=Raghothaman">
  Mukund Raghothaman Associate Professor of Computer Science
</a>
<a href="/directory/faculty/profile/?fname=Maja&lname=Mataric">
  Maja Mataric Chan Soon-Shiong Chair and Distinguished Professor of Computer Science
</a>
</body></html>
"""

PROFILE_HTML = """
<html><body>
<h1>Maja Mataric</h1>
<div>Chan Soon-Shiong Chair and Distinguished Professor of Computer Science</div>
<h2>Biography</h2>
<p>She is the founding director of the USC Robotics and Autonomous Systems Center and directs the Interaction Lab.</p>
<h2>Research Summary</h2>
<p>Research in socially assistive robotics, human-robot interaction, artificial intelligence, and machine learning.</p>
<h2>Appointments</h2>
<ul><li>Thomas Lord Department of Computer Science</li></ul>
<h2>Contact Information</h2>
<p>mataric@usc.edu</p>
<h2>Links</h2>
<a href="https://uscinteractionlab.web.app/">Research Website</a>
<a href="https://scholar.google.com/example">Publications</a>
</body></html>
"""


def test_parse_usc_directory_splits_name_and_title():
    entries = parse_usc_directory_html(DIRECTORY_HTML)
    assert [entry.name for entry in entries] == ["Mukund Raghothaman", "Maja Mataric"]
    assert "Associate Professor" in entries[0].title
    assert "fname=Mukund" in entries[0].profile_url


def test_parse_usc_profile_extracts_research_email_and_lab():
    details = parse_usc_profile_html(
        PROFILE_HTML,
        "https://www.cs.usc.edu/directory/faculty/profile/?fname=Maja&lname=Mataric",
        "Maja Mataric",
        "Professor",
    )
    assert details.email == "mataric@usc.edu"
    assert "socially assistive robotics" in details.research_interests.lower()
    assert details.website_url == "https://uscinteractionlab.web.app/"
    assert details.department == "Computer Science"


def test_usc_prefers_personal_site_and_keeps_research_text_concise():
    long_research = " ".join(
        [
            "I develop human-centered automation systems for robotics and manufacturing.",
            "My group studies physics-informed machine learning and decision support.",
            "We build robotic assistants that learn from human demonstrations.",
            "We also investigate safe planning under uncertainty.",
            "This fifth sentence should not cause the full biography to fill the result card.",
        ]
        * 8
    )
    html = f"""
    <html><body>
    <h1>Satyandra K. Gupta</h1>
    <div>Smith International Professorship in Mechanical Engineering and Professor of Aerospace and Mechanical Engineering and Computer Science</div>
    <h2>Research Summary</h2><p>{long_research}</p>
    <h2>Appointments</h2><ul><li>Thomas Lord Department of Computer Science</li></ul>
    <h2>Contact Information</h2><p>guptask@usc.edu</p>
    <h2>Links</h2>
    <a href="https://cam.usc.edu/">Research Website</a>
    <a href="https://sites.usc.edu/skgupta/">Personal Website</a>
    </body></html>
    """
    details = parse_usc_profile_html(
        html,
        "https://viterbi.usc.edu/directory/faculty/Gupta/Satyandra",
        "Satyandra K. Gupta",
        "Professor",
    )
    assert details.website_url == "https://sites.usc.edu/skgupta/"
    assert len(details.research_interests) <= 760
    assert "human-centered automation" in details.research_interests.lower()


def test_usc_rejects_generic_all_labs_directory_as_personal_website():
    html = """
    <html><body>
      <h1>Example Professor</h1>
      <div>Professor of Computer Science</div>
      <div>example@usc.edu</div>
      <h2>Research Summary</h2><p>Machine learning.</p>
      <a href="https://www.cs.usc.edu/research/research-areas-labs/">Research Website</a>
    </body></html>
    """
    details = parse_usc_profile_html(
        html,
        "https://viterbi.usc.edu/directory/faculty/example",
        "Example Professor",
        "Professor",
    )
    assert details.website_url == "Not publicly available"


def test_usc_replaces_known_retired_wensheng_wu_profile_route():
    html = """
    <html><body>
      <a href='/directory/faculty/profile/?fname=Wensheng&lname=Wu'>
        Wensheng Wu Associate Professor of Computer Science Practice
      </a>
    </body></html>
    """
    entries = parse_usc_directory_html(html)
    assert len(entries) == 1
    assert entries[0].profile_url == "https://viterbi.usc.edu/directory/faculty/Wu/Wensheng"

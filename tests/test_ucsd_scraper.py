from scrapers.ucsd import (
    merge_research_sources,
    parse_ucsd_ai_faculty_html,
    parse_ucsd_directory_html,
    parse_ucsd_nlp_people_html,
    parse_ucsd_profile_html,
    parse_ucsd_robotics_html,
    parse_ucsd_visual_html,
)


DIRECTORY_HTML = """
<html><body>
<a href="/people/faculty-profiles/prithviraj-ammanabrolu"><img alt="Prithviraj Ammanabrolu"></a>
<a href="/people/faculty-profiles/prithviraj-ammanabrolu">Prithviraj Ammanabrolu</a>
<a href="/people/faculty-profiles/manmohan-chandraker">Manmohan Chandraker</a>
<a href="/people/faculty-profiles/faculty">Faculty</a>
</body></html>
"""

PROFILE_HTML = """
<html><body><h1>Prithviraj Ammanabrolu</h1>
<div>prithvi@ucsd.edu</div>
<a href="https://prithvirajva.com/">Website</a>
</body></html>
"""

AI_HTML = """
<html><body><h1>CSE Affiliated AI Faculty</h1>
<h4>Raj Ammanabrolu</h4>
<a href="https://cseweb.ucsd.edu/~kamalika/">Kamalika Chaudhuri</a>
</body></html>
"""

NLP_HTML = """
<html><body><p><a href="https://prithvirajva.com/">Prithviraj Ammanabrolu</a>
is an Assistant Professor in CSE and directs the PEARLS Lab. His research group works at the intersection of NLP, Reinforcement Learning, and Embodied AI.</p></body></html>
"""

ROBOTICS_HTML = """
<html><body>
<h3>Computer Science and Engineering</h3>
<div>Manmohan Chandraker</div>
<div>Computer Science and Engineering Professor</div>
<p>His work focuses on computer vision, 3D scene understanding, autonomous driving, and robotics.</p>
<a href="https://viscomp.ucsd.edu/">Visual Computing Center</a>
<h3>Electrical and Computer Engineering</h3>
</body></html>
"""


ECE_ROBOTICS_HTML = """
<html><body>
<h1>Intelligent Systems, Robotics &amp; Control (Impacted)</h1>
<p>Research builds systems that can sense, reason, decide, and act using machine learning and control.</p>
<h2>Faculty</h2>
<h3>Xiaolong Wang</h3>
<div>Associate Professor</div>
<div>xiw012@ucsd.edu</div>
<a href="https://jacobsschool.ucsd.edu/people/profile/xiaolong-wang">Full Profile</a>
<a href="https://xiaolonw.github.io/">Website</a>
<h3>Michael Yip</h3>
<div>Professor</div>
<div>yip@ucsd.edu</div>
<a href="https://yip.eng.ucsd.edu/">Lab Web</a>
<h2>Adjunct Faculty</h2>
</body></html>
"""

VISUAL_HTML = """
<html><body><h4>Computer Science and Engineering</h4>
<h5><a href="https://cseweb.ucsd.edu/~mkchandraker/">Manmohan Chandraker</a></h5>
<p>Chandraker's research focuses on 3D reconstruction and scene understanding for autonomous driving and robotics.</p>
<h4>Electrical and Computer Engineering</h4>
</body></html>
"""


def test_parse_ucsd_directory_deduplicates_profile_links():
    entries = parse_ucsd_directory_html(DIRECTORY_HTML)
    assert [entry.name for entry in entries] == ["Prithviraj Ammanabrolu", "Manmohan Chandraker"]


def test_parse_ucsd_profile_extracts_email_and_website():
    details = parse_ucsd_profile_html(
        PROFILE_HTML,
        "https://cse.ucsd.edu/people/faculty-profiles/prithviraj-ammanabrolu",
        "Prithviraj Ammanabrolu",
    )
    assert details.email == "prithvi@ucsd.edu"
    assert details.website_url == "https://prithvirajva.com/"


def test_ucsd_research_sources_merge_specific_details():
    ai = parse_ucsd_ai_faculty_html(AI_HTML)
    nlp = parse_ucsd_nlp_people_html(NLP_HTML)
    robotics = parse_ucsd_robotics_html(ROBOTICS_HTML)
    visual = parse_ucsd_visual_html(VISUAL_HTML)
    merged = merge_research_sources(ai, nlp, robotics, visual)

    prithvi = merged["prithvirajammanabrolu"]
    assert any("natural language processing" in item.lower() for item in prithvi.interests)
    assert "assistant professor" in prithvi.title.lower()

    manmohan = merged["manmohanchandraker"]
    joined = " ".join(manmohan.interests).lower()
    assert "computer vision" in joined
    assert "robotics" in joined


def test_parse_current_ucsd_ece_robotics_page():
    robotics = parse_ucsd_robotics_html(
        ECE_ROBOTICS_HTML,
        "https://www.ece.ucsd.edu/faculty-research/ece-research-areas/intelligent-systems-robotics-control-impacted",
    )

    xiaolong = robotics["xiaolongwang"]
    assert "associate professor" in xiaolong.title.lower()
    assert "robotics" in " ".join(xiaolong.interests).lower()
    assert xiaolong.website_url == "https://xiaolonw.github.io/"

    michael = robotics["michaelyip"]
    assert michael.website_url == "https://yip.eng.ucsd.edu/"


def test_ucsd_robotics_rejects_social_profile_as_website():
    html = """
    <html><body>
      <h1>Intelligent Systems, Robotics &amp; Control</h1>
      <p>Robotics and machine learning.</p>
      <h2>Faculty</h2>
      <h3>Example Professor</h3>
      <div>Professor</div>
      <div>example@ucsd.edu</div>
      <a href="https://www.linkedin.com/in/example/">Website</a>
    </body></html>
    """
    robotics = parse_ucsd_robotics_html(html)
    assert robotics["exampleprofessor"].website_url == "Not publicly available"

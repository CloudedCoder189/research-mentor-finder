from pathlib import Path

import pytest

from scrapers.ucla import parse_ucla_profile_html, parse_ucla_research_areas_html


RESEARCH_HTML = """
<html><main>
<h2>Artificial Intelligence</h2>
<p>The computational study of intelligent behavior, machine learning, and language.</p>
<a href="https://samueli.ucla.edu/people/kai-wei-chang/">Kai-Wei Chang</a>
<a href="https://example.org/saadia">Saadia Gabriel</a>
<h2>Graphics &amp; Vision</h2>
<p>Computer vision, image understanding, rendering, and autonomous systems.</p>
<a href="https://samueli.ucla.edu/people/kai-wei-chang/">Kai-Wei Chang</a>
<a href="https://samueli.ucla.edu/people/stefano-soatto/">Stefano Soatto</a>
</main></html>
"""

PROFILE_HTML = """
<html><body>
<h1>Kai-Wei Chang</h1>
<div>PROFESSOR</div><div>COMPUTER SCIENCE</div>
<div>Email: kwchang@cs.ucla.edu</div>
<h3>Websites</h3><a href="https://web.cs.ucla.edu/~kwchang/">Kai-Wei Chang's Website</a>
<h2>RESEARCH AND INTERESTS</h2>
<ul><li>Statistical approaches to natural language processing</li>
<li>Machine learning methods for complex data</li></ul>
<h2>NOTABLE PUBLICATIONS AND BOOKS</h2>
<h2>IN THE NEWS</h2>
<a href="https://www.marktechpost.com/example-ai-news/">Researchers introduce an AI framework</a>
</body></html>
"""


def test_parse_ucla_research_areas_merges_people_across_sections():
    entries = parse_ucla_research_areas_html(RESEARCH_HTML)
    by_name = {entry.name: entry for entry in entries}

    assert set(by_name) == {"Kai-Wei Chang", "Saadia Gabriel", "Stefano Soatto"}
    assert by_name["Kai-Wei Chang"].areas == ["Artificial Intelligence", "Graphics & Vision"]
    assert by_name["Kai-Wei Chang"].profile_url.endswith("/kai-wei-chang/")
    assert by_name["Saadia Gabriel"].website_url == "https://example.org/saadia"


def test_parse_ucla_profile_extracts_public_fields():
    details = parse_ucla_profile_html(
        PROFILE_HTML,
        "https://samueli.ucla.edu/people/kai-wei-chang/",
        "Kai-Wei Chang",
    )

    assert details.title == "Professor"
    assert details.department == "Computer Science"
    assert details.email == "kwchang@cs.ucla.edu"
    assert "natural language processing" in details.research_interests.lower()
    assert details.website_url == "https://web.cs.ucla.edu/~kwchang/"


def test_ucla_profile_never_uses_news_article_as_professor_website():
    html = """
    <html><body>
    <h1>Example Professor</h1>
    <div>PROFESSOR</div><div>COMPUTER SCIENCE</div>
    <div>Email: example@cs.ucla.edu</div>
    <h2>IN THE NEWS</h2>
    <a href="https://www.marktechpost.com/researchers-ai-story/">Researchers publish AI work</a>
    </body></html>
    """
    details = parse_ucla_profile_html(
        html,
        "https://samueli.ucla.edu/people/example-professor/",
        "Example Professor",
    )
    assert details.website_url == "Not publicly available"


def test_ucla_title_can_appear_after_extra_profile_navigation_text():
    filler = "".join(f"<span>Navigation item {i}</span>" for i in range(25))
    html = f"""
    <html><body>
    <h1>Yuchen Cui</h1>
    {filler}
    <div>ASSISTANT PROFESSOR</div><div>COMPUTER SCIENCE</div>
    <div>Email: yuchencui@cs.ucla.edu</div>
    <h2>RESEARCH AND INTERESTS</h2>
    <ul><li>Machine learning</li><li>Human-robot interaction</li></ul>
    </body></html>
    """
    details = parse_ucla_profile_html(
        html,
        "https://samueli.ucla.edu/people/yuchen-cui/",
        "Yuchen Cui",
    )
    assert details.title == "Assistant Professor"


def test_ucla_research_parser_rejects_footer_links_as_people():
    html = """
    <html><body>
      <h2>Artificial Intelligence</h2>
      <p>Machine learning and reasoning.</p>
      <a href="https://samueli.ucla.edu/people/real-professor/">Real Professor</a>
      <a href="/terms/">Terms of Use</a>
      <a href="/privacy/">Privacy Policy</a>
    </body></html>
    """
    entries = parse_ucla_research_areas_html(html)
    assert [entry.name for entry in entries] == ["Real Professor"]


@pytest.mark.parametrize("slug,name,title,topics", [
    ("aditya-grover", "Aditya Grover", "Assistant Professor", ["Probabilistic machine learning", "sequential decision making"]),
    ("kai-wei-chang", "Kai-Wei Chang", "Professor", ["natural language processing", "complex and big data"]),
    ("yuchen-cui", "Yuchen Cui", "Assistant Professor", ["Machine learning", "Human-robot interaction"]),
])
def test_current_ucla_template_ignores_logo_and_navigation(slug, name, title, topics):
    html = (Path(__file__).parent / "fixtures" / "ucla" / f"{slug}.html").read_text(encoding="utf-8")
    details = parse_ucla_profile_html(html, f"https://samueli.ucla.edu/people/{slug}/", name)
    assert details.title == title
    assert details.department == "Computer Science"
    assert all(topic in details.research_interests for topic in topics)
    assert details.website_url != "https://example.org/footer"
    if slug == "aditya-grover":
        assert details.website_url == "https://aditya-grover.github.io/"


@pytest.mark.parametrize("headings", ["<h1>Other Person</h1>", "<h1>Example Person</h1><h1>Example Person</h1>"])
def test_wrong_or_ambiguous_profile_does_not_supply_fields(headings):
    html = f"{headings}<p>Professor</p><p>Computer Science</p><p>person@cs.ucla.edu</p>"
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "Example Person")
    assert details.title == details.department == details.research_interests == "Not publicly available"
    assert details.email == ""


def test_directory_substring_is_not_a_director_appointment():
    html = "<h1>Example Person</h1><div>Expert Directory</div><div>DIRECTOR</div>"
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "Example Person")
    assert details.title == "Director"
    assert details.department == "Not publicly available"


def test_navigation_fields_and_nonresearch_accordions_are_excluded():
    html = """<main><h1>Example Person</h1>
    <nav><p>Bioengineering</p><p>Director</p><p>other@cs.ucla.edu</p></nav>
    <div>Associate Professor</div><div>Computer Science</div>
    <details><summary>Research and Interests</summary><p>Robot learning</p>
      <details><summary>News</summary><p>Unrelated award</p></details></details>
    <details><summary>News</summary><p>Unrelated story</p></details>
    </main><footer><p>other@cs.ucla.edu</p></footer>"""
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "Example Person")
    assert details.title == "Associate Professor"
    assert details.department == "Computer Science"
    assert details.email == ""
    assert details.research_interests == "Robot learning"


def test_missing_name_does_not_treat_logo_as_a_person():
    html = "<h1></h1><p>Expert Directory</p><p>Bioengineering</p>"
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "")
    assert details.title == details.department == "Not publicly available"


def test_fields_after_profile_container_do_not_leak_into_profile():
    html = """<main><h1>Example Person</h1><h2>Research Interests</h2></main>
    <p>Professor</p><p>Bioengineering</p><p>Unrelated external research description</p>"""
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "Example Person")
    assert details.title == details.department == details.research_interests == "Not publicly available"


def test_website_section_cannot_read_link_outside_profile_container():
    html = """<main><h1>Example Person</h1><h3>Websites</h3></main>
    <a href="https://example.org/unrelated">Personal website</a>"""
    details = parse_ucla_profile_html(html, "https://samueli.ucla.edu/people/example/", "Example Person")
    assert details.website_url == "Not publicly available"


@pytest.mark.parametrize("record_id,name,slug,title,department", [
    (129, "Jonathan Kao", "jonathan-kao", "Associate Professor", "Electrical and Computer Engineering; Computer Science"),
    (133, "Nanyun Peng", "nanyun-peng", "Associate Professor", "Computer Science"),
    (135, "Jason (Jinsheng) Cong", "jason-jingsheng-cong", "Distinguished Professor", "Computer Science; Electrical and Computer Engineering"),
    (141, "Hanrui Wang", "hanrui-wang", "Assistant Professor (Starting November 1, 2027)", "Computer Science"),
    (143, "Joseph DiStefano", "joseph-distefano", "Distinguished Professor Emeritus", "Computer Science; Bioengineering"),
    (162, "Tobias Du\u0308rschmid", "tobias-d%C3%BCrschmid", "Assistant Teaching Professor", "Computer Science"),
])
def test_reviewed_appointment_edge_cases(record_id, name, slug, title, department):
    html = (Path(__file__).parent / "fixtures/ucla" / f"profile-{record_id}.html").read_text(encoding="utf-8")
    result = parse_ucla_profile_html(html, f"https://samueli.ucla.edu/people/{slug}/", name)
    assert result.title == title
    assert result.department == department


@pytest.mark.parametrize("url", ["https://example.org/people/nanyun-peng/", "https://samueli.ucla.edu/people/wrong-person/"])
def test_reviewed_name_alias_cannot_be_used_on_an_unrelated_page(url):
    html = (Path(__file__).parent / "fixtures/ucla/profile-133.html").read_text(encoding="utf-8")
    result = parse_ucla_profile_html(html, url, "Nanyun Peng")
    assert result.title == result.department == "Not publicly available"


@pytest.mark.parametrize("record_id,name,slug,topic", [
    (152, "Xiang Anthony Chen", "xiang-anthony-chen", "intelligent user interfaces"),
    (162, "Tobias Du\u0308rschmid", "tobias-d%C3%BCrschmid", "Software Engineering and Development"),
])
def test_plain_text_research_accordion(record_id, name, slug, topic):
    html = (Path(__file__).parent / "fixtures/ucla" / f"profile-{record_id}.html").read_text(encoding="utf-8")
    result = parse_ucla_profile_html(html, f"https://samueli.ucla.edu/people/{slug}/", name)
    assert topic in result.research_interests

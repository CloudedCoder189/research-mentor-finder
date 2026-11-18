from scrapers.configurable import (
    FacultyDirectoryConfig,
    enrich_candidate_from_profile,
    parse_configurable_directory_html,
)


def config(**overrides):
    values = dict(
        university_name="Example University",
        directory_url="https://example.edu/faculty",
        department="Computer Science",
        source_type="Official directory",
        expected_email_domains=("example.edu",),
        city="Example City",
        profile_path_hints=("/people/",),
    )
    values.update(overrides)
    return FacultyDirectoryConfig(**values)


def test_table_directory_extracts_contact_and_research():
    html = """
    <table>
      <tr><th>Name</th><th>Title</th><th>Email</th><th>Research Interests</th></tr>
      <tr>
        <td><a href='/people/ada-lovelace'>Ada Lovelace</a></td>
        <td>Associate Professor</td>
        <td><a href='mailto:ada@example.edu'>ada@example.edu</a></td>
        <td>Artificial intelligence, algorithms, and scientific computing</td>
      </tr>
    </table>
    """
    rows = parse_configurable_directory_html(html, config())
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "Ada Lovelace"
    assert row.title == "Associate Professor"
    assert row.email == "ada@example.edu"
    assert "artificial intelligence" in row.research_interests.casefold()
    assert row.profile_url == "https://example.edu/people/ada-lovelace"


def test_card_directory_merges_profile_data():
    directory = """
    <article class='faculty-card'>
      <h3><a href='/people/grace-hopper'>Grace Hopper</a></h3>
      <p>Professor</p>
      <p>Research Interests: Programming languages and compilers</p>
    </article>
    """
    rows = parse_configurable_directory_html(directory, config())
    assert len(rows) == 1
    profile = """
    <html><body>
      <h1>Grace Hopper</h1>
      <p>Professor of Computer Science</p>
      <a href='mailto:grace@example.edu'>Email</a>
      <a href='https://grace-lab.org'>Lab Website</a>
    </body></html>
    """
    enriched = enrich_candidate_from_profile(rows[0], profile, rows[0].profile_url, config())
    assert enriched.email == "grace@example.edu"
    assert enriched.website_url == "https://grace-lab.org"
    assert enriched.research_interests == "Programming languages and compilers"


def test_unrelated_navigation_links_are_not_personal_websites():
    directory = """
    <article>
      <h3><a href='/people/alan-turing'>Alan Turing</a></h3>
      <p>Professor</p>
      <a href='mailto:turing@example.edu'>turing@example.edu</a>
      <a href='/research'>Research</a>
      <a href='https://linkedin.com/in/turing'>Website</a>
    </article>
    """
    rows = parse_configurable_directory_html(directory, config())
    assert len(rows) == 1
    assert rows[0].website_url == "Not publicly available"


def test_new_scrapers_register_with_string_names():
    from scrapers.universities import IMPLEMENTED_SCRAPERS

    assert "University of California, Davis" in IMPLEMENTED_SCRAPERS
    assert "California Institute of Technology" in IMPLEMENTED_SCRAPERS
    assert all(isinstance(name, str) for name in IMPLEMENTED_SCRAPERS)


def test_obfuscated_email_and_strict_person_matching():
    from scrapers.configurable import _obfuscated_email_candidates, _strict_person_email

    candidates = _obfuscated_email_candidates(
        "Ada: ada.lovelace at example dot edu; Office: admin@example.edu"
    )
    assert "ada.lovelace@example.edu" in candidates
    assert _strict_person_email(candidates | {"admin@example.edu"}, "Ada Lovelace", ("example.edu",)) == "ada.lovelace@example.edu"
    assert _strict_person_email({"assistant@example.edu"}, "Ada Lovelace", ("example.edu",)) == ""


def _cloudflare_encode(email: str, key: int = 0x2A) -> str:
    return f"{key:02x}" + "".join(f"{ord(char) ^ key:02x}" for char in email)


def test_cloudflare_protected_email_is_extracted_without_guessing():
    from bs4 import BeautifulSoup
    from scrapers.configurable import _email_candidates

    encoded = _cloudflare_encode("ada.lovelace@example.edu")
    soup = BeautifulSoup(
        f"<a href='/cdn-cgi/l/email-protection#{encoded}' "
        f"data-cfemail='{encoded}'>[email protected]</a>",
        "html.parser",
    )
    assert _email_candidates(soup) == {"ada.lovelace@example.edu"}


def test_profile_ignores_generic_research_centers_and_accepts_named_lab():
    candidate = parse_configurable_directory_html(
        """
        <article>
          <h3><a href='/people/misha-sra'>Misha Sra</a></h3>
          <p>Associate Professor</p>
          <a href='mailto:sra@example.edu'>sra@example.edu</a>
        </article>
        """,
        config(),
    )[0]
    profile = """
    <html><body>
      <h1>Misha Sra</h1>
      <p>Associate Professor sra@example.edu</p>
      <nav><a href='/research/research-centers'>Research Centers</a></nav>
      <a href='https://lab.example.edu/'>Human-AI Experience Lab</a>
    </body></html>
    """
    enriched = enrich_candidate_from_profile(
        candidate,
        profile,
        "https://example.edu/people/misha-sra",
        config(),
    )
    assert enriched.website_url == "https://lab.example.edu/"


def test_profile_does_not_save_generic_research_centers_as_personal_site():
    candidate = parse_configurable_directory_html(
        """
        <article>
          <h3><a href='/people/james-preiss'>James Preiss</a></h3>
          <p>Assistant Professor</p>
          <a href='mailto:james@example.edu'>james@example.edu</a>
        </article>
        """,
        config(),
    )[0]
    profile = """
    <html><body>
      <h1>James Preiss</h1>
      <p>Assistant Professor james@example.edu</p>
      <nav><a href='/index.php/research/research-centers'>Research Centers</a></nav>
    </body></html>
    """
    enriched = enrich_candidate_from_profile(
        candidate,
        profile,
        "https://example.edu/people/james-preiss",
        config(),
    )
    assert enriched.website_url == "Not publicly available"

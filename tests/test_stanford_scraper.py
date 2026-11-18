from scrapers.stanford import (
    choose_professional_email,
    extract_public_emails,
    merge_directory_entries,
    parse_ai_directory_html,
    parse_cs_directory_html,
)


AI_FIXTURE = """
<html><body>
<section>
  <div class="person-card">
    <h3>Stefano Example</h3>
    <p>Probabilistic Reasoning, Machine Learning &amp; Sustainability</p>
    <a href="https://example.stanford.edu/stefano">Read More</a>
  </div>
  <div class="person-card mobile-copy">
    <h3>Stefano Example</h3>
    <p>Probabilistic Reasoning, Machine Learning &amp; Sustainability</p>
    <a href="https://example.stanford.edu/stefano">Read More</a>
  </div>
  <div class="person-card">
    <h3>Chris Sample</h3>
    <p>Natural Language Processing &amp; Deep Learning</p>
    <a href="/chris">Read More</a>
  </div>
</section>
</body></html>
"""

CS_FIXTURE = """
<html><body>
<div class="faculty-card">
  <h3><a href="/people/stefano-example">Stefano Example</a></h3>
  <p>Associate Professor of Computer Science</p>
</div>
<div class="faculty-card">
  <h3><a href="/people/chris-sample">Chris Sample</a></h3>
  <p>Professor of Linguistics and of Computer Science</p>
</div>
</body></html>
"""

PROFILE_FIXTURE = """
<html><body>
<a href="mailto:stefano@example.stanford.edu">Email</a>
<p>Lab coordinator: coordinator@stanford.edu</p>
<p>Alternative: stefano [at] cs [dot] stanford [dot] edu</p>
</body></html>
"""


def test_ai_directory_deduplicates_and_extracts_interests():
    entries = parse_ai_directory_html(AI_FIXTURE)
    assert len(entries) == 2
    first = next(entry for entry in entries if entry.name == "Stefano Example")
    assert "Machine Learning" in first.research_interests
    assert first.website_url == "https://example.stanford.edu/stefano"


def test_cs_directory_and_merge_add_title_and_profile():
    ai_entries = parse_ai_directory_html(AI_FIXTURE)
    cs_entries = parse_cs_directory_html(CS_FIXTURE)
    merged = merge_directory_entries(ai_entries, cs_entries)
    first = next(entry for entry in merged if entry.name == "Stefano Example")
    assert "Associate Professor" in first.title
    assert first.profile_url.endswith("/people/stefano-example")


def test_email_extraction_prefers_person_address():
    emails = extract_public_emails(PROFILE_FIXTURE)
    chosen = choose_professional_email(emails, "Stefano Example")
    assert chosen in {
        "stefano@example.stanford.edu",
        "stefano@cs.stanford.edu",
    }
    assert chosen != "coordinator@stanford.edu"


def test_extract_stanford_academic_website_from_official_profile():
    from scrapers.stanford import extract_stanford_website_url

    html = """
    <html><body>
      <a href="mailto:cbfinn@cs.stanford.edu">Email</a>
      <a href="https://ai.stanford.edu/~cbfinn/">Academic website</a>
      <a href="https://scholar.google.com/example">Google Scholar</a>
    </body></html>
    """
    result = extract_stanford_website_url(
        html,
        "https://www.cs.stanford.edu/people/chelsea-finn",
        "https://www.cs.stanford.edu/people/chelsea-finn",
    )
    assert result == "https://ai.stanford.edu/~cbfinn/"


def test_direct_stanford_tilde_page_is_kept_as_website():
    from scrapers.stanford import extract_stanford_website_url

    result = extract_stanford_website_url(
        "<html><body><p>Personal academic page</p></body></html>",
        "https://ai.stanford.edu/~cbfinn/",
        "https://www.cs.stanford.edu/people/chelsea-finn",
    )
    assert result == "https://ai.stanford.edu/~cbfinn/"


def test_stanford_domain_email_beats_old_institution_email():
    chosen = choose_professional_email(
        ["ebrunskill@cs.cmu.edu", "ebrun@cs.stanford.edu"],
        "Emma Brunskill",
    )
    assert chosen == "ebrun@cs.stanford.edu"


def test_merge_uses_known_official_stanford_profile_and_cleans_title():
    from scrapers.stanford import StanfordDirectoryEntry

    ai_entries = [
        StanfordDirectoryEntry(
            name="Dan Yamins",
            research_interests="AI and neuroscience",
            website_url="https://stanford.edu/~yamins/",
        )
    ]
    cs_entries = {
        "danyamins": StanfordDirectoryEntry(
            name="Dan Yamins",
            title="Associate Professor of Psychology and of Computer Science Stanford University",
            profile_url="https://www.cs.stanford.edu/people/dan-yamins",
        )
    }
    merged = merge_directory_entries(ai_entries, cs_entries)
    assert merged[0].profile_url == "https://profiles.stanford.edu/daniel-yamins"
    assert merged[0].title == "Associate Professor of Psychology and of Computer Science"

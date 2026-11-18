"""Tests for the V9.7 Phase 4 Washington expansion.

Phase 4 adds three non-authoritative Washington scrapers beyond California and
Oregon:

* University of Washington -- Allen School CSE (Elementor profiles), ECE
  (inline ``stafftemplate--entry`` cards), Statistics (profile-followed
  contact tables, read with certificate verification disabled), and the
  Chemistry / Physics / Economics / Biology Drupal people directories
  (``uw.py``);
* Washington State University -- Voiland College EECS (790), MME (793), and
  CEE (788) via the WordPress REST People Directory (``wsu.py``);
* Western Washington University -- CS and ECE Drupal ``div.card`` directory
  views (``wwu.py``).

The tests exercise the offline parse helpers on small HTML/JSON fixtures, the
non-authoritative (no-prune) refresh contract, the canonical-first cross-list
deduplication, and the registration/taxonomy/verification wiring for the three
Washington university registries.
"""

from __future__ import annotations

from scrapers.base import ScrapedProfessor
from scrapers.broadened import combine_broadened
from scrapers.universities import IMPLEMENTED_SCRAPERS
from scrapers.uw import (
    ECE_DIRECTORY_URL,
    UWPerson,
    UW_UNIVERSITY_NAME,
    UWBiologyScraper,
    UWCHeChemistryScraper,
    UWCSEFacultyScraper,
    UWECEfacultyScraper,
    UWEconomicsScraper,
    UWPhysicsScraper,
    UWCStatisticsScraper,
    UniversityOfWashingtonScraper,
    _uw_profile_research,
    extract_cse_slugs,
    extract_stats_people,
    parse_bio_directory,
    parse_cse_profile,
    parse_drupal_people_list,
    parse_ece_directory,
    parse_stats_profile,
)
from scrapers.wsu import (
    WSU_UNIVERSITY_NAME,
    WSUEECSDeptScraper,
    WSUMMEDeptScraper,
    WSUCEEDeptScraper,
    WashingtonStateUniversityScraper,
    keep_wsu_person,
    parse_wsu_person,
)
from scrapers.wwu import (
    WWU_UNIVERSITY_NAME,
    WWUComputerScienceScraper,
    WWUECEScraper,
    WesternWashingtonUniversityScraper,
    keep_wwu_faculty,
    parse_wwu_cards,
)
from services.taxonomy import infer_taxonomy
from services.verification import OFFICIAL_DOMAINS


# ---------- Fixtures ----------


def _cse_roster_page(slugs: list[str]) -> str:
    links = "\n".join(
        f'<a href="https://www.cs.washington.edu/people/faculty/{slug}/">Profile</a>'
        for slug in slugs
    )
    return f"<html><body>{links}</body></html>"


def _cse_profile(
    name: str,
    title: str,
    email: str,
    research: str | None = None,
    website: str | None = None,
) -> str:
    site = (
        f'<a href="{website}">Faculty Webpage</a>' if website else ""
    )
    expertise = (
        f'<div class="elementor-widget-container"><p>Expertise: {research}</p></div>'
        if research
        else ""
    )
    return f"""
    <html><body>
      <h1>Faculty</h1>
      <h2>{name}</h2>
      <h3>{title}</h3>
      {expertise}
      <div class="elementor-widget-container"><p>Email: {email}</p></div>
      {site}
    </body></html>
    """


def _ece_page() -> str:
    return """
    <html><body>
      <div class="stafftemplate--entry">
        <span class="stafftemplate--name">Mary Hayes</span>
        <span class="stafftemplate--title">Associate Professor</span>
        <span class="stafftemplate--interests">Computer Architecture; Accelerators</span>
        <a href="mailto:mhayes@uw.edu">mhayes@uw.edu</a>
      </div>
      <div class="stafftemplate--entry">
        <span class="stafftemplate--name">Tom Nguyen</span>
        <span class="stafftemplate--title">Assistant Professor</span>
        <span class="stafftemplate--interests">Embedded Systems Security</span>
        <a href="mailto:tomnguyen@uw.edu">tomnguyen@uw.edu</a>
      </div>
    </body></html>
    """


def _drupal_people_rows() -> str:
    return """
    <html><body>
      <div class="views-row">
        <div class="views-field views-field-title">
          <a href="/people/dan-rogers">Dan Rogers</a>
        </div>
        <div class="views-field-field-job-title">Professor</div>
        <div class="views-field-field-email"><a href="mailto:droger@uw.edu">droger@uw.edu</a></div>
      </div>
      <div class="views-row">
        <div class="views-field views-field-title">
          <a href="/people/sarah-lin">Sarah Lin</a>
        </div>
        <div class="views-field-field-job-title">Associate Teaching Professor</div>
        <div class="views-field-field-email"><a href="mailto:slin@uw.edu">slin@uw.edu</a></div>
      </div>
    </body></html>
    """


def _bio_card_page() -> str:
    return """
    <html><body>
      <div class="directory-item">
        <a href="/people/anita-chow" class="fakes'class">Anita Chow</a>
        <div class="directory-item__title">Associate Professor</div>
        <div class="directory-item__info"><a href="mailto:anchow@uw.edu">anchow@uw.edu</a></div>
      </div>
      <div class="directory-item">
        <a href="/people/ray-patel">Ray Patel</a>
        <div class="directory-item__title">Lecturer</div>
        <div class="directory-item__info"><a href="mailto:rayp@uw.edu">rayp@uw.edu</a></div>
      </div>
    </body></html>
    """


def _stats_roster() -> str:
    return """
    <html><body>
      <div class="views-element-container">
        <a href="/people/alice-smith" class="fakeimage"><img/></a>
        <a href="/people/alice-smith">Alice Smith</a>
        <a href="/people/bob-jones">Bob Jones</a>
        <a href="/people/emeriti">Emeriti</a>
        <a href="/people/faculty-awards">Awards</a>
      </div>
    </body></html>
    """


def _stats_profile(name: str, title: str, email: str) -> str:
    return f"""
    <html><body>
      <div class="region-content">
        <h1>{name} (she/her)</h1>
        <h3>{title}</h3>
        <table>
          <tr><td><strong>Email</strong></td><td><a href="mailto:{email}">{email}</a></td></tr>
        </table>
        <strong>Bio:</strong> I work on Bayesian statistics and machine learning,
        especially nonparametric methods and network analysis.
        <a href="https://alicesmith.example.com">Homepage</a>
      </div>
    </body></html>
    """


def _wwu_cards() -> str:
    return """
    <html><body>
      <div class="card">
        <h3><a href="/people/lena-kim">Lena Kim, PhD</a></h3>
        <span class="job-title">Associate Professor</span>
        <div class="body"><a href="mailto:lena.kim@wwu.edu">lena.kim@wwu.edu</a></div>
      </div>
      <div class="card">
        <h3><a href="/people/omar-farid">Omar Farid</a></h3>
        <span class="job-title">Assistant Professor</span>
        <div class="body"><a href="mailto:omar.farid@wwu.edu">omar.farid@wwu.edu</a></div>
      </div>
      <div class="card">
        <h3><a href="/directory/paul-ross">Paul Ross</a></h3>
        <span class="job-title">Program Coordinator &amp; Pre-major Advisor</span>
        <div class="body"><a href="mailto:paul.ross@wwu.edu">paul.ross@wwu.edu</a></div>
      </div>
      <div class="card">
        <h3><a href="/directory/kate-meier">Kate Meier</a></h3>
        <span class="job-title">Electronics Technician 4</span>
        <div class="body"><a href="mailto:kate.meier@wwu.edu">kate.meier@wwu.edu</a></div>
      </div>
    </body></html>
    """


def _wsu_item(
    *,
    title: str = "Jane Doe",
    classification: list[int],
    content: str = "",
    email: str = "",
    email_alt: str = "",
    position_title: str = "",
    website: str = "",
    focus: list[str] | None = None,
) -> dict:
    return {
        "title": {"rendered": title, "protected": False},
        "position_title": position_title,
        "classification": classification,
        "email": email,
        "email_alt": email_alt,
        "content": {"rendered": content, "protected": False},
        "link": "https://people.wsu.edu/people/jane-doe",
        "taxonomy_terms": {
            "wsuwp_focus_area": [{"name": name} for name in (focus or [])]
        },
    }


# ---------- University of Washington: parse helpers ----------


def test_uw_cse_slugs_deduped_in_order():
    html = _cse_roster_page(["alice-smith", "bob-jones", "alice-smith", "carol-li"])
    assert extract_cse_slugs(html) == ["alice-smith", "bob-jones", "carol-li"]


def test_uw_cse_profile_parses_email_title_research_website():
    person = parse_cse_profile(
        _cse_profile(
            "Alice Smith",
            "Associate Professor",
            "asmith@cs.washington.edu",
            research="Machine Learning; Natural Language Processing",
            website="https://homes.cs.washington.edu/~asmith/",
        ),
        "https://www.cs.washington.edu/people/faculty/alice-smith/",
    )
    assert person.name == "Alice Smith"
    assert person.title == "Associate Professor"
    assert person.email == "asmith@cs.washington.edu"
    assert "Machine Learning" in person.research_interests
    assert person.website_url == "https://homes.cs.washington.edu/~asmith/"


def test_uw_cse_profile_shared_email_normalized_lowercase():
    person = parse_cse_profile(
        _cse_profile("Bob Jones", "Professor", "bobjones@CS.WASHINGTON.EDU"),
        "https://www.cs.washington.edu/people/faculty/bob-jones/",
    )
    assert person.email == "bobjones@cs.washington.edu"


def test_uw_ece_directory_pairs_email_per_card():
    people = parse_ece_directory(_ece_page(), ECE_DIRECTORY_URL)
    assert len(people) == 2
    mary, tom = people
    assert mary.name == "Mary Hayes"
    assert mary.email == "mhayes@uw.edu"
    assert "Accelerators" in mary.research_interests
    assert tom.name == "Tom Nguyen"
    assert tom.email == "tomnguyen@uw.edu"


def test_uw_drupal_people_list_parses_rows():
    people = parse_drupal_people_list(
        _drupal_people_rows(), "https://phys.washington.edu"
    )
    assert len(people) == 2
    assert people[0].name == "Dan Rogers"
    assert people[0].title == "Professor"
    assert people[0].email == "droger@uw.edu"
    assert people[0].profile_url == "https://phys.washington.edu/people/dan-rogers"
    assert people[1].email == "slin@uw.edu"


def test_uw_bio_directory_parses_cards():
    people = parse_bio_directory(_bio_card_page(), "https://biology.washington.edu")
    assert len(people) == 2
    assert people[0].name == "Anita Chow"
    assert people[0].title == "Associate Professor"
    assert people[0].email == "anchow@uw.edu"
    assert people[0].profile_url == "https://biology.washington.edu/people/anita-chow"


def test_uw_stats_roster_skips_nonperson_slugs():
    people = extract_stats_people(_stats_roster(), "https://stat.washington.edu")
    slugs = [person.slug for person in people]
    assert "alice-smith" in slugs and "bob-jones" in slugs
    assert "emeriti" not in slugs and "faculty-awards" not in slugs


def test_uw_stats_profile_parses_contact_and_bio():
    person = parse_stats_profile(
        _stats_profile("Alice Smith", "Associate Professor", "asmith@uw.edu"),
        UWPerson(
            name="Alice Smith",
            profile_url="https://stat.washington.edu/people/alice-smith",
            slug="alice-smith",
        ),
    )
    assert person.email == "asmith@uw.edu"
    assert person.title == "Associate Professor"
    assert "Bayesian" in person.research_interests
    assert person.website_url == "https://alicesmith.example.com"


def test_uw_profile_research_stops_at_next_section_boundary():
    html = """
    <html><body><article>
      <h3>Fields of Interest</h3>
      <p>Computational Biology Synthetic Biology Systems Biology</p>
      <h3>Biography</h3>
      <p>Dr. Bagheri runs the Bagheri Lab at UW.</p>
    </article></body></html>
    """
    research = _uw_profile_research(html)
    assert "Computational Biology" in research
    assert "Bagheri Lab" not in research


def test_uw_profile_research_never_leaks_email_or_phone():
    html = """
    <html><body><article>
      <h3>Fields of Interest</h3>
      <p>Behavioral Ecology; call 206-555-0100 or email bob@uw.edu for details.</p>
    </article></body></html>
    """
    research = _uw_profile_research(html)
    assert "bob@uw.edu" not in research
    assert "206-555-0100" not in research


def test_uw_cse_scraper_is_never_authoritative():
    for cls in (
        UWCSEFacultyScraper,
        UWECEfacultyScraper,
        UWCStatisticsScraper,
        UWCHeChemistryScraper,
        UWPhysicsScraper,
        UWEconomicsScraper,
        UWBiologyScraper,
        UniversityOfWashingtonScraper,
    ):
        assert cls.authoritative_roster is False


def test_uw_combined_uses_floor_guard_message():
    scraper = UniversityOfWashingtonScraper()
    sub = scraper.sub_scrapers[0]
    assert sub.department == "Computer Science and Engineering"
    assert "at least 60 were expected" in (sub._floor_message(3) or "")
    assert sub._floor_message(91) is None


# ---------- Washington State University ----------


def test_wsu_keep_faculty_classification():
    keep, reason = keep_wsu_person(_wsu_item(classification=[424], position_title="Assistant Professor"))
    assert keep
    assert "faculty" in reason


def test_wsu_keep_career_teaching_track_titles():
    _, reason = keep_wsu_person(
        _wsu_item(classification=[424], position_title="Teaching Professor - Career")
    )
    assert reason == "classification=faculty"


def test_wsu_drop_staff_only():
    keep, reason = keep_wsu_person(
        _wsu_item(classification=[409, 410], position_title="Administrative Professional")
    )
    assert not keep
    assert "staff-only" in reason


def test_wsu_keep_nonstaff_role_by_title():
    keep, reason = keep_wsu_person(
        _wsu_item(classification=[546], position_title="Instructor")
    )
    assert keep
    assert reason == "explicit faculty title"


def test_wsu_keep_prefers_faculty_when_mixed_with_staff():
    keep, _ = keep_wsu_person(_wsu_item(classification=[410, 424], position_title="Staff"))
    assert keep


def test_wsu_parse_extracts_name_email_research():
    person = parse_wsu_person(
        _wsu_item(
            title="Marcus Reyes",
            classification=[424],
            position_title="Assistant Professor",
            email="marcus.reyes@wsu.edu",
            content="<p>Dr. Reyes works on computer vision and medical imaging.</p>",
        )
    )
    assert person.name == "Marcus Reyes"
    assert person.title == "Assistant Professor"
    assert person.email == "marcus.reyes@wsu.edu"
    assert "computer vision" in person.research_interests


def test_wsu_parse_falls_back_to_alt_email_and_focus_areas():
    person = parse_wsu_person(
        _wsu_item(
            title="Nina Patel",
            classification=[424],
            email_alt="nina.patel@wsu.edu",
            content="<p>BIOBLOCK.</p>",
            focus=["Machine Learning", "Computer Vision"],
        )
    )
    assert person.email == "nina.patel@wsu.edu"
    assert "Machine Learning" in person.research_interests


def test_wsu_website_skips_blocklisted_and_directory_hosts():
    person = parse_wsu_person(
        _wsu_item(
            title="Owen Gale",
            classification=[424],
            email="owen.gale@wsu.edu",
            content=(
                '<p><a href="https://scholar.google.com/citations?user=xyz">Scholar</a> '
                '<a href="https://people.wsu.edu/owen-gale">Directory</a> '
                '<a href="https://galesci.github.io">Lab</a></p>'
            ),
        )
    )
    assert person.website_url == "https://galesci.github.io"


def test_wsu_organization_ids_registered():
    assert WSUEECSDeptScraper.organization_id == 790
    assert WSUMMEDeptScraper.organization_id == 793
    assert WSUCEEDeptScraper.organization_id == 788
    for cls in (WSUEECSDeptScraper, WSUMMEDeptScraper, WSUCEEDeptScraper, WashingtonStateUniversityScraper):
        assert cls.authoritative_roster is False


# ---------- Western Washington University ----------


def test_wwu_parse_cards_returns_all_rows_with_emails():
    rows = parse_wwu_cards(_wwu_cards(), "https://cs.wwu.edu")
    assert len(rows) == 4
    assert rows[0][0] == "Lena Kim"
    assert rows[0][1] == "Associate Professor"
    assert rows[0][2] == "lena.kim@wwu.edu"


def test_wwu_keep_faculty_filters_staff_cards():
    rows = parse_wwu_cards(_wwu_cards(), "https://cs.wwu.edu")
    kept = [(name, title) for name, title, _email, _url in rows if keep_wwu_faculty(title)]
    names = {name for name, _title in kept}
    assert names == {"Lena Kim", "Omar Farid"}
    assert not keep_wwu_faculty("Program Coordinator & Pre-major Advisor")
    assert not keep_wwu_faculty("Electronics Technician 4")
    assert keep_wwu_faculty("Teaching Instructor")
    assert keep_wwu_faculty("Lecturer")


def test_wwu_scrapers_never_authoritative():
    for cls in (WWUComputerScienceScraper, WWUECEScraper, WesternWashingtonUniversityScraper):
        assert cls.authoritative_roster is False


# ---------- Canonical-first cross-list deduplication ----------


def _professor(email: str, department: str) -> ScrapedProfessor:
    return ScrapedProfessor(
        name="Cross Listed",
        university="University of Washington",
        department=department,
        title="Professor",
        email=email,
    )


def test_uw_duplicate_email_keeps_canonical_department_first():
    combined = combine_broadened(
        [_professor("shared@uw.edu", "Computer Science and Engineering")],
        [_professor("shared@uw.edu", "Electrical and Computer Engineering")],
    )
    assert len(combined) == 1
    assert combined[0].department == "Computer Science and Engineering"


def test_uw_shared_full_mailbox_email_rejected():
    combined = combine_broadened(
        [_professor("dept@cs.washington.edu", "Computer Science and Engineering")],
        [_professor("office@uw.edu", "Electrical and Computer Engineering")],
    )
    assert combined == []


# ---------- Registration, taxonomy, verification wiring ----------


def test_phase4_universities_registered():
    for name in (UW_UNIVERSITY_NAME, WSU_UNIVERSITY_NAME, WWU_UNIVERSITY_NAME):
        assert name in IMPLEMENTED_SCRAPERS
    assert IMPLEMENTED_SCRAPERS[UW_UNIVERSITY_NAME] is UniversityOfWashingtonScraper
    assert IMPLEMENTED_SCRAPERS[WSU_UNIVERSITY_NAME] is WashingtonStateUniversityScraper
    assert IMPLEMENTED_SCRAPERS[WWU_UNIVERSITY_NAME] is WesternWashingtonUniversityScraper


def test_phase4_university_wrappers_run_canonical_sub_scrapers():
    assert [sub.department for sub in UniversityOfWashingtonScraper().sub_scrapers] == [
        "Computer Science and Engineering",
        "Electrical and Computer Engineering",
        "Statistics",
        "Chemistry",
        "Physics",
        "Economics",
        "Biology",
    ]
    assert [sub.department for sub in WashingtonStateUniversityScraper().sub_scrapers] == [
        "Electrical Engineering and Computer Science",
        "Mechanical and Materials Engineering",
        "Civil and Environmental Engineering",
    ]
    assert [sub.department for sub in WesternWashingtonUniversityScraper().sub_scrapers] == [
        "Computer Science",
        "Electrical and Computer Engineering",
    ]


def test_phase4_verification_domains():
    assert OFFICIAL_DOMAINS[UW_UNIVERSITY_NAME] == ("uw.edu", "washington.edu", "u.washington.edu")
    assert OFFICIAL_DOMAINS[WSU_UNIVERSITY_NAME] == ("wsu.edu",)
    assert OFFICIAL_DOMAINS[WWU_UNIVERSITY_NAME] == ("wwu.edu",)


def test_phase4_taxonomy_mappings():
    assert infer_taxonomy(
        university=UW_UNIVERSITY_NAME,
        department="Computer Science and Engineering",
    )[0:3] == ("College of Engineering", "Engineering & Computing", "Computer Science and Engineering")
    assert infer_taxonomy(
        university=UW_UNIVERSITY_NAME,
        department="Statistics",
    )[0:3] == ("College of Arts and Sciences", "Mathematics & Computing", "Statistics")
    assert infer_taxonomy(
        university=UW_UNIVERSITY_NAME,
        department="Biology",
    )[0:3] == ("College of Arts and Sciences", "Life Sciences", "Biology")
    assert infer_taxonomy(
        university=WSU_UNIVERSITY_NAME,
        department="Electrical Engineering and Computer Science",
    )[0:3] == (
        "Voiland College of Engineering and Architecture",
        "Engineering & Computing",
        "Electrical Engineering and Computer Science",
    )
    assert infer_taxonomy(
        university=WWU_UNIVERSITY_NAME,
        department="Computer Science",
    )[0:3] == ("College of Science and Engineering", "Computing", "Computer Science")


def test_phase4_registry_metadata_state_washington():
    from services.university_registry import UNIVERSITY_REGISTRY, states_for

    for university in (UW_UNIVERSITY_NAME, WSU_UNIVERSITY_NAME, WWU_UNIVERSITY_NAME):
        assert UNIVERSITY_REGISTRY[university].state == "Washington"
    assert "Washington" in states_for()
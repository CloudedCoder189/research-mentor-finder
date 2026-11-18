"""Tests for the V9.7 Phase 3 Oregon expansion.

Phase 3 adds three non-authoritative Oregon scrapers beyond California:

* Oregon State University -- EECS + MIME ``coe-brand-people-card`` rosters
  (``osu.py``), including the ``block_config_key`` pagination key and
  person/email card pairing;
* University of Oregon -- CAS Computer Science + Data Science directories
  (``uo.py``), including the A-Z letter pager and two-field title composition;
* Portland State University -- Maseeh College CS + ECE roster tables (``psu.py``),
  including conservative staff-title filtering.

The tests exercise the offline parse helpers on small HTML fixtures, the
non-authoritative (no-prune) refresh contract, and the registration/taxonomy/
verification wiring for the three university registries.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from scrapers.base import ScrapedProfessor
from scrapers.osu import (
    OSU_BASE_URL,
    OSU_EECS_URL,
    OSU_MIME_URL,
    OSU_UNIVERSITY_NAME,
    OSUEECSScraper,
    OSUMIMEScraper,
    OregonStateUniversityScraper,
    extract_osu_block_config_key,
    parse_osu_directory_page,
    parse_osu_profile_details,
)
from scrapers.psu import (
    PSU_DIRECTORY_URL,
    PSU_UNIVERSITY_NAME,
    PSUComputerScienceScraper,
    PSUElectricalAndComputerEngineeringScraper,
    PortlandStateUniversityScraper,
    keep_psu_faculty,
    parse_psu_directory_page,
    parse_psu_profile_details,
)
from scrapers.universities import IMPLEMENTED_SCRAPERS
from scrapers.uo import (
    UO_CS_DIRECTORY_URL,
    UO_UNIVERSITY_NAME,
    UOComputerScienceScraper,
    UODataScienceScraper,
    UniversityOfOregonScraper,
    compose_uo_title,
    extract_uo_letter_paths,
    parse_uo_listing_page,
    parse_uo_profile_details,
)
from services.taxonomy import infer_taxonomy
from services.verification import OFFICIAL_DOMAINS


def _osu_page(cards: list[str], *, pager: bool = False) -> str:
    """Render a page of ``coe-brand-people-card`` cards for fixture purposes."""
    rows = "\n".join(
        f"""
        <div class="coe-brand-people-card">
          <h2 class="coe-brand-people-card-name">{name}</h2>
          <p class="mb-4-5">{title}</p>
          <p class="coe-brand-people-email-label">Email</p>
          <p class="text-truncate coe-brand-people-email body-small">
            <a href="mailto:{email}">{email}</a>
          </p>
          <a href="/about/people/{slug}">See profile</a>
        </div>
        """
        for name, title, email, slug in cards
    )
    pager_markup = ""
    if pager:
        pager_markup = (
            '<a href="/EECS/About/People?block_config_key='
            'block_11%3Aaabbcc&page=1">Next</a>'
        )
    return f"<html><body>{rows}{pager_markup}</body></html>"


def _osu_profile(research: str | None = None, website: str | None = None) -> str:
    interests = (
        f'<div class="profile-research-interests">'
        f'<div class="field__item"><p>{research}</p></div></div>'
        if research
        else ""
    )
    site = (
        f'<div class="field--name-field-engr-research-website">'
        f'<div class="field__item"><a href="{website}">Lab</a></div></div>'
        if website
        else ""
    )
    return f"<html><body>{interests}{site}</body></html>"


# ---------- OSU directory parsing ----------


def test_osu_directory_page_keeps_person_email_paired():
    html = _osu_page(
        [
            ("Houssam Abbas", "Associate Professor", "houssam.abbas@oregonstate.edu", "houssam-abbas"),
            ("Julie A. Adams", "Professor", "julie.a.adams@oregonstate.edu", "julie-adams"),
        ]
    )
    cards = parse_osu_directory_page(html, OSU_EECS_URL)
    assert len(cards) == 2
    first = cards[0]
    assert first.name == "Houssam Abbas"
    assert first.email == "houssam.abbas@oregonstate.edu"
    assert first.profile_url == f"{OSU_BASE_URL}/about/people/houssam-abbas"


def test_osu_card_title_merges_additional_positions():
    html = _osu_page(
        [
            (
                "Julie A. Adams",
                "Professor | Dean's Professor",
                "julie.a.adams@oregonstate.edu",
                "julie-adams",
            )
        ]
    )
    html = html.replace(
        '<p class="mb-4-5">Professor | Dean\'s Professor</p>',
        '<p class="mb-4-5">Professor | Dean\'s Professor</p>'
        '<p class="mb-4-5">Additional Positions CoRIS Associate Director for Research</p>',
    )
    card = parse_osu_directory_page(html, OSU_EECS_URL)[0]
    assert "Dean's Professor" in card.title
    assert "CoRIS Associate Director for Research" in card.title


def test_osu_card_dropped_without_email():
    html = _osu_page([
        ("No Email", "Program Manager", "", "no-email"),
    ])
    assert parse_osu_directory_page(html, OSU_EECS_URL) == []


def test_osu_block_config_key_extracted_from_pager():
    html = _osu_page([("A Name", "Professor", "a.name@oregonstate.edu", "a-name")], pager=True)
    assert extract_osu_block_config_key(html) == "block_11%3Aaabbcc"


def test_osu_profile_details_research_and_website():
    details = parse_osu_profile_details(
        _osu_profile(
            research="Formal methods, computational ethics, planning.",
            website="http://www.houssamabbas.com/",
        ),
        f"{OSU_BASE_URL}/about/people/houssam-abbas",
    )
    assert "Formal methods" in details.research_interests
    assert details.website_url == "http://www.houssamabbas.com/"


def test_osu_scrapers_are_not_authoritative():
    assert OSUEECSScraper.authoritative_roster is False
    assert OSUMIMEScraper.authoritative_roster is False
    assert OregonStateUniversityScraper.authoritative_roster is False


def test_osu_pagination_reads_extra_pages_and_dedupes(monkeypatch):
    first = _osu_page(
        [
            (f"Person {index}", "Professor", f"p{index}@oregonstate.edu", f"p{index}-slug")
            for index in range(40)
        ],
        pager=True,
    )
    second = _osu_page(
        [
            ("Person 0", "Professor", "p0@oregonstate.edu", "p0-slug"),
            ("Person 40", "Professor", "p40@oregonstate.edu", "p40-slug"),
        ]
    )

    class FakeTransport:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_soup(self, url: str) -> BeautifulSoup:
            self.calls.append(url)
            if url == OSU_EECS_URL:
                content = first
            else:
                content = second
            return BeautifulSoup(content, "html.parser")

    transport = FakeTransport()
    monkeypatch.setattr(OSUEECSScraper, "get_soup", transport.get_soup)
    record = OSUEECSScraper(
        progress_callback=lambda _message: None,
        request_delay=0,
    )
    records = record.scrape()
    assert len(records) == 41  # 40 + "Person 40", with the repeated person deduped
    assert {r.email for r in records} == {
        f"p{index}@oregonstate.edu" for index in range(41)
    }
    assert any("block_config_key=block_11%3Aaabbcc" in url for url in transport.calls)


# ---------- UO directory parsing ----------


def _uo_listing(rows: list[tuple]) -> str:
    entries = "\n".join(
        f"""
        <div class="listing__row">
          <div class="views-field views-field-lname">
            <h2 class="views-field-views-field-lname">
              <a href="/directory/computer-science-faculty/all/{slug}">{name}</a>
            </h2>
          </div>
          <div class="views-field-job-title"><div class="field-content">{title1}</div></div>
          <div class="views-field-job-title2"><div class="field-content">{title2}</div></div>
          <div class="views-field-email"><span class="field-content"><a href="mailto:{email}">{email}</a></span></div>
          <div class="views-field-keywords"><div class="field-content">{keywords}</div></div>
        </div>
        """
        for name, title1, title2, email, keywords, slug in rows
    )
    letters = "".join(
        f'<li class="pager-alphabetical__item"><a href="/directory/computer-science-faculty/{letter}">{letter}</a></li>'
        for letter in "ACM"
    )
    return f"<html><body>{entries}<ul>{letters}</ul></body></html>"


def test_uo_listing_page_extracts_fields():
    html = _uo_listing(
        [
            ("Zena Ariola", "Associate Department Head", "Professor", "ariola@uoregon.edu",
             "Programming Languages, Term Rewriting", "ariola"),
            ("Dan Carrere", "Associate Teaching Professor", "Cybersecurity Faculty", "dcarrere@uoregon.edu",
             "Cybersecurity, Unix Systems", "dcarrere"),
        ]
    )
    entries = parse_uo_listing_page(html, UO_CS_DIRECTORY_URL)
    assert len(entries) == 2
    assert entries[0].email == "ariola@uoregon.edu"
    assert entries[0].profile_url.endswith("/all/ariola")
    assert "Programming Languages" in entries[0].research_interests


def test_uo_letter_paths_deduplicated():
    paths = extract_uo_letter_paths(_uo_listing([]))
    assert paths == [
        "/directory/computer-science-faculty/A",
        "/directory/computer-science-faculty/C",
        "/directory/computer-science-faculty/M",
    ]


def test_uo_title_composition():
    assert (
        compose_uo_title("Professor", "Director of Undergraduate Studies")
        == "Professor | Director of Undergraduate Studies"
    )
    assert compose_uo_title("Director of CIT Minor", "Associate Teaching Professor") == (
        "Associate Teaching Professor | Director of CIT Minor"
    )
    assert compose_uo_title("Associate Teaching Professor", "Cybersecurity Faculty") == (
        "Associate Teaching Professor"
    )
    assert compose_uo_title("Associate Department Head", "Professor") == (
        "Professor | Associate Department Head"
    )


def test_uo_profile_details_email_and_research():
    html = (
        "<html><body>"
        '<a href="mailto:ariola@uoregon.edu">ariola@uoregon.edu</a>'
        "<h2>Research Interests</h2><p>Term rewriting and lambda calculus.</p>"
        "</body></html>"
    )
    details = parse_uo_profile_details(html)
    assert details.email == "ariola@uoregon.edu"
    assert "lambda calculus" in details.research_interests.casefold()


def test_uo_scrapers_are_not_authoritative():
    assert UOComputerScienceScraper.authoritative_roster is False
    assert UODataScienceScraper.authoritative_roster is False
    assert UniversityOfOregonScraper.authoritative_roster is False


# ---------- PSU directory parsing ----------


def _psu_page(rows: list[tuple], section: str = "cs") -> str:
    table = "\n".join(
        f"<tr><td>{name}</td><td>{title}</td><td>{contact}</td></tr>"
        for name, title, contact in rows
    )
    return (
        f"<html><body>"
        f'<p><a id="{section}" href="#{section}">{section.upper()}</a></p>'
        f"<table><tr><th>Name</th><th>Title</th><th>Contact</th></tr>{table}</table>"
        "</body></html>"
    )


def test_psu_staff_title_filter():
    assert keep_psu_faculty("Assistant Professor") is True
    assert keep_psu_faculty("Professor and Chair") is True
    assert keep_psu_faculty("Senior Instructor") is True
    assert keep_psu_faculty("Adjunct Research Professor") is True
    assert keep_psu_faculty("Professor Emeritus") is True
    assert keep_psu_faculty("General Contact") is False
    assert keep_psu_faculty("Graduate Academic Advisor") is False
    assert keep_psu_faculty("Department Manager") is False
    assert keep_psu_faculty("Systems Administrator") is False


def test_psu_directory_table_parsing_and_staff_dropped():
    html = _psu_page(
        [
            ("", "General Contact", 'csoffice@pdx.edu <a href="mailto:csoffice@pdx.edu">link</a>'),
            ("Ameeta Agrawal", "Assistant Professor", '<a href="mailto:ameeta@pdx.edu">ameeta@pdx.edu</a>'),
            ("Ella Barrett", "Graduate Academic Advisor", '<a href="mailto:ebozigar@pdx.edu">ebozigar@pdx.edu</a>'),
        ]
    )
    entries = parse_psu_directory_page(html, "cs", PSU_DIRECTORY_URL)
    assert [entry.name for entry in entries] == ["Ameeta Agrawal", "Ella Barrett"]
    faculty = [entry for entry in entries if keep_psu_faculty(entry.title)]
    assert [entry.name for entry in faculty] == ["Ameeta Agrawal"]


def test_psu_text_only_email_extracted():
    html = _psu_page([("Ada Person", "Professor", "ada@pdx.edu 503-555-1234")])
    entry = parse_psu_directory_page(html, "cs", PSU_DIRECTORY_URL)[0]
    assert entry.email == "ada@pdx.edu"


def test_psu_profile_details_research_from_og_description():
    html = (
        "<html><head><meta property=\"og:description\" content=\"Dr. Ameeta Agrawal is an "
        "Assistant Professor of Computer Science at Portland State University. Dr. Agrawal's "
        "primary areas of research include natural language processing, machine learning, and "
        "computational social science.\" /></head><body>"
        '<h1>Ameeta Agrawal</h1><h2 class="text-lg-white"><span>Assistant Professor</span></h2>'
        '<p><a href="mailto:ameeta@pdx.edu">ameeta@pdx.edu</a></p>'
        "</body></html>"
    )
    details = parse_psu_profile_details(html)
    assert details.email == "ameeta@pdx.edu"
    assert "natural language processing" in details.research_interests.casefold()
    assert details.title == "Assistant Professor"


def test_psu_scrapers_are_not_authoritative():
    assert PSUComputerScienceScraper.authoritative_roster is False
    assert PSUElectricalAndComputerEngineeringScraper.authoritative_roster is False
    assert PortlandStateUniversityScraper.authoritative_roster is False


def test_psu_department_scrapers_have_directory_url():
    assert PSUComputerScienceScraper.directory_url.endswith("directory")
    assert PSUElectricalAndComputerEngineeringScraper.directory_url.endswith("directory")


# ---------- Cross-listed deduplication across departments ----------


def _fake_source(records: list[ScrapedProfessor]):
    class _Source:
        last_error = ""

        def safe_scrape(self) -> list[ScrapedProfessor]:
            return records

    return _Source()


def test_uo_combined_scraper_dedupes_cross_listed_cs_ds(monkeypatch):
    shared_row = ScrapedProfessor(
        name="Same Person",
        university=UO_UNIVERSITY_NAME,
        department="Computer Science",
        title="Professor",
        email="same@uoregon.edu",
    )
    script = UniversityOfOregonScraper()
    monkeypatch.setattr(script, "cs", _fake_source([shared_row]))
    monkeypatch.setattr(
        script,
        "ds",
        _fake_source(
            [
                ScrapedProfessor(
                    name="Same Person",
                    university=UO_UNIVERSITY_NAME,
                    department="Data Science",
                    title="Professor",
                    email="same@uoregon.edu",
                ),
                ScrapedProfessor(
                    name="Only Data Science",
                    university=UO_UNIVERSITY_NAME,
                    department="Data Science",
                    title="Assistant Professor",
                    email="only.ds@uoregon.edu",
                ),
            ]
        ),
    )
    records = script.scrape()
    assert len(records) == 2
    emails = {record.email for record in records}
    assert emails == {"same@uoregon.edu", "only.ds@uoregon.edu"}


def test_osu_combined_scraper_dedupes_cross_listed_eecs_mime(monkeypatch):
    row = ScrapedProfessor(
        name="Joint Person",
        university=OSU_UNIVERSITY_NAME,
        department="Electrical and Computer Engineering",
        title="Professor",
        email="joint@oregonstate.edu",
    )
    script = OregonStateUniversityScraper()
    monkeypatch.setattr(script, "eecs", _fake_source([row]))
    monkeypatch.setattr(
        script,
        "mime",
        _fake_source(
            [
                ScrapedProfessor(
                    name="Joint Person",
                    university=OSU_UNIVERSITY_NAME,
                    department="Mechanical, Industrial, and Manufacturing Engineering",
                    title="Professor",
                    email="joint@oregonstate.edu",
                )
            ]
        ),
    )
    assert len(script.scrape()) == 1


# ---------- Registration, taxonomy, verification wiring ----------


def test_phase3_universities_registered():
    for name in ("Oregon State University", "University of Oregon", "Portland State University"):
        assert name in IMPLEMENTED_SCRAPERS


def test_phase3_verification_domains():
    assert OFFICIAL_DOMAINS["Oregon State University"] == (
        "oregonstate.edu",
        "orst.edu",
        "osucascades.edu",
    )
    assert OFFICIAL_DOMAINS["University of Oregon"] == ("uoregon.edu",)
    assert OFFICIAL_DOMAINS["Portland State University"] == ("pdx.edu",)


def test_phase3_taxonomy_mappings():
    assert infer_taxonomy(
        university="Oregon State University",
        department="Mechanical, Industrial, and Manufacturing Engineering",
    )[0:3] == ("College of Engineering", "Engineering", "Mechanical, Industrial, and Manufacturing Engineering")
    assert infer_taxonomy(
        university="University of Oregon", department="Data Science"
    )[0:3] == ("College of Arts and Sciences", "Computing", "Data Science")
    assert infer_taxonomy(
        university="Portland State University", department="Computer Science"
    )[0:3] == ("Maseeh College of Engineering and Computer Science", "Computing", "Computer Science")


def test_phase3_registry_metadata_state_oregon():
    from services.university_registry import UNIVERSITY_REGISTRY

    for university in ("Oregon State University", "University of Oregon", "Portland State University"):
        assert UNIVERSITY_REGISTRY[university].state == "Oregon"


# ---------- Refresh contract: non-authoritative never prunes ----------


def test_phase3_refresh_never_prunes_unless_authoritative(monkeypatch):
    import services.refresh as refresh_service

    class FakeOregonScraper:
        university_name = "Oregon State University"
        authoritative_roster = False

        def __init__(self, **kwargs) -> None:
            pass

        def safe_scrape(self):
            return [
                ScrapedProfessor(
                    name="Oregon Professor",
                    university="Oregon State University",
                    department="Electrical and Computer Engineering",
                    title="Professor",
                    email="oregon@oregonstate.edu",
                )
            ]

    def fail_prune(*_args, **_kwargs):
        raise AssertionError("non-authoritative scraper must never prune")

    monkeypatch.setattr(refresh_service, "UNIVERSITY_SCRAPERS", {"Oregon State University": FakeOregonScraper})
    monkeypatch.setattr(refresh_service, "delete_demo_records", lambda: None)
    monkeypatch.setattr(refresh_service, "upsert_professors", lambda rows: len(rows))
    monkeypatch.setattr(refresh_service, "prune_university_records", fail_prune)

    summary = refresh_service.refresh_university("Oregon State University")
    assert summary["scraped"] == 1
    assert summary["pruned"] == 0
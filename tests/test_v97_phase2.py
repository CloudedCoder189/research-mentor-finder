"""Tests for the V9.7 Phase 2 expansion.

Phase 2 adds UC Berkeley Electrical Engineering (``berkeley.py``),
UC San Diego Electrical and Computer Engineering (``ucsd_ece.py``) and the
UC Berkeley Department of Statistics (``berkeley_stats.py``), all merged into
the existing broadened wrappers, plus the Statistics taxonomy mapping with the
department-specific school override.
"""

from pathlib import Path

import database
from scrapers.base import ScrapedProfessor
from scrapers.berkeley import BERKELEY_EE_DIRECTORY_URL, BerkeleyEEScraper
from scrapers.berkeley_stats import (
    BERKELEY_STATS_DIRECTORY_URL,
    parse_berkeley_stats_directory_html,
    parse_berkeley_stats_profile_html,
)
from scrapers.broadened import BroadenedBerkeleyScraper, BroadenedUCSDScraper
from scrapers.ucsd_ece import (
    UCSD_ECE_DIRECTORY_URL,
    parse_ucsd_ece_directory_html,
    parse_jacobs_profile_html,
)
from scrapers.universities import IMPLEMENTED_SCRAPERS
from services.taxonomy import (
    NOT_AVAILABLE,
    infer_discipline,
    infer_field,
    infer_taxonomy,
)

_JACOBS_PROFILE = "https://jacobsschool.ucsd.edu/faculty/profile?id=525"


def _record(name, department, email, university="University of California, San Diego"):
    return ScrapedProfessor(
        name=name,
        university=university,
        department=department,
        title="Assistant Professor",
        research_interests="Machine learning and signal processing",
        email=email,
        profile_url="https://example.org/people/placeholder",
    )


# ---------- UCSD ECE directory parsing ----------


ECE_DIRECTORY = """
<html><body>
<a name="main"></a>
<h2>Main Navigation</h2>
<p>About People Research News Events Contact</p>
<h2>Faculty</h2>
<p>Electrical &amp; Computer Engineering faculty directory</p>
<div>
  <h2>Nicholas A. Antipa</h2>
  <p>Assistant Professor, ECE</p>
  <p><a href="mailto:nantipa@ucsd.edu">nantipa@ucsd.edu</a></p>
  <p><a href="http://jacobsschool.ucsd.edu/faculty/faculty_bios/index.sfe?fmp_recid=">Legacy</a>
     <a href="https://jacobsschool.ucsd.edu/faculty/profile?id=525">Full profile</a></p>
</div>
<div>
  <h2>Nikolay A. Atanasov</h2>
  <p><a href="mailto:natanasov@ucsd.edu">Send email</a></p>
  <p><a href="http://jacobsschool.ucsd.edu/faculty/faculty_bios/index.sfe?fmp_recid=409">Profile</a></p>
</div>
<div>
  <h2>Pradeep K. Khosla</h2>
  <p>Chancellor</p>
  <p><a href="mailto:chancellor@ucsd.edu">chancellor@ucsd.edu</a>
     <a href="mailto:pkhosla@ucsd.edu">pkhosla@ucsd.edu</a></p>
  <p><a href="https://jacobsschool.ucsd.edu/faculty/profile?id=525">Full profile</a></p>
</div>
<div>
  <h2>Stay Connected</h2>
  <p><a href="https://twitter.com/ucsdece">Twitter</a>
     <a href="mailto:eceinfo@ucsd.edu">eceinfo@ucsd.edu</a></p>
</div>
<div>
  <h2>Jorge Poveda</h2>
  <p><a href="mailto:jorgedp@ucsd.edu">jorgedp@ucsd.edu</a></p>
  <p><a href="https://poveda.ucsd.edu">Personal site</a></p>
</div>
</body></html>
"""


def test_ucsd_ece_directory_extracts_cards_and_drops_role_mailboxes():
    entries = parse_ucsd_ece_directory_html(ECE_DIRECTORY, UCSD_ECE_DIRECTORY_URL)
    by_name = {entry.name: entry for entry in entries}

    assert "Nicholas A. Antipa" in by_name
    assert "Nikolay A. Atanasov" in by_name
    # Chancellor role mailbox is rejected by the strict last-name matcher when a
    # matching address exists.
    assert "Pradeep K. Khosla" in by_name
    assert by_name["Pradeep K. Khosla"].email == "pkhosla@ucsd.edu"
    # "Stay Connected" is not a person name.
    assert "Stay Connected" not in by_name
    # A person with a directory email but no official profile link is kept;
    # only people with neither email nor profile link are dropped.
    assert by_name["Jorge Poveda"].email == "jorgedp@ucsd.edu"
    assert by_name["Jorge Poveda"].profile_url == "Not publicly available"


def test_ucsd_ece_directory_prefers_modern_profile_link_over_empty_legacy():
    entries = parse_ucsd_ece_directory_html(ECE_DIRECTORY, UCSD_ECE_DIRECTORY_URL)
    antipa = next(e for e in entries if e.name == "Nicholas A. Antipa")
    assert antipa.profile_url == _JACOBS_PROFILE


def test_ucsd_ece_directory_wrong_name_email_skips_person():
    html = """
    <html><body>
    <div>
      <h2>Rookie Researcher</h2>
      <p>PhD student</p>
      <p><a href="mailto:jane.smith@not-specific.edu">jane.smith@not-specific.edu</a></p>
    </div>
    </body></html>
    """
    # An email from outside the expected domain is rejected, so the record is
    # dropped (no email and no official profile link).
    entries = parse_ucsd_ece_directory_html(html, UCSD_ECE_DIRECTORY_URL)
    assert entries == []


# ---------- Jacobs School profile parsing ----------


JACOBS_PROFILE = """
<html><body>
<nav>Skip to main content Search Menu - JSOE About Faculty Profiles</nav>
<main>
  <h1>Faculty Profiles</h1>
  <h3>Nicholas Antipa</h3>
  <p>Assistant Professor, ECE</p>
  <p>Co-design of optical systems and algorithms; computational optical systems</p>
  <hr />
  <h3>Capsule Bio</h3>
  <p>Nicholas Antipa is an Assistant Professor of Electrical and Computer
     Engineering at the University of California San Diego. His research
     group develops computational imaging systems that combine optics,
     algorithms and machine learning.</p>
  <p><a href="mailto:nantipa@ucsd.edu">Email</a></p>
</main>
</body></html>
"""


def test_jacobs_profile_title_and_research_summary():
    profile = parse_jacobs_profile_html(JACOBS_PROFILE, _JACOBS_PROFILE, "Nicholas A. Antipa")
    assert profile.title == "Assistant Professor, ECE"
    assert "Co-design of optical systems and algorithms" in profile.research_interests
    assert "Narrative bio" not in profile.research_interests
    assert profile.email == "nantipa@ucsd.edu"


def test_jacobs_profile_falls_back_when_no_heading_found():
    html = """
    <html><body>
    <main>
      <h1>Faculty Profiles</h1>
      <p>This researcher works on computational photography; their profile
         lacks a name heading but has research sentences.</p>
    </main>
    </body></html>
    """
    profile = parse_jacobs_profile_html(html, _JACOBS_PROFILE, "Somebody Else")
    assert profile.title == "Not publicly available"
    assert "computational photography" in profile.research_interests


# ---------- Berkeley Statistics directory parsing ----------


STATS_DIRECTORY = """
<html><body>
<nav>Statistics Department Berkeley Research People</nav>
<div>
  <h3><a href="/people/ani-adhikari">Ani Adhikari</a></h3>
  <h3><a href="/people/jennifer-chayes">Jennifer Chayes</a></h3>
</div>
<div>
  <h2>Regular Faculty</h2>
  <h3>Our Faculty</h3>
  <p>Researchers across statistical theory.</p>
</div>
<div>
  <h3><a href="/people/students/sam-roe">Sam Roe</a></h3>
  <h3><a href="/people/past/old-pro">Old Pro</a></h3>
</div>
<div>
  <h3><a href="/people/emma-ding">Emma Ding</a></h3>
</div>
</body></html>
"""


def test_stats_directory_keeps_current_faculty_only():
    entries = parse_berkeley_stats_directory_html(STATS_DIRECTORY, BERKELEY_STATS_DIRECTORY_URL)
    names = {entry.name for entry in entries}
    assert names == {"Ani Adhikari", "Jennifer Chayes", "Emma Ding"}
    assert not any("/students/" in entry.profile_url for entry in entries)
    assert not any("/past/" in entry.profile_url for entry in entries)


# ---------- Berkeley Statistics profile parsing ----------


STATS_PROFILE = """
<html><body>
<nav>Skip to main content Berkeley Statistics Research</nav>
<section class="region region-content">
  <article class="node node--type-faculty node--view-mode-full">
    <h1>Emma Ding</h1>
    <div class="field field--name-field-job-title">
      <span class="field__label">Position</span>
      Assistant Professor
    </div>
    <div class="field field--name-field-email">
      <span class="field__label">Email</span>
      email eding@berkeley.edu
    </div>
    <div class="field field--name-field-website">
      <a href="https://emma-ding.github.io">Personal site</a>
    </div>
    <div class="field field--name-field-location">Evans Hall</div>
  </article>
  <div>
    <h2>Research Areas</h2>
    <p>Causal inference, high-dimensional statistics, experimental design.</p>
  </div>
</section>
</body></html>
"""

CONTACT_ONLY_PROFILE = """
<html><body>
<section class="region region-content">
  <article class="node node--type-faculty node--view-mode-full">
    <h1>Ani Adhikari</h1>
    <div class="field field--name-field-job-title">Teaching Professor</div>
    <div class="field field--name-field-email">
      <span class="field__label">Email</span>
      email adhikari@berkeley.edu
    </div>
  </article>
  <p>Office: Evans Hall 456. Office hours by appointment.</p>
</section>
</body></html>
"""


def test_stats_profile_extracts_structured_fields_and_research():
    profile = parse_berkeley_stats_profile_html(
        STATS_PROFILE, "https://statistics.berkeley.edu/people/emma-ding", "Emma Ding"
    )
    assert profile.title == "Assistant Professor"
    assert profile.email == "eding@berkeley.edu"  # bare address, label stripped
    assert profile.website_url == "https://emma-ding.github.io"
    assert "Causal inference" in profile.research_interests


def test_stats_profile_contact_only_has_no_research():
    profile = parse_berkeley_stats_profile_html(
        CONTACT_ONLY_PROFILE,
        "https://statistics.berkeley.edu/people/ani-adhikari",
        "Ani Adhikari",
    )
    assert profile.title == "Teaching Professor"
    assert profile.email == "adhikari@berkeley.edu"
    assert profile.research_interests == "Not publicly available"


# ---------- Broadened wrapper shape and registration ----------


def test_phase2_wrappers_register_and_keep_existing_sources_first():
    berkeley = BroadenedBerkeleyScraper(max_profiles=1)
    assert [s.__class__.__name__ for s in berkeley.sub_scrapers] == [
        "BerkeleyScraper",
        "BerkeleyEEScraper",
        "BerkeleyStatsScraper",
    ]
    assert berkeley.sub_scrapers[0].university_name == "University of California, Berkeley"
    assert berkeley.sub_scrapers[2].university_name == "University of California, Berkeley"
    assert not hasattr(berkeley, "authoritative_roster")

    ucsd = BroadenedUCSDScraper(max_profiles=1)
    assert [s.__class__.__name__ for s in ucsd.sub_scrapers] == [
        "UCSDScraper",
        "UCSDECEScraper",
    ]
    assert ucsd.sub_scrapers[0].university_name == "University of California, San Diego"
    assert ucsd.sub_scrapers[1].university_name == "University of California, San Diego"
    assert not hasattr(ucsd, "authoritative_roster")

    assert IMPLEMENTED_SCRAPERS["University of California, Berkeley"].__name__ == (
        "BroadenedBerkeleyScraper"
    )
    assert IMPLEMENTED_SCRAPERS["University of California, San Diego"].__name__ == (
        "BroadenedUCSDScraper"
    )


def test_berkeley_ee_scraper_configuration():
    assert BERKELEY_EE_DIRECTORY_URL.endswith("/Lists/EE/faculty.html")
    assert BerkeleyEEScraper.department == "Electrical Engineering and Computer Sciences"
    assert "Electrical Engineering" in BerkeleyEEScraper.source_type
    assert BerkeleyEEScraper.university_name == "University of California, Berkeley"


def test_ucsd_ece_scraper_configuration():
    assert UCSD_ECE_DIRECTORY_URL == "https://www.ece.ucsd.edu/people/faculty"


# ---------- Statistics taxonomy with school override ----------


def test_statistics_taxonomy_includes_ls_school_override():
    assert infer_field("Statistics") == "Statistics"
    assert infer_discipline("Statistics") == "Mathematics & Computing"
    school, discipline, field, subfield = infer_taxonomy(
        university="University of California, Berkeley",
        department="Statistics",
        categories="Statistical Methodology, Machine Learning",
    )
    assert school == "College of Letters and Science"
    assert discipline == "Mathematics & Computing"
    assert field == "Statistics"
    assert subfield == "Statistical Methodology"


def test_v97_phase2_backfill_writes_statistics_taxonomy(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        record = _record(
            "Michael Jordan",
            "Statistics",
            "jordan@berkeley.edu",
            university="University of California, Berkeley",
        )
        database.upsert_professors([record.as_record()])
        row = database.fetch_professors()[0]
        assert row["school_or_college"] == "College of Letters and Science"
        assert row["discipline"] == "Mathematics & Computing"
        assert row["field"] == "Statistics"
    finally:
        database.DB_PATH = original


def test_phase2_refresh_keeps_existing_records_and_adds_new(tmp_path: Path, monkeypatch):
    from services import refresh as refresh_service
    from scrapers import broadened as broadened_module

    university = "University of California, San Diego"
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    try:
        existing_cse = _record(
            "Existing CSE Prof", "Computer Science and Engineering", "existing@ucsd.edu"
        )
        database.upsert_professors([existing_cse.as_record()])

        class FakeCSE:
            def __init__(self, request_delay=0.45, timeout=20, max_profiles=None, progress_callback=None):
                self.university_name = university
                self.last_error = ""

            def safe_scrape(self):
                return [
                    existing_cse,
                    _record(
                        "Cross Listed Prof",
                        "Computer Science and Engineering",
                        "cross@ucsd.edu",
                    ),
                ]

        class FakeECE:
            def __init__(self, request_delay=0.45, timeout=20, max_profiles=None, progress_callback=None):
                self.university_name = university
                self.last_error = ""

            def safe_scrape(self):
                return [
                    _record(
                        "Cross Listed Prof",
                        "Electrical and Computer Engineering",
                        "cross@ucsd.edu",
                    ),
                    _record(
                        "New ECE Prof",
                        "Electrical and Computer Engineering",
                        "newece@ucsd.edu",
                    ),
                ]

        monkeypatch.setattr(broadened_module, "UCSDScraper", FakeCSE)
        monkeypatch.setattr(broadened_module, "UCSDECEScraper", FakeECE)
        monkeypatch.setattr(
            refresh_service,
            "UNIVERSITY_SCRAPERS",
            {university: broadened_module.BroadenedUCSDScraper},
        )
        monkeypatch.setattr(refresh_service, "delete_demo_records", lambda: None)
        monkeypatch.setattr(
            refresh_service,
            "prune_university_records",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not prune")),
        )

        summary = refresh_service.refresh_university(university, max_profiles=None)

        assert summary["pruned"] == 0
        assert summary["saved"] == 3
        rows = {str(row["email"]): row for row in database.fetch_professors()}
        assert rows["cross@ucsd.edu"]["department"] == "Computer Science and Engineering"
        assert rows["newece@ucsd.edu"]["department"] == "Electrical and Computer Engineering"
        assert rows["newece@ucsd.edu"]["verification_status"] == "Not checked"
    finally:
        database.DB_PATH = original
from pathlib import Path

import database
from scrapers.base import ScrapedProfessor
from scrapers.broadened import (
    UCSB_ECE_CONFIG,
    UCSC_ECE_CONFIG,
    BroadenedUCSBScraper,
    BroadenedUCSCScraper,
    combine_broadened,
)
from scrapers.universities import IMPLEMENTED_SCRAPERS
from services import refresh as refresh_service
from services.taxonomy import (
    NOT_AVAILABLE,
    infer_discipline,
    infer_field,
    infer_taxonomy,
)


def _record(
    name: str,
    university: str,
    department: str,
    email: str,
    title: str = "Assistant Professor",
) -> ScrapedProfessor:
    return ScrapedProfessor(
        name=name,
        university=university,
        department=department,
        title=title,
        research_interests="Machine learning and signal processing",
        email=email,
        profile_url=f"https://example.org/people/{email.split('@')[0]}",
    )


# ---------- Local combine/cleanup logic ----------


def test_combine_broadened_keeps_existing_department_first_for_cross_listed():
    cross_listed = "Alex Chen"
    ucsc_cs = _record(
        cross_listed,
        "University of California, Santa Cruz",
        "Computer Science and Engineering",
        "achen@ucsc.edu",
    )
    ucsc_ece_same_email = _record(
        cross_listed,
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "achen@ucsc.edu",
    )
    ucsc_ece_new = _record(
        "Priya Rao",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "prao@ucsc.edu",
    )
    ucsc_ece_same_name_other_email = _record(
        "Jordan Lee",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "jlee@ece.ucsc.edu",
    )
    ucsc_cs_same_name_other_email = _record(
        "Jordan Lee",
        "University of California, Santa Cruz",
        "Computer Science and Engineering",
        "jlee@soe.ucsc.edu",
    )

    combined = combine_broadened(
        [ucsc_cs, ucsc_cs_same_name_other_email],
        [ucsc_ece_same_email, ucsc_ece_new, ucsc_ece_same_name_other_email],
    )

    by_email = {record.email: record for record in combined}
    assert len(combined) == 3
    assert by_email["achen@ucsc.edu"].department == "Computer Science and Engineering"
    assert by_email["prao@ucsc.edu"].department == "Electrical and Computer Engineering"
    # Same person, different email, same name+university -> first (CS) wins.
    assert by_email["jlee@soe.ucsc.edu"].department == "Computer Science and Engineering"
    assert "jlee@ece.ucsc.edu" not in by_email


def test_combine_broadened_drops_generic_mailboxes_and_role_card_entries():
    role_card = _record(
        "Undergraduate Director",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "dmilutin@ucsc.edu",
    )
    generic_dept = _record(
        "Elaina A Whelan",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "be-ece-dept-mgmt@ucsc.edu",
        title="Department Manager",
    )
    generic_chair = _record(
        "Marco A Rolandi",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "be-ecechair@ucsc.edu",
        title="Department Chair",
    )
    good = _record(
        "Good Prof",
        "University of California, Santa Cruz",
        "Electrical and Computer Engineering",
        "good@ucsc.edu",
    )

    combined = combine_broadened([role_card, generic_dept, generic_chair, good])

    assert [record.name for record in combined] == ["Good Prof"]


def test_combine_broadened_drops_graduate_advising_role_card():
    advising_role_card = _record(
        "Graduate Advising",
        "University of California, Santa Cruz",
        "Computer Science and Engineering",
        "cm-gradadvising@ucsc.edu",
        title="Director Marcella M Gomez Graduate Student Advisor Jessica Michael",
    )
    advising_role_card_legacy_email = _record(
        "Graduate Advising",
        "University of California, Santa Cruz",
        "Computer Science and Engineering",
        "cse-gradadvising+fernanda@ucsc.edu",
    )
    good = _record(
        "Good Prof",
        "University of California, Santa Cruz",
        "Computer Science and Engineering",
        "good@ucsc.edu",
    )

    combined = combine_broadened(
        [advising_role_card, advising_role_card_legacy_email, good]
    )

    assert [record.name for record in combined] == ["Good Prof"]
    assert combined[0].email == "good@ucsc.edu"


def test_broadened_configs_shape_and_registration():
    assert UCSC_ECE_CONFIG.department == "Electrical and Computer Engineering"
    assert UCSC_ECE_CONFIG.university_name == "University of California, Santa Cruz"
    assert UCSC_ECE_CONFIG.expected_email_domains == ("ucsc.edu",)
    assert UCSC_ECE_CONFIG.directory_url.endswith("/electrical-and-computer-engineering/people/")
    assert UCSB_ECE_CONFIG.department == "Electrical and Computer Engineering"
    assert UCSB_ECE_CONFIG.university_name == "University of California, Santa Barbara"
    assert UCSB_ECE_CONFIG.directory_url == "https://www.ece.ucsb.edu/people/faculty"

    assert IMPLEMENTED_SCRAPERS["University of California, Santa Cruz"].__name__ == (
        "BroadenedUCSCScraper"
    )
    assert IMPLEMENTED_SCRAPERS["University of California, Santa Barbara"].__name__ == (
        "BroadenedUCSBScraper"
    )

    for scraper_class in (BroadenedUCSCScraper, BroadenedUCSBScraper):
        instance = scraper_class(max_profiles=1)
        assert len(instance.sub_scrapers) == 2
        assert instance.sub_scrapers[0].university_name == instance.university_name
        assert instance.sub_scrapers[1].config.department == "Electrical and Computer Engineering"
        assert not hasattr(instance, "authoritative_roster")


def test_broadened_configurable_scrapers_set_university_name():
    from scrapers.broadened import UCSBECEScraper, UCSCECEScraper

    assert UCSCECEScraper.university_name == "University of California, Santa Cruz"
    assert UCSBECEScraper.university_name == "University of California, Santa Barbara"
    assert UCSBECEScraper.directory_url == "https://www.ece.ucsb.edu/people/faculty"


# ---------- Taxonomy for the new department ----------


def test_v97_taxonomy_maps_electrical_and_computer_engineering():
    assert infer_field("Electrical and Computer Engineering") == "Electrical and Computer Engineering"
    assert infer_discipline("Electrical and Computer Engineering") == "Engineering"
    school, discipline, field, subfield = infer_taxonomy(
        university="University of California, Santa Cruz",
        department="Electrical and Computer Engineering",
        categories="Signal Processing, Machine Learning",
    )
    assert school == "Baskin School of Engineering"
    assert discipline == "Engineering"
    assert field == "Electrical and Computer Engineering"
    assert subfield == "Signal Processing"
    school_ucsb, _, _, _ = infer_taxonomy(
        university="University of California, Santa Barbara",
        department="Electrical and Computer Engineering",
    )
    assert school_ucsb == "College of Engineering"


# ---------- Refresh integration (offline) ----------


def test_v97_broadened_refresh_adds_ece_without_relabeling_or_pruning(tmp_path: Path, monkeypatch):
    from scrapers import broadened as broadened_module

    university = "University of California, Santa Cruz"
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    database.initialize_database()
    try:
        existing_cs = _record(
            "Existing CS Prof",
            university,
            "Computer Science and Engineering",
            "existing@ucsc.edu",
        )
        database.upsert_professors([existing_cs.as_record()])
        assert len(database.fetch_professors()) == 1

        cross_cs = _record(
            "Cross Listed Prof",
            university,
            "Computer Science and Engineering",
            "cross@ucsc.edu",
        )
        new_ece = _record(
            "New ECE Prof",
            university,
            "Electrical and Computer Engineering",
            "newece@ucsc.edu",
        )

        class FakeCS:
            config = UCSC_ECE_CONFIG

            def __init__(self, request_delay=0.45, timeout=20, max_profiles=None, progress_callback=None):
                self.university_name = university
                self.last_error = ""

            def safe_scrape(self):
                return [existing_cs, cross_cs]

        class FakeECE:
            config = UCSC_ECE_CONFIG

            def __init__(self, request_delay=0.45, timeout=20, max_profiles=None, progress_callback=None):
                self.university_name = university
                self.last_error = ""

            def safe_scrape(self):
                return [
                    _record(
                        "Cross Listed Prof",
                        university,
                        "Electrical and Computer Engineering",
                        "cross@ucsc.edu",
                    ),
                    new_ece,
                    _record(
                        "Generic Mailbox Person",
                        university,
                        "Electrical and Computer Engineering",
                        "be-ecechair@ucsc.edu",
                    ),
                    _record(
                        "Graduate Director",
                        university,
                        "Electrical and Computer Engineering",
                        "role-person@ucsc.edu",
                    ),
                ]

        monkeypatch.setattr(broadened_module, "UCSCScraper", FakeCS)
        monkeypatch.setattr(broadened_module, "UCSCECEScraper", FakeECE)
        monkeypatch.setattr(
            refresh_service,
            "UNIVERSITY_SCRAPERS",
            {university: broadened_module.BroadenedUCSCScraper},
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

        rows = database.fetch_professors()
        by_email = {str(row["email"]): row for row in rows}
        assert len(rows) == 3
        assert by_email["existing@ucsc.edu"]["department"] == "Computer Science and Engineering"
        assert by_email["cross@ucsc.edu"]["department"] == "Computer Science and Engineering"
        assert by_email["newece@ucsc.edu"]["department"] == "Electrical and Computer Engineering"
        assert by_email["newece@ucsc.edu"]["verification_status"] == "Not checked"
        assert by_email["existing@ucsc.edu"]["verification_status"] == "Not checked"
        assert "be-ecechair@ucsc.edu" not in by_email
        assert "role-person@ucsc.edu" not in by_email
    finally:
        database.DB_PATH = original


def test_v97_wrapper_preserves_ordering_of_existing_scrapers():
    wrapper = BroadenedUCSCScraper(max_profiles=1)
    from scrapers.ucsc import UCSCScraper

    assert wrapper.sub_scrapers[0].config.department == "Computer Science and Engineering"
    assert isinstance(wrapper.sub_scrapers[1].config, UCSC_ECE_CONFIG.__class__)
    assert wrapper.sub_scrapers[0].config is UCSCScraper.config


def test_v97_backfill_writes_taxonomy_for_ece(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        record = _record(
            "ECE Taxonomy Prof",
            "University of California, Santa Cruz",
            "Electrical and Computer Engineering",
            "taxonomy@ucsc.edu",
        )
        database.upsert_professors([record.as_record()])
        row = database.fetch_professors()[0]
        assert row["school_or_college"] == "Baskin School of Engineering"
        assert row["discipline"] == "Engineering"
        assert row["field"] == "Electrical and Computer Engineering"
        assert row["subfield"] == NOT_AVAILABLE
    finally:
        database.DB_PATH = original


def _stamp_embedding(tmp_path: Path, email: str) -> None:
    with database.connect() as connection:
        connection.execute(
            "UPDATE professors SET embedding_json = '[]', embedding_model = 'test', "
            "ai_summary = 'existing AI summary' WHERE email = ?",
            (email,),
        )


def _semantic_record(
    name: str,
    email: str,
    *,
    title: str,
    research_interests: str,
    categories: str,
) -> dict:
    return {
        "name": name,
        "university": "University of California, Santa Cruz",
        "department": "Computer Science and Engineering",
        "title": title,
        "research_interests": research_interests,
        "categories": categories,
        "email": email,
    }


def test_v97_semantic_change_ignores_pronoun_only_title(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        base = {
            "name": "Pronoun Update Prof",
            "university": "University of California, Santa Cruz",
            "department": "Computer Science and Engineering",
            "email": "pronoun@ucsc.edu",
            "title": "Associate Professor",
            "research_interests": "Machine learning and signal processing",
            "categories": "Machine Learning",
        }
        database.upsert_professors([base])
        _stamp_embedding(tmp_path, "pronoun@ucsc.edu")

        pronoun_only = dict(base, title="Associate Professor She/Her/Hers")
        database.upsert_professors([pronoun_only])
        row = database.fetch_professors()[0]
        assert row["embedding_json"] == "[]"

        promoted = dict(base, title="Professor")
        database.upsert_professors([promoted])
        row = database.fetch_professors()[0]
        assert row["embedding_json"] == ""
    finally:
        database.DB_PATH = original


NAV_A = (
    "Important Data Privacy Update: Changes to Student Directory Information "
    "Dismiss UC Santa Cruz MyUCSC People Calendars Maps A-Z Index Search Campus "
    "Directory About Admissions Academics Research Campus Life Visit UCSC Quick "
    "Start Guides Current Students"
)
NAV_B = (
    "Campus Directory - UC Santa Cruz UC Santa Cruz MyUCSC People Calendars Maps "
    "A-Z Index Search Campus Directory About Admissions Academics Research Campus "
    "Life Visit UCSC Calendars Dismiss Skip To Main Content"
)


def test_v97_semantic_change_ignores_nav_only_research_interests(tmp_path: Path):
    from database import _research_nav_only, _title_signature

    assert _research_nav_only(NAV_A) == 1
    assert _research_nav_only(NAV_B) == 1
    assert _research_nav_only("Machine learning and signal processing") == 0
    assert _title_signature("Associate Professor She/Her/Hers") == "associate professor"

    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        base = _semantic_record(
            "Nav Chrome Prof",
            "navchrome@ucsc.edu",
            title="Professor",
            research_interests=NAV_A,
            categories="Security & Privacy",
        )
        database.upsert_professors([base])
        _stamp_embedding(tmp_path, "navchrome@ucsc.edu")

        nav_variant = _semantic_record(
            "Nav Chrome Prof",
            "navchrome@ucsc.edu",
            title="Professor",
            research_interests=NAV_B,
            categories="Other Computing Research",
        )
        database.upsert_professors([nav_variant])
        row = database.fetch_professors()[0]
        assert row["embedding_json"] == "[]"
        assert row["ai_summary"] == "existing AI summary"

        real_change = _semantic_record(
            "Nav Chrome Prof",
            "navchrome@ucsc.edu",
            title="Professor",
            research_interests="Machine learning and signal processing",
            categories="Machine Learning",
        )
        database.upsert_professors([real_change])
        row = database.fetch_professors()[0]
        assert row["embedding_json"] == ""
    finally:
        database.DB_PATH = original


def _force_maintenance(tmp_path: Path) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO app_migrations (migration_key, applied_at, details) "
            "VALUES ('professors_data_maintenance', CURRENT_TIMESTAMP, '-1') "
            "ON CONFLICT(migration_key) DO UPDATE SET details = excluded.details"
        )
    database.initialize_database()


_SRA_FIX_ROW = {
    "name": "Misha Sra",
    "university": "University of California, Santa Barbara",
    "department": "Computer Science and Engineering",
    "email": "sra@cs.ucsb.edu",
    "profile_url": "https://www.cs.ucsb.edu/people/faculty/misha-sra",
    "website_url": "https://sites.cs.ucsb.edu/~sra/",
    "research_interests": "Human-centered and social computing, machine learning",
    "categories": "Human-Computer Interaction",
}


def test_v97_data_maintenance_preserves_embedding_for_pronoun_only_title_fix(
    tmp_path: Path,
):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        row = dict(_SRA_FIX_ROW, title="Associate Professor She/Her/Hers")
        database.upsert_professors([row])
        _stamp_embedding(tmp_path, _SRA_FIX_ROW["email"])

        _force_maintenance(tmp_path)

        fetched = {r["email"]: r for r in database.fetch_professors()}
        professor = fetched[_SRA_FIX_ROW["email"]]
        assert professor["title"] == "Associate Professor"
        assert professor["embedding_json"] == "[]"
        assert professor["ai_summary"] == "existing AI summary"
    finally:
        database.DB_PATH = original


def test_v97_data_maintenance_clears_embedding_for_real_title_fix(tmp_path: Path):
    original = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        row = dict(_SRA_FIX_ROW, title="Assistant Professor")
        database.upsert_professors([row])
        _stamp_embedding(tmp_path, _SRA_FIX_ROW["email"])

        _force_maintenance(tmp_path)

        fetched = {r["email"]: r for r in database.fetch_professors()}
        professor = fetched[_SRA_FIX_ROW["email"]]
        assert professor["title"] == "Associate Professor"
        assert professor["embedding_json"] == ""
    finally:
        database.DB_PATH = original
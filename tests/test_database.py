from pathlib import Path

import database


def test_clean_title_drops_directory_navigation_and_prose():
    assert (
        database._clean_title(
            "Assistant Professor of Computer Science College of Sciences "
            "Department of Computer Science College of Sciences San Diego E-Mail"
        )
        == "Assistant Professor of Computer Science"
    )
    assert (
        database._clean_title(
            "Professor Affiliation Faculty Faculty Type Regular Faculty "
            "Web Site Home Page Computer Vision Lab Primary"
        )
        == "Professor"
    )
    assert (
        database._clean_title(
            "Professor of Applied and Computational Mathematics Profile Publications "
            "Teaching algorithms, numerical analysis, statistics, random matrix theory "
            "Overview Joel Tropp's work lies at the inte"
        )
        == "Professor of Applied and Computational Mathematics"
    )
    assert (
        database._clean_title(
            "Instructor in Computing and Mathematical Sciences B.S., ETH Zurich, 2021, "
            "M.S., 2021, Ph.D., 2024. Caltech, 2024-26. Profile Publications Teaching"
        )
        == "Instructor in Computing and Mathematical Sciences"
    )


def test_clean_title_collapses_repeated_and_garbage_titles():
    assert (
        database._clean_title(
            "Distinguished Professor Doluca Family Chair in ECE "
            "Distinguished Professor Doluca Family Chair in ECE"
        )
        == "Distinguished Professor Doluca Family Chair in ECE"
    )
    assert database._clean_title("Assistant Professor 5104993609") == "Assistant Professor"
    assert database._clean_title("Assistant Professor He/Him/His") == "Assistant Professor"
    assert (
        database._clean_title("Professor & Graduate Program Advisor He/Him/His")
        == "Professor & Graduate Program Advisor"
    )


def test_clean_title_keeps_legitimate_long_academic_titles():
    for title in (
        "Distinguished Professor of Electrical Engineering and Computer Science, and holder "
        "of the Ming Hsieh Chair in Electrical and Computer Engineering",
        "Assistant Professor (Research) of Psychiatry and Behavioral Sciences and, by "
        "courtesy, of Computer Science and of Biomedical Data Science",
        "Associate Professor in the Department of Computer Science and Engineering at the "
        "University of California",
        "Professor of Computer Science, Electrical and Computer Engineering, and Biomedical "
        "Sciences, and Fletcher Jones Foundation Chair in Computer Science",
        "Professor, Applied Mathematics; Boeing Professor in AI & Data-Driven Engineering, "
        "Electrical & Computer Engineering; Adjunct Professor, Physics",
    ):
        assert database._clean_title(title) == title


def test_clean_title_collapses_connector_separated_repeat():
    # Umesh Mishra (id 1126): the directory printed the endowed-chair form of the
    # name on both sides of the real title.
    messy = (
        "Distinguished Professor Richard A. Auhll Professor Donald W. Whittier "
        "Professor of ECE Dean of the College of Engineering & Distinguished "
        "Professor Richard A. Auhll Professor Donald W. Whittier Professor"
    )
    cleaned = database._clean_title(messy)
    assert cleaned == (
        "Distinguished Professor Richard A. Auhll Professor Donald W. Whittier "
        "Professor of ECE Dean of the College of Engineering"
    )
    # Idempotent: a second pass must not change the repaired title.
    assert database._clean_title(cleaned) == cleaned
    # The duplicate block really is gone.
    assert cleaned.count("Richard A. Auhll Professor") == 1
    assert not cleaned.endswith("&")


def test_clean_title_connector_rule_spares_legitimate_titles():
    legitimate = (
        "Distinguished Professor of Electrical Engineering and Computer Science, and holder "
        "of the Ming Hsieh Chair in Electrical and Computer Engineering",
        "Assistant Professor (Research) of Psychiatry and Behavioral Sciences and, by "
        "courtesy, of Computer Science and of Biomedical Data Science",
        "Associate Professor in the Department of Computer Science and Engineering at the "
        "University of California",
        "Professor of Computer Science, Electrical and Computer Engineering, and Biomedical "
        "Sciences, and Fletcher Jones Foundation Chair in Computer Science",
        "Professor, Applied Mathematics; Boeing Professor in AI & Data-Driven Engineering, "
        "Electrical & Computer Engineering; Adjunct Professor, Physics",
    )
    for title in legitimate:
        assert database._clean_title(title) == title


def test_clean_title_connector_rule_requires_a_real_repeat():
    # A long title that merely mentions two similar phrases must survive: the
    # leading block has to repeat verbatim at the end.
    title = (
        "Professor of Electrical Engineering and Computer Science Chair and "
        "Professor of Electrical Engineering and Computer Science Vice Chair"
    )
    assert database._clean_title(title) == title


def test_upsert_updates_same_person_when_email_changes(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        base = {
            "name": "Sample Person",
            "university": "Stanford University",
            "department": "Computer Science",
            "title": "Professor",
            "research_interests": "Machine learning",
            "email": "old@stanford.edu",
            "website_url": "https://example.edu",
            "profile_url": "https://example.edu/profile",
            "categories": "Machine Learning",
            "source_type": "Test",
        }
        database.upsert_professors([base])
        updated = dict(base)
        updated["email"] = "new@stanford.edu"
        updated["research_interests"] = "Machine learning and robotics"
        database.upsert_professors([updated])

        records = database.fetch_professors()
        assert len(records) == 1
        assert records[0]["email"] == "new@stanford.edu"
        assert "robotics" in records[0]["research_interests"]
    finally:
        database.DB_PATH = original_path


def test_database_migrates_and_saves_outreach_fields(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        database.upsert_professors(
            [
                {
                    "name": "Opportunity Person",
                    "university": "Example University",
                    "department": "Computer Science",
                    "title": "Assistant Professor",
                    "research_interests": "Machine learning",
                    "email": "person@example.edu",
                    "website_url": "https://example.edu/lab",
                    "profile_url": "https://example.edu/person",
                    "categories": "Machine Learning",
                    "opportunity_level": "Strong",
                    "opportunity_signals": "Lists open positions",
                    "opportunity_source_url": "https://example.edu/lab/join",
                    "source_type": "Test",
                }
            ]
        )
        record = database.fetch_professors()[0]
        assert record["opportunity_level"] == "Strong"
        assert record["opportunity_signals"] == "Lists open positions"
    finally:
        database.DB_PATH = original_path


def test_database_cleans_legacy_layout_and_link_artifacts(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        database.upsert_professors(
            [
                {
                    "name": "Terms of Use",
                    "university": "University of California, Los Angeles",
                    "department": "Computer Science",
                    "title": "Not publicly available",
                    "research_interests": "Not publicly available",
                    "email": "uclaengr@seas.ucla.edu",
                    "website_url": "https://www.linkedin.com/company/example",
                    "profile_url": "https://www.cs.ucla.edu/research-areas/",
                    "categories": "",
                    "source_type": "Test",
                },
                {
                    "name": "Real Professor",
                    "university": "University of California, Berkeley",
                    "department": "Computer Science",
                    "title": "Below The Line Assistant Professor",
                    "research_interests": "Machine learning",
                    "email": "real@ucsd.edua",
                    "website_url": "https://www2.eecs.berkeley.edu/Research/Areas/Centers/",
                    "profile_url": "https://example.berkeley.edu/real",
                    "categories": "Machine Learning",
                    "source_type": "Test",
                },
            ]
        )
        records = database.fetch_professors()
        assert len(records) == 1
        assert records[0]["name"] == "Real Professor"
        assert records[0]["title"] == "Assistant Professor"
        assert records[0]["email"] == "real@ucsd.edu"
        assert records[0]["website_url"] == "Not publicly available"
    finally:
        database.DB_PATH = original_path


def test_database_removes_document_share_links_from_website_field(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        database.upsert_professors([
            {
                "name": "Document Link Person",
                "university": "San Jose State University",
                "department": "Computer Science",
                "title": "Lecturer",
                "research_interests": "Computing education",
                "email": "document@sjsu.edu",
                "website_url": "https://drive.google.com/file/d/example/view",
                "profile_url": "https://www.sjsu.edu/people/document.person/",
                "categories": "Computer Science",
                "source_type": "Test",
            }
        ])
        record = database.fetch_professors()[0]
        assert record["website_url"] == "Not publicly available"
    finally:
        database.DB_PATH = original_path


def test_startup_url_only_cleanup_preserves_ai_index(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        database.upsert_professors([
            {
                "name": "Indexed Person",
                "university": "San Jose State University",
                "department": "Computer Science",
                "title": "Professor",
                "research_interests": "Machine learning",
                "email": "indexed@sjsu.edu",
                "website_url": "https://example.org/lab",
                "profile_url": "https://www.sjsu.edu/people/indexed/",
                "categories": "Machine Learning",
                "source_type": "Test",
            }
        ])
        with database.connect() as connection:
            connection.execute(
                """
                UPDATE professors
                SET website_url = 'https://drive.google.com/file/d/example/view',
                    ai_categories = 'AI', ai_summary = 'Existing summary',
                    embedding_json = '[0.1, 0.2]', embedding_model = 'test-model',
                    embedding_source_hash = 'hash', ai_enriched_at = '2026-01-01'
                """
            )
        database.initialize_database()
        record = database.fetch_professors()[0]
        assert record["website_url"] == database.NOT_AVAILABLE
        assert record["ai_summary"] == "Existing summary"
        assert record["embedding_json"] == "[0.1, 0.2]"
        assert record["embedding_model"] == "test-model"
    finally:
        database.DB_PATH = original_path


def test_startup_repairs_known_urls_without_forcing_dead_tantalo_url(tmp_path: Path):
    original_path = database.DB_PATH
    database.DB_PATH = tmp_path / "professors.db"
    try:
        database.initialize_database()
        database.upsert_professors(
            [
                {
                    "name": "James A. Preiss",
                    "university": "University of California, Santa Barbara",
                    "department": "Computer Science",
                    "title": "Assistant Professor",
                    "research_interests": "Robotics",
                    "email": "preiss@ucsb.edu",
                    "website_url": "https://www.cs.ucsb.edu/index.php/research/research-centers",
                    "profile_url": "https://www.cs.ucsb.edu/people/faculty/james-preiss",
                    "categories": "Robotics",
                    "source_type": "Test",
                },
                {
                    "name": "Misha Sra",
                    "university": "University of California, Santa Barbara",
                    "department": "Computer Science",
                    "title": "Associate Professor She/Her/Hers",
                    "research_interests": "Human-AI interaction",
                    "email": "sra@cs.ucsb.edu",
                    "website_url": "https://www.cs.ucsb.edu/index.php/research/research-centers",
                    "profile_url": "https://www.cs.ucsb.edu/people/faculty/misha-sra",
                    "categories": "Artificial Intelligence",
                    "source_type": "Test",
                },
                {
                    "name": "Patrick Tantalo",
                    "university": "University of California, Santa Cruz",
                    "department": "Computer Science and Engineering",
                    "title": "Lecturer",
                    "research_interests": "Computer science education",
                    "email": "ptantalo@ucsc.edu",
                    "website_url": "https://users.soe.ucsc.edu/~ptantalo/",
                    "profile_url": "https://campusdirectory.ucsc.edu/cd_detail?uid=ptantalo",
                    "categories": "Computer Science",
                    "source_type": "Test",
                },
                {
                    "name": "Wensheng Wu",
                    "university": "University of Southern California",
                    "department": "Computer Science",
                    "title": "Associate Professor of Computer Science Practice",
                    "research_interests": "Databases",
                    "email": "wenshenw@usc.edu",
                    "website_url": "Not publicly available",
                    "profile_url": "https://www.cs.usc.edu/directory/faculty/profile/?lname=Wu&fname=Wensheng",
                    "categories": "Data Science",
                    "source_type": "Test",
                },
            ]
        )
        database.initialize_database()
        records = {record["name"]: record for record in database.fetch_professors()}
        assert records["James A. Preiss"]["website_url"] == "https://www.jamespreiss.com/"
        assert records["Misha Sra"]["website_url"] == "https://sites.cs.ucsb.edu/~sra/"
        assert records["Misha Sra"]["title"] == "Associate Professor"
        assert records["Patrick Tantalo"]["website_url"] == "https://users.soe.ucsc.edu/~ptantalo/"
        assert records["Wensheng Wu"]["profile_url"] == "https://viterbi.usc.edu/directory/faculty/Wu/Wensheng"
        assert all(record["verification_status"] == "Not checked" for record in records.values())
    finally:
        database.DB_PATH = original_path

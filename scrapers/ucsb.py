from scrapers.configurable import ConfigurableFacultyScraper, FacultyDirectoryConfig


class UCSBScraper(ConfigurableFacultyScraper):
    config = FacultyDirectoryConfig(
        university_name="University of California, Santa Barbara",
        directory_url="https://www.cs.ucsb.edu/people/faculty",
        department="Computer Science",
        source_type="Official UC Santa Barbara Computer Science faculty directory and profiles",
        expected_email_domains=("ucsb.edu", "cs.ucsb.edu"),
        city="Santa Barbara",
        profile_path_hints=("/people/", "/faculty/"),
        allow_directory_profile_fallback=True,
    )

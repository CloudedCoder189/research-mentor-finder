from scrapers.configurable import ConfigurableFacultyScraper, FacultyDirectoryConfig


class UCSCScraper(ConfigurableFacultyScraper):
    config = FacultyDirectoryConfig(
        university_name="University of California, Santa Cruz",
        directory_url="https://engineering.ucsc.edu/departments/computer-science-and-engineering/people/",
        department="Computer Science and Engineering",
        source_type="Official UC Santa Cruz Computer Science and Engineering people directory and profiles",
        expected_email_domains=("ucsc.edu",),
        city="Santa Cruz",
        profile_path_hints=("/people/", "/faculty/"),
    )

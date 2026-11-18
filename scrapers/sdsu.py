from scrapers.configurable import ConfigurableFacultyScraper, FacultyDirectoryConfig


class SDSUScraper(ConfigurableFacultyScraper):
    config = FacultyDirectoryConfig(
        university_name="San Diego State University",
        directory_url="https://cs.sdsu.edu/faculty/",
        department="Computer Science",
        source_type="Official San Diego State University Computer Science faculty directory and profiles",
        expected_email_domains=("sdsu.edu",),
        city="San Diego",
        profile_path_hints=("/people/", "/faculty/", "/profiles/"),
    )

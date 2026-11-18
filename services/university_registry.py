from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UniversityMetadata:
    name: str
    slug: str
    city: str
    state: str
    country: str = "United States"
    primary_directory_url: str = "Not publicly available"


UNIVERSITY_REGISTRY: dict[str, UniversityMetadata] = {
    "Stanford University": UniversityMetadata(
        name="Stanford University",
        slug="stanford",
        city="Stanford",
        state="California",
        primary_directory_url="https://www.cs.stanford.edu/people/faculty",
    ),
    "University of California, Berkeley": UniversityMetadata(
        name="University of California, Berkeley",
        slug="uc-berkeley",
        city="Berkeley",
        state="California",
        primary_directory_url="https://www2.eecs.berkeley.edu/Faculty/Lists/CS/faculty.html",
    ),
    "University of California, Los Angeles": UniversityMetadata(
        name="University of California, Los Angeles",
        slug="ucla",
        city="Los Angeles",
        state="California",
        primary_directory_url="https://www.cs.ucla.edu/research-areas/",
    ),
    "University of California, San Diego": UniversityMetadata(
        name="University of California, San Diego",
        slug="uc-san-diego",
        city="San Diego",
        state="California",
        primary_directory_url="https://cse.ucsd.edu/people/faculty-profiles/faculty",
    ),
    "San Jose State University": UniversityMetadata(
        name="San Jose State University",
        slug="san-jose-state",
        city="San Jose",
        state="California",
        primary_directory_url="https://www.sjsu.edu/cs/faculty/faculty.php",
    ),
    "University of California, Davis": UniversityMetadata(
        name="University of California, Davis",
        slug="uc-davis",
        city="Davis",
        state="California",
        primary_directory_url="https://cs.ucdavis.edu/directory",
    ),
    "University of California, Irvine": UniversityMetadata(
        name="University of California, Irvine",
        slug="uc-irvine",
        city="Irvine",
        state="California",
        primary_directory_url="https://cs.ics.uci.edu/faculty/",
    ),
    "University of California, Santa Barbara": UniversityMetadata(
        name="University of California, Santa Barbara",
        slug="uc-santa-barbara",
        city="Santa Barbara",
        state="California",
        primary_directory_url="https://www.cs.ucsb.edu/people/faculty",
    ),
    "University of California, Santa Cruz": UniversityMetadata(
        name="University of California, Santa Cruz",
        slug="uc-santa-cruz",
        city="Santa Cruz",
        state="California",
        primary_directory_url="https://engineering.ucsc.edu/departments/computer-science-and-engineering/people/",
    ),
    "California Institute of Technology": UniversityMetadata(
        name="California Institute of Technology",
        slug="caltech",
        city="Pasadena",
        state="California",
        primary_directory_url="https://www.cms.caltech.edu/people/faculty",
    ),
    "Santa Clara University": UniversityMetadata(
        name="Santa Clara University",
        slug="santa-clara",
        city="Santa Clara",
        state="California",
        primary_directory_url="https://www.scu.edu/engineering/academic-programs/department-of-computer-engineering/faculty--staff/",
    ),
    "California Polytechnic State University, San Luis Obispo": UniversityMetadata(
        name="California Polytechnic State University, San Luis Obispo",
        slug="cal-poly-slo",
        city="San Luis Obispo",
        state="California",
        primary_directory_url="https://csc.calpoly.edu/faculty/",
    ),
    "San Diego State University": UniversityMetadata(
        name="San Diego State University",
        slug="san-diego-state",
        city="San Diego",
        state="California",
        primary_directory_url="https://cs.sdsu.edu/faculty/",
    ),
    "University of Southern California": UniversityMetadata(
        name="University of Southern California",
        slug="usc",
        city="Los Angeles",
        state="California",
        primary_directory_url="https://www.cs.usc.edu/directory/faculty/",
    ),
    "Oregon State University": UniversityMetadata(
        name="Oregon State University",
        slug="oregon-state",
        city="Corvallis",
        state="Oregon",
        primary_directory_url="https://engineering.oregonstate.edu/EECS/About/People",
    ),
    "University of Oregon": UniversityMetadata(
        name="University of Oregon",
        slug="university-of-oregon",
        city="Eugene",
        state="Oregon",
        primary_directory_url="https://cas.uoregon.edu/directory/computer-science-faculty",
    ),
    "Portland State University": UniversityMetadata(
        name="Portland State University",
        slug="portland-state",
        city="Portland",
        state="Oregon",
        primary_directory_url="https://www.pdx.edu/engineering/directory",
    ),
    "University of Washington": UniversityMetadata(
        name="University of Washington",
        slug="university-of-washington",
        city="Seattle",
        state="Washington",
        primary_directory_url="https://www.cs.washington.edu/people/faculty-members/",
    ),
    "Washington State University": UniversityMetadata(
        name="Washington State University",
        slug="washington-state",
        city="Pullman",
        state="Washington",
        primary_directory_url="https://people.wsu.edu/wp-json/wp/v2/people?organization=790",
    ),
    "Western Washington University": UniversityMetadata(
        name="Western Washington University",
        slug="western-washington",
        city="Bellingham",
        state="Washington",
        primary_directory_url="https://cs.wwu.edu/faculty",
    ),
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    return slug or "unknown-university"


def metadata_for(university: str) -> UniversityMetadata:
    name = " ".join(str(university).split()).strip() or "Unknown University"
    return UNIVERSITY_REGISTRY.get(
        name,
        UniversityMetadata(
            name=name,
            slug=slugify(name),
            city="Not publicly available",
            state="Not publicly available",
        ),
    )


def infer_department_category(department: str, research_text: str = "") -> str:
    text = f"{department} {research_text}".casefold()
    rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Computer Science", ("computer science", "computing", "informatics")),
        (
            "Electrical & Computer Engineering",
            ("electrical", "computer engineering", "ece", "engineering and computer science"),
        ),
        ("Data Science & Statistics", ("data science", "statistics", "statistical")),
        (
            "Biomedical & Health Computing",
            ("biomedical", "medicine", "medical", "health", "bioinformatics", "genomics"),
        ),
        ("Robotics & Autonomous Systems", ("robot", "autonomous", "control systems")),
        ("Cognitive Science & Psychology", ("cognitive", "psychology", "neuroscience")),
        ("Environmental & Climate Computing", ("climate", "environment", "earth science")),
    )
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other Research Area"


def states_for(universities: list[str] | None = None) -> list[str]:
    names = universities or list(UNIVERSITY_REGISTRY)
    states = {metadata_for(name).state for name in names}
    return sorted(state for state in states if state != "Not publicly available")

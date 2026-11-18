"""Conservative academic taxonomy inference for professor records.

Every mapping below is derived from values already published on the record
(``department`` and categories labels) or from well-known facts about the 14
registered universities. Nothing is invented per professor: rows that cannot be
mapped confidently keep the shared ``Not publicly available`` marker. The
inferrers are pure functions so they can be unit-tested and reused by the
one-time database backfill.
"""

from __future__ import annotations

NOT_AVAILABLE = "Not publicly available"

FIELD_FROM_DEPARTMENT: dict[str, str] = {
    "Computer Science": "Computer Science",
    "Computer Science and Engineering": "Computer Science and Engineering",
    "Computer Science and Software Engineering": "Computer Science and Software Engineering",
    "Electrical Engineering and Computer Sciences": "Electrical Engineering and Computer Sciences",
    "Electrical and Computer Engineering": "Electrical and Computer Engineering",
    "Electrical Engineering and Computer Science": "Electrical Engineering and Computer Science",
    "Mechanical and Materials Engineering": "Mechanical and Materials Engineering",
    "Civil and Environmental Engineering": "Civil and Environmental Engineering",
    "Bioengineering": "Bioengineering",
    "Computing and Mathematical Sciences": "Computing and Mathematical Sciences",
    "Statistics": "Statistics",
    "Data Science": "Data Science",
    "Chemistry": "Chemistry",
    "Physics": "Physics",
    "Economics": "Economics",
    "Biology": "Biology",
    "Mechanical, Industrial, and Manufacturing Engineering": "Mechanical, Industrial, and Manufacturing Engineering",
}

DISCIPLINE_FROM_FIELD: dict[str, str] = {
    "Computer Science": "Computing",
    "Computer Science and Engineering": "Engineering & Computing",
    "Computer Science and Software Engineering": "Engineering & Computing",
    "Electrical Engineering and Computer Sciences": "Engineering & Computing",
    "Electrical and Computer Engineering": "Engineering",
    "Electrical Engineering and Computer Science": "Engineering & Computing",
    "Mechanical and Materials Engineering": "Engineering",
    "Civil and Environmental Engineering": "Engineering",
    "Bioengineering": "Engineering",
    "Computing and Mathematical Sciences": "Mathematics & Computing",
    "Statistics": "Mathematics & Computing",
    "Data Science": "Computing",
    "Chemistry": "Physical & Life Sciences",
    "Physics": "Physical & Life Sciences",
    "Economics": "Social Sciences",
    "Biology": "Life Sciences",
    "Mechanical, Industrial, and Manufacturing Engineering": "Engineering",
}

SCHOOL_OR_COLLEGE_FROM_UNIVERSITY: dict[str, str] = {
    "Stanford University": "School of Engineering",
    "University of California, Berkeley": "College of Engineering",
    "University of California, Los Angeles": "Samueli School of Engineering",
    "University of California, San Diego": "Jacobs School of Engineering",
    "University of California, Davis": "College of Engineering",
    "University of California, Irvine": "Donald Bren School of Information and Computer Sciences",
    "University of California, Santa Barbara": "College of Engineering",
    "University of California, Santa Cruz": "Baskin School of Engineering",
    "University of Southern California": "Viterbi School of Engineering",
    "San Jose State University": "College of Engineering",
    "San Diego State University": "College of Engineering",
    "California Polytechnic State University, San Luis Obispo": "College of Engineering",
    "Santa Clara University": "School of Engineering",
    "California Institute of Technology": "Division of Engineering and Applied Science",
    "Oregon State University": "College of Engineering",
    "University of Oregon": "College of Arts and Sciences",
    "Portland State University": "Maseeh College of Engineering and Computer Science",
    "University of Washington": "College of Engineering",
    "Washington State University": "Voiland College of Engineering and Architecture",
    "Western Washington University": "College of Science and Engineering",
}


def infer_field(department: str) -> str:
    """Normalize a single-department value into a known field label.

    Joint appointments are stored as ``Department A; Department B`` — those are
    intentionally left unlabeled rather than guessing a primary department.
    """
    department = " ".join(str(department).split()).strip()
    if not department or ";" in department:
        return NOT_AVAILABLE
    return FIELD_FROM_DEPARTMENT.get(department, NOT_AVAILABLE)


def infer_discipline(field: str) -> str:
    """Broad academic area mapped from a known field label."""
    return DISCIPLINE_FROM_FIELD.get(field, NOT_AVAILABLE)


def infer_subfield(categories: str, ai_categories: str) -> str:
    """First published category label, or the shared marker when none exists."""
    for source in (categories, ai_categories):
        for token in str(source or "").split(","):
            label = " ".join(token.split()).strip()
            if label:
                return label
    return NOT_AVAILABLE


# Department-specific home units that differ from the university-wide default
# (Statistics at UC Berkeley lives in the College of Letters and Science, not
# the College of Engineering).
SCHOOL_OR_COLLEGE_FROM_UNIVERSITY_AND_DEPARTMENT: dict[tuple[str, str], str] = {
    ("University of California, Berkeley", "Statistics"): "College of Letters and Science",
    ("University of Oregon", "Computer Science"): "College of Arts and Sciences",
    ("University of Oregon", "Data Science"): "College of Arts and Sciences",
    ("University of Washington", "Statistics"): "College of Arts and Sciences",
    ("University of Washington", "Chemistry"): "College of Arts and Sciences",
    ("University of Washington", "Physics"): "College of Arts and Sciences",
    ("University of Washington", "Economics"): "College of Arts and Sciences",
    ("University of Washington", "Biology"): "College of Arts and Sciences",
}


def infer_school_or_college(university: str) -> str:
    """Known home unit for the registered universities, else the shared marker."""
    return SCHOOL_OR_COLLEGE_FROM_UNIVERSITY.get(
        " ".join(str(university).split()).strip(), NOT_AVAILABLE
    )


def infer_taxonomy(
    *,
    university: str,
    department: str,
    categories: str = "",
    ai_categories: str = "",
) -> tuple[str, str, str, str]:
    """Return ``(school_or_college, discipline, field, subfield)`` for a record."""
    university = " ".join(str(university).split()).strip()
    department = " ".join(str(department).split()).strip()
    field = infer_field(department)
    school = SCHOOL_OR_COLLEGE_FROM_UNIVERSITY_AND_DEPARTMENT.get(
        (university, department), infer_school_or_college(university)
    )
    return (
        school,
        infer_discipline(field),
        field,
        infer_subfield(categories, ai_categories),
    )
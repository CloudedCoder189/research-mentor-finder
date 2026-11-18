"""Washington State University faculty scrapers (V9.7 Phase 4).

Washington State publishes the official WSU People Directory through the
WordPress REST API on ``people.wsu.edu``.  Each person profile is a
``wsuwp_people_profile`` post whose JSON carries the verified shorthand
``nid``, personal email, ``position_title``, ``organization`` and
``classification`` taxonomy term ids, a research-focused biography block
(``content``), a personal ``website``, and the public profile URL.

Three Voiland College of Engineering and Architecture schools are in scope:

* School of Electrical Engineering and Computer Science -- organization 790;
* School of Mechanical and Materials Engineering -- organization 793;
* Department of Civil and Environmental Engineering -- organization 788.

People are selected by their direct department membership (``organization``
filter), which is far narrower than the keyword-wide ``?search=`` endpoint.  A
record is kept when the person is classified Faculty, or carries an explicit
faculty title (Professor / Chair / Instructor / Lecturer).  Staff-only roles
(Administrative Professional, Staff, Graduate Assistant, Hourly, Public
Affiliate) are dropped.

The combined :class:`WashingtonStateUniversityScraper` runs the schools in
canonical order (EECS first) and collapses cross-listed people through
:func:`services.deduplication.deduplicate`; it is deliberately non-authoritative
so a refresh never prunes existing records.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.broadened import combine_broadened
from scrapers.configurable import (
    LINK_BLOCKLIST,
    NOT_AVAILABLE,
    _clean,
    _clean_name,
    _concise_bio_research,
    sanitize_research_text,
)

LOGGER = logging.getLogger(__name__)

WSU_UNIVERSITY_NAME = "Washington State University"
WSU_PEOPLE_API = "https://people.wsu.edu/wp-json/wp/v2/people"

# term ids from the ``classification`` taxonomy.
WSU_CLASSIFICATION_FACULTY = 424
WSU_CLASSIFICATION_ADJUNCT = 546
WSU_CLASSIFICATION_EMERITUS = 520
WSU_CLASSIFICATION_AFFILIATE = 550
WSU_DROP_CLASSIFICATIONS = {
    409,  # administrative professional
    410,  # staff
    411,  # graduate assistant
    412,  # hourly
    413,  # public affiliate
}

WSU_FACULTY_TITLE_RE = re.compile(
    r"\b(?:professor|chair|dean|instructor|lecturer)\b", re.I
)

# term ids from the ``wsuwp_university_org`` taxonomy.
WSU_ORGANIZATIONS: dict[str, int] = {
    "Electrical Engineering and Computer Science": 790,
    "Mechanical and Materials Engineering": 793,
    "Civil and Environmental Engineering": 788,
}

WSU_DEPT_FLOORS: dict[str, int] = {
    "Electrical Engineering and Computer Science": 20,
    "Mechanical and Materials Engineering": 20,
    "Civil and Environmental Engineering": 15,
}

WSU_PER_PAGE = 100


@dataclass(slots=True)
class WSUPerson:
    name: str
    title: str = NOT_AVAILABLE
    email: str = ""
    profile_url: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE


def _rendered_text(value: object) -> str:
    return (
        " ".join(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True).split())
        if value
        else ""
    )


def _field(item: dict, key: str) -> str:
    value = item.get(key)
    if isinstance(value, dict):
        return str(value.get("rendered", "") or "")
    return str(value or "")


_BOILERPLATE = (
    "This link leads to an external website that is not hosted by the university",
    "The views and content expressed are those of the faculty member",
    "and do not represent the official positions of the university",
    "This link leads to an external website",
)

_BIO_BOUNDARY_LABELS = (
    "Education",
    "Courses",
    "Teaching",
    "Publications",
    "Selected Publications",
    "Professional Experience",
    "Experience",
    "Awards",
    "Honors",
    "Service",
    "Memberships",
    "Correspondence",
)


def _wsu_research(content_html: str) -> str:
    """Research description from a WSU profile's bio block.

    The rendered ``content`` mixes the person's research paragraphs with
    boilerplate around linked websites and other biography sections; the
    research-labeled section is preferred and everything is capped/cleaned.
    """
    soup = BeautifulSoup(str(content_html or ""), "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    text = re.sub(r"<a\b[^>]*>", " ", text)  # escaped HTML anchors survive text extraction.
    for phrase in _BOILERPLATE:
        text = text.replace(phrase, " ").replace(phrase.casefold(), " ")
    cleaned = sanitize_research_text(text, max_chars=2400)
    if cleaned == NOT_AVAILABLE:
        return NOT_AVAILABLE

    for label in (
        "Research Areas",
        "Research Interests",
        "Research Focus",
        "Research Statement",
        "Research:",
        "Research",
    ):
        index = cleaned.casefold().find(label.casefold())
        if index == -1:
            continue
        value = cleaned[index + len(label):].strip(" :;,-")
        value = re.split(
            r"\s+(?:" + "|".join(re.escape(boundary) for boundary in _BIO_BOUNDARY_LABELS) + r")\s*:?",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        research = sanitize_research_text(value)
        if research != NOT_AVAILABLE:
            return research
    return _concise_bio_research(cleaned)


def _website_from_content(content_html: str) -> str:
    """First public personal/lab website published inside a WSU bio block."""
    soup = BeautifulSoup(str(content_html or ""), "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href.casefold().startswith(("http://", "https://")):
            continue
        if "people.wsu.edu" in href.casefold():
            continue
        host = href.split("/", 3)[2].casefold() if href.casefold().startswith("http") else ""
        if any(host == blocked or host.endswith(f".{blocked}") for blocked in LINK_BLOCKLIST):
            continue
        return href
    return ""


def keep_wsu_person(item: dict) -> tuple[bool, str]:
    """Decide whether one WSU People Directory record belongs in the app.

    Faculty classification, or an explicit faculty title, keeps the person;
    staff-only roles are rejected.  The classification ids live on the REST
    record as a list of integer term ids.
    """
    classifications = {int(value) for value in (item.get("classification") or []) if str(value).isdigit()}
    if WSU_CLASSIFICATION_FACULTY in classifications:
        return True, "classification=faculty"
    title = _clean(item.get("position_title", "") or "")
    working_titles = " ".join(str(value) for value in (item.get("working_titles") or []))
    combined_title = f"{title} {working_titles}"
    if WSU_FACULTY_TITLE_RE.search(combined_title):
        return True, "explicit faculty title"
    if combined_title and not (classifications & WSU_DROP_CLASSIFICATIONS):
        return True, "non-staff role"
    return False, f"staff-only role ({sorted(classifications)})"


def parse_wsu_person(item: dict) -> WSUPerson:
    """Convert one WSU People Directory REST object into a local record."""
    title_value = _field(item, "title")
    name = _clean_name(_rendered_text(title_value))
    if not name:
        name = _clean_name(
            f"{item.get('first_name', '')} {item.get('last_name', '')}"
        )
    title = _clean(_field(item, "position_title"))
    if not title:
        titles = [
            str(value)
            for value in (item.get("working_titles") or [])
            if str(value).strip()
        ]
        title = "; ".join(titles) if titles else NOT_AVAILABLE
    email = str(item.get("email", "") or "").strip().casefold()
    if not email:
        email = str(item.get("email_alt", "") or "").strip().casefold()
    profile_url = str(item.get("link", "") or "").strip() or NOT_AVAILABLE
    research = NOT_AVAILABLE
    content_raw = item.get("content")
    content = (
        content_raw.get("rendered", "") if isinstance(content_raw, dict) else ""
    )
    research = _wsu_research(content)
    if research == NOT_AVAILABLE:
        focus = [
            str(term.get("name", ""))
            for term in (item.get("taxonomy_terms") or {}).get("wsuwp_focus_area", [])
        ]
        research = sanitize_research_text("; ".join(name for name in focus if name))
    website = _website_from_content(content)
    return WSUPerson(
        name=name,
        title=title,
        email=email,
        profile_url=profile_url,
        research_interests=research,
        website_url=website or NOT_AVAILABLE,
    )


class WSUDeptScraper(BaseUniversityScraper):
    university_name = WSU_UNIVERSITY_NAME
    department = NOT_AVAILABLE
    organization_id: int | None = None
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 30,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback
        self.raw_count = 0
        self.kept_count = 0
        self.dropped_staff = 0
        self.dropped_no_email = 0

    def scrape(self) -> list[ScrapedProfessor]:
        records: list[ScrapedProfessor] = []
        page = 1
        while True:
            url = (
                f"{WSU_PEOPLE_API}?organization={self.organization_id}"
                f"&per_page={WSU_PER_PAGE}&page={page}"
            )
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            items = response.json()
            if self.progress_callback:
                self.progress_callback(
                    f"Reading Washington State {self.department} people page {page} "
                    f"({len(items)} records)..."
                )
            for item in items:
                self.raw_count += 1
                keep, reason = keep_wsu_person(item)
                if not keep:
                    self.dropped_staff += 1
                    continue
                self.kept_count += 1
                person = parse_wsu_person(item)
                if not person.email:
                    self.dropped_no_email += 1
                    continue
                records.append(
                    ScrapedProfessor(
                        name=person.name,
                        university=self.university_name,
                        department=self.department,
                        title=person.title,
                        research_interests=person.research_interests,
                        email=person.email,
                        website_url=person.website_url,
                        profile_url=person.profile_url,
                        source_type=(
                            f"Official Washington State {self.department} people "
                            "directory (people.wsu.edu)"
                        ),
                    )
                )
            if len(items) < WSU_PER_PAGE:
                break
            page += 1
            if page > 100:
                LOGGER.warning("WSU %s pagination exceeded 100 pages", self.department)
                break

        if self.max_profiles is not None:
            records = records[: self.max_profiles]
        floor = WSU_DEPT_FLOORS.get(self.department)
        if floor is not None and self.raw_count < floor:
            self.last_error = (
                f"{self.department} returned only {self.raw_count} records; "
                f"at least {floor} were expected."
            )
        return records


class WSUEECSDeptScraper(WSUDeptScraper):
    directory_url = f"{WSU_PEOPLE_API}?organization=790"
    department = "Electrical Engineering and Computer Science"
    organization_id = WSU_ORGANIZATIONS["Electrical Engineering and Computer Science"]


class WSUMMEDeptScraper(WSUDeptScraper):
    directory_url = f"{WSU_PEOPLE_API}?organization=793"
    department = "Mechanical and Materials Engineering"
    organization_id = WSU_ORGANIZATIONS["Mechanical and Materials Engineering"]


class WSUCEEDeptScraper(WSUDeptScraper):
    directory_url = f"{WSU_PEOPLE_API}?organization=788"
    department = "Civil and Environmental Engineering"
    organization_id = WSU_ORGANIZATIONS["Civil and Environmental Engineering"]


class WashingtonStateUniversityScraper(BaseUniversityScraper):
    """Combined Washington State University scraper (EECS + MME + CEE)."""

    university_name = WSU_UNIVERSITY_NAME
    directory_url = (
        "https://people.wsu.edu/wp-json/wp/v2/people?organization=790"
    )
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 30,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.sub_scrapers: list[WSUDeptScraper] = [
            WSUEECSDeptScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            WSUMMEDeptScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            WSUCEEDeptScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
        ]
        self.last_error = ""

    def scrape(self) -> list[ScrapedProfessor]:
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            message
            for message in (getattr(sub, "last_error", "") for sub in self.sub_scrapers)
            if str(message or "").strip()
        ]
        if errors:
            self.last_error = " ".join(errors)
        elif not combined:
            self.last_error = "No Washington State University faculty records were returned."
        return combined
"""Portland State University Maseeh College of Engineering (Phase 3).

V9.7 Phase 3 expands beyond California with the official Portland State
University Maseeh College of Engineering and Computer Science directory at
``https://www.pdx.edu/engineering/directory``.

The page is a single server-rendered document whose sections are anchored by
ids such as ``#cs`` and ``#ece``, each followed by a ``<table>`` with Name |
Title | Contact columns.  The table itself is the roster; the scraper targets
a section, parses the table that follows it, and keeps only academic rows.

Staff validation is title-based and conservative: a row is kept when its title
carries an academic term (professor, instructor, lecturer, of practice, chair,
faculty, researcher, ...); when it carries neither an academic nor a staff term
the row is kept (unknown titles are retained).  Clearly administrative titles
(advisor/adviser, manager, coordinator, general contact, administrator,
secretary, specialist, analyst, assistant to, ...) without an academic term are
dropped, so shared "General Contact" rows never become professor records.

Individual profile pages (``/profile/<slug>``) are thin but embed a research
narrative in ``og:description``, which the scraper reads when it follows a
profile for a row without an inline email.

Like the other Phase 3 Oregon scrapers, the combined
:class:`PortlandStateUniversityScraper` is deliberately not authoritative, so
a refresh never prunes existing Oregon records.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import NOT_AVAILABLE, _clean, _email_candidates, sanitize_research_text
from services.deduplication import deduplicate

LOGGER = logging.getLogger(__name__)

PSU_BASE_URL = "https://www.pdx.edu"
PSU_DIRECTORY_URL = "https://www.pdx.edu/engineering/directory"

PSU_UNIVERSITY_NAME = "Portland State University"

MAILTO_RE = re.compile(r"^mailto:", re.I)
PDX_EMAIL_RE = re.compile(r"[\w.+-]+@pdx\.edu", re.I)
OG_DESCRIPTION_RE = re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', re.S)
RESEARCH_PHRASE_RE = re.compile(r"research\s+include[s]?\s+", re.I)
RESEARCH_LABEL_RE = re.compile(r"research\s+interests?\s*[:.\-]?\s*", re.I)

STAFF_TITLE_TERMS = (
    "advisor",
    "adviser",
    "manager",
    "coordinator",
    "general contact",
    "contact",
    "administrator",
    "secretary",
    "specialist",
    "analyst",
    "assistant to",
    "receptionist",
    "office",
    "hiring",
    "recruiter",
    "counsel",
    "program support",
)

ACADEMIC_TITLE_TERMS = (
    "professor",
    "instructor",
    "lecturer",
    "of practice",
    "chair",
    "dean",
    "faculty",
    "researcher",
    "research scientist",
    "postdoc",
    "teaching",
)


@dataclass(slots=True)
class PSUDirectoryEntry:
    name: str
    title: str
    email: str
    profile_url: str


@dataclass(slots=True)
class PSUProfileDetails:
    email: str = ""
    title: str = ""
    research_interests: str = NOT_AVAILABLE


def keep_psu_faculty(title: str) -> bool:
    """Return True when a directory-table title is an academic roster row."""
    value = " ".join((title or "").casefold().split())
    if not value:
        return False
    if any(term in value for term in ACADEMIC_TITLE_TERMS):
        return True
    if any(term in value for term in STAFF_TITLE_TERMS):
        return False
    return True


def parse_psu_directory_page(
    html_text: str,
    section_id: str,
    base_url: str,
) -> list[PSUDirectoryEntry]:
    """Parse the roster table that follows the ``section_id`` anchor."""
    soup = BeautifulSoup(html_text, "html.parser")
    section = soup.find(id=section_id)
    if section is None:
        return []
    table = section.find_next("table")
    if table is None:
        return []
    headers = [th.get_text(" ", strip=True).casefold() for th in table.find_all("th")]
    if not any("name" in header for header in headers):
        return []

    entries: list[PSUDirectoryEntry] = []
    seen: set[tuple[str, str]] = set()
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        name = _clean(cells[0].get_text(" ", strip=True))
        title = _clean(cells[1].get_text(" ", strip=True)) if len(cells) > 1 else ""
        email = ""
        contact_node = cells[2] if len(cells) > 2 else None
        if contact_node is not None:
            mailto = contact_node.find("a", href=MAILTO_RE)
            if mailto is not None:
                email = _clean(mailto.get("href", "")[len("mailto:"):])
            else:
                match = PDX_EMAIL_RE.search(contact_node.get_text(" ", strip=True))
                if match:
                    email = match.group(0)
        profile_url = NOT_AVAILABLE
        for anchor in cells[0].find_all("a", href=True):
            href = anchor.get("href", "")
            if re.search(r"/profile/", href, re.I):
                profile_url = urljoin(base_url, href)
                break
        if not name:
            continue
        key = (name.casefold(), email.casefold())
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            PSUDirectoryEntry(name=name, title=title, email=email, profile_url=profile_url)
        )
    return entries


def _psu_research_from_description(description: str) -> str:
    """Isolate the research phrase inside a PSU profile og:description.

    The descriptions open like "Dr. Ameeta Agrawal is an Assistant Professor of
    Computer Science ... Dr. Agrawal's primary areas of research include
    natural language processing, machine learning, ...", so the research
    narrative is the fragment after "research include[s]".
    """
    text = _clean(unescape(description or ""))
    match = RESEARCH_PHRASE_RE.search(text)
    if match:
        return sanitize_research_text(_clean(text[match.end():]))
    label = RESEARCH_LABEL_RE.search(text)
    if label:
        return sanitize_research_text(_clean(text[label.end():]))
    return NOT_AVAILABLE


def parse_psu_profile_details(html_text: str) -> PSUProfileDetails:
    """Read email, title, and research narrative from a PSU profile page."""
    soup = BeautifulSoup(html_text, "html.parser")
    email = ""
    mailto = soup.find("a", href=MAILTO_RE)
    if mailto is not None:
        email = _clean(mailto.get("href", "")[len("mailto:"):])
    if not email:
        for candidate in _email_candidates(soup):
            if candidate.endswith("@pdx.edu"):
                email = candidate
                break
    title = ""
    title_node = soup.select_one("h2.text-lg-white")
    if title_node is not None:
        title = _clean(title_node.get_text(" ", strip=True))
    research = NOT_AVAILABLE
    match = OG_DESCRIPTION_RE.search(html_text)
    if match:
        research = _psu_research_from_description(match.group(1))
    return PSUProfileDetails(email=email, title=title, research_interests=research)


class PSUDirectoryScraper(BaseUniversityScraper):
    """Base scraper for one Portland State Maseeh College roster section."""

    university_name = PSU_UNIVERSITY_NAME
    department = "Not publicly available"
    directory_url = PSU_DIRECTORY_URL
    section_id = ""
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.4,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback
        self.staff_filtered = 0

    def scrape(self) -> list[ScrapedProfessor]:
        page_soup = self.get_soup(self.directory_url)
        entries = parse_psu_directory_page(
            str(page_soup), self.section_id, self.directory_url
        )
        kept = [entry for entry in entries if keep_psu_faculty(entry.title)]
        self.staff_filtered = len(entries) - len(kept)
        entries = kept
        entries.sort(key=lambda entry: entry.name.casefold())
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking Portland State {self.department} entry "
                    f"{index} of {total}: {entry.name}"
                )
            email = entry.email
            research = NOT_AVAILABLE
            title = entry.title
            if not email and entry.profile_url != NOT_AVAILABLE:
                profile_soup = None
                try:
                    profile_soup = self.get_soup(entry.profile_url)
                except requests.RequestException as exc:
                    LOGGER.warning(
                        "Could not inspect PSU profile for %s: %s",
                        entry.name,
                        exc,
                    )
                if profile_soup is not None:
                    details = parse_psu_profile_details(str(profile_soup))
                    email = details.email
                    if details.title and title in ("", NOT_AVAILABLE):
                        title = details.title
                    research = details.research_interests
            if not email:
                continue
            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department=self.department,
                    title=title,
                    research_interests=research,
                    email=email,
                    profile_url=entry.profile_url,
                    source_type=(
                        "Official Portland State University engineering "
                        "directory"
                    ),
                )
            )
        return records


class PSUComputerScienceScraper(PSUDirectoryScraper):
    section_id = "cs"
    department = "Computer Science"


class PSUElectricalAndComputerEngineeringScraper(PSUDirectoryScraper):
    section_id = "ece"
    department = "Electrical and Computer Engineering"


class PortlandStateUniversityScraper(BaseUniversityScraper):
    """Combined Portland State University scraper (CS + ECE)."""

    university_name = PSU_UNIVERSITY_NAME
    directory_url = PSU_DIRECTORY_URL
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.4,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.cs = PSUComputerScienceScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.ece = PSUElectricalAndComputerEngineeringScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.last_error = ""
        self.staff_filtered_total = 0

    def scrape(self) -> list[ScrapedProfessor]:
        cs_records = self.cs.safe_scrape()
        ece_records = self.ece.safe_scrape()
        self.staff_filtered_total = self.cs.staff_filtered + self.ece.staff_filtered
        errors = [
            message
            for message in (self.cs.last_error, self.ece.last_error)
            if str(message or "").strip()
        ]
        if errors:
            self.last_error = " ".join(errors)
        unique = deduplicate(
            [record.as_record() for record in cs_records + ece_records]
        )
        return [ScrapedProfessor(**row) for row in unique]
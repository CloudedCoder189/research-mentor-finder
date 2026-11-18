"""Western Washington University faculty scrapers (V9.7 Phase 4).

Two WWU departments are added, both through Drupal directory views that pair
each ``div.card``'s ``h3`` name link with a ``.job-title`` span and the
``mailto:`` address published inside the card body:

* Computer Science (``cs.wwu.edu/faculty``) -- the full teaching/track role
  roster;
* Electrical & Computer Engineering (``eece.wwu.edu/faculty-and-staff-directory``)
  -- the combined engineering directory, whose coordinator and technician cards
  are filtered out so only professor-track rows survive.

Titles that name a professor, instructor, or lecturer are kept (career and
teaching tracks included); program-manager, coordinator, technician, and
administrative-support cards are dropped.  The combined wrapper runs Computer
Science first (canonical) and collapses any cross-listed people; it is
deliberately non-authoritative so a refresh never prunes existing records.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.broadened import combine_broadened
from scrapers.configurable import NOT_AVAILABLE, _clean, _clean_name

LOGGER = logging.getLogger(__name__)

WWU_UNIVERSITY_NAME = "Western Washington University"
WWU_CS_DIRECTORY_URL = "https://cs.wwu.edu/faculty"
WWU_EECE_DIRECTORY_URL = "https://eece.wwu.edu/faculty-and-staff-directory"

WWU_DEPT_FLOORS: dict[str, int] = {
    "Computer Science": 12,
    "Electrical and Computer Engineering": 6,
}

# Careers that are faculty-track are always kept; the rest are dropped.
WWU_FACULTY_TRACK_RE = re.compile(r"\b(?:professor|instructor|lecturer)\b", re.I)


def keep_wwu_faculty(title: str) -> bool:
    """True only for professor-track roles (career and teaching tracks included)."""
    return bool(WWU_FACULTY_TRACK_RE.search(title or ""))


def parse_wwu_cards(html_text: str, base_url: str) -> list[tuple[str, str, str, str]]:
    """Return ``(name, title, email, profile_url)`` for every directory card."""
    soup = BeautifulSoup(html_text, "html.parser")
    rows: list[tuple[str, str, str, str]] = []
    for card in soup.select("div.card"):
        heading = card.select_one("h3 a[href]")
        if heading is None:
            continue
        name = _clean_name(heading.get_text(" ", strip=True))
        if not name:
            continue
        title_node = card.select_one(".job-title")
        title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
        email_anchor = card.select_one('a[href^="mailto:"]')
        email = ""
        if email_anchor is not None:
            email = _clean(email_anchor.get("href", "")[len("mailto:"):]).casefold()
        if not email:
            continue
        profile_url = NOT_AVAILABLE
        href = str(heading.get("href", "")).strip()
        if href.startswith("/") and href.casefold().startswith(("/people/", "/directory/")):
            profile_url = f"{base_url}{href}"
        rows.append((name, title, email, profile_url))
    return rows


class WWUDeptScraper(BaseUniversityScraper):
    university_name = WWU_UNIVERSITY_NAME
    department = NOT_AVAILABLE
    directory_base = ""
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
        self.faculty_count = 0

    def scrape(self) -> list[ScrapedProfessor]:
        soup = self.get_soup(self.directory_url)
        rows = parse_wwu_cards(str(soup), self.directory_base)
        kept = [(name, title, email, url) for name, title, email, url in rows if keep_wwu_faculty(title)]
        self.faculty_count = len(kept)
        if self.max_profiles is not None:
            kept = kept[: self.max_profiles]
        records = [
            ScrapedProfessor(
                name=name,
                university=self.university_name,
                department=self.department,
                title=title or NOT_AVAILABLE,
                research_interests=NOT_AVAILABLE,
                email=email,
                website_url=NOT_AVAILABLE,
                profile_url=profile_url,
                source_type=self.source_label,
            )
            for name, title, email, profile_url in kept
        ]
        floor = WWU_DEPT_FLOORS.get(self.department)
        if floor is not None and len(kept) < floor:
            self.last_error = (
                f"{self.department} returned only {len(kept)} faculty cards; "
                f"at least {floor} were expected."
            )
        return records


class WWUComputerScienceScraper(WWUDeptScraper):
    directory_url = WWU_CS_DIRECTORY_URL
    directory_base = "https://cs.wwu.edu"
    department = "Computer Science"
    source_label = (
        "Official Western Washington University Computer Science faculty directory"
    )


class WWUECEScraper(WWUDeptScraper):
    directory_url = WWU_EECE_DIRECTORY_URL
    directory_base = "https://eece.wwu.edu"
    department = "Electrical and Computer Engineering"
    source_label = (
        "Official Western Washington University Electrical & Computer Engineering "
        "faculty and staff directory"
    )


class WesternWashingtonUniversityScraper(BaseUniversityScraper):
    """Combined Western Washington University scraper (CS + ECE)."""

    university_name = WWU_UNIVERSITY_NAME
    directory_url = WWU_CS_DIRECTORY_URL
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 30,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.sub_scrapers: list[WWUDeptScraper] = [
            WWUComputerScienceScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            WWUECEScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
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
            self.last_error = "No Western Washington University faculty records were returned."
        return combined
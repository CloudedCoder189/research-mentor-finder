"""University of Oregon College of Arts and Sciences directory (Phase 3).

V9.7 Phase 3 expands beyond California with the official University of Oregon
College of Arts and Sciences directory pages for Computer Science
(``/directory/computer-science-faculty``) and Data Science
(``/directory/data-science-faculty``).

Each directory page is a server-rendered Drupal listing whose person entries
are ``div.listing__row`` blocks carrying the name and profile link
(``h2.views-field-views-field-lname a``), a primary job title
(``.views-field-job-title``), an optional secondary job title
(``.views-field-job-title2``), the email (``.views-field-email a[href^=mailto:]``)
and research keywords (``.views-field-keywords``).

The page also exposes an A-Z pager (``li.pager-alphabetical__item a``).  The
scraper reads the main page and every letter page and deduplicates by profile
slug so the roster stays complete even if the main page later paginates.
Profiles are only fetched when the listing row carries no email, because the
directory itself already supplies research keywords.

Titles are composed from the two job-title fields: the academic rank leads and
program role labels that merely end in "Faculty" (for example "Cybersecurity
Faculty") are dropped as non-academic.

The combined :class:`UniversityOfOregonScraper` runs both department scrapers
and collapses cross-listed people (someone listed under both CS and Data
Science with the same email or name) through
:func:`services.deduplication.deduplicate`.  It is deliberately not
authoritative, so a refresh never prunes existing Oregon records.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    NOT_AVAILABLE,
    _choose_email,
    _clean,
    _email_candidates,
    sanitize_research_text,
)
from services.deduplication import deduplicate

LOGGER = logging.getLogger(__name__)

UO_BASE_URL = "https://cas.uoregon.edu"
UO_CS_DIRECTORY_URL = "https://cas.uoregon.edu/directory/computer-science-faculty"
UO_DS_DIRECTORY_URL = "https://cas.uoregon.edu/directory/data-science-faculty"

UO_UNIVERSITY_NAME = "University of Oregon"

ACADEMIC_RANK_RE = re.compile(r"\b(?:professor|instructor|lecturer)\b", re.I)
FACULTY_SUFFIX_RE = re.compile(r"[Ff]aculty$")


@dataclass(slots=True)
class UODirectoryEntry:
    name: str
    title_field1: str
    title_field2: str
    email: str
    research_interests: str
    profile_url: str


@dataclass(slots=True)
class UOProfileDetails:
    email: str = ""
    research_interests: str = NOT_AVAILABLE


def compose_uo_title(title_field1: str, title_field2: str) -> str:
    """Merge the two UO job-title fields into one clean title string.

    Labels that merely end in "Faculty" (for example "Cybersecurity Faculty")
    are program tags rather than academic ranks or staff roles, so they are
    dropped.  An academic rank leads and a single program role is appended
    with `` | `` (for example "Professor | Director of Undergraduate Studies");
    two ranks are joined with ``; ``.
    """
    parts: list[str] = []
    for field in (title_field1, title_field2):
        value = _clean(field or "")
        if not value:
            continue
        if FACULTY_SUFFIX_RE.search(value) and not ACADEMIC_RANK_RE.search(value):
            continue
        parts.append(value)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    ranks = [part for part in parts if ACADEMIC_RANK_RE.search(part)]
    roles = [part for part in parts if not ACADEMIC_RANK_RE.search(part)]
    if ranks and roles:
        return " | ".join(ranks[:1] + roles[:2])
    if len(ranks) >= 2:
        return "; ".join(ranks[:2])
    return " | ".join(parts)


def parse_uo_listing_page(
    html_text: str,
    base_url: str,
) -> list[UODirectoryEntry]:
    """Extract person rows from one UO CAS directory listing page."""
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[UODirectoryEntry] = []
    seen: set[str] = set()
    for row in soup.select("div.listing__row"):
        name_anchor = row.select_one("h2 a[href]")
        if name_anchor is None:
            continue
        name = _clean(name_anchor.get_text(" ", strip=True))
        if not name:
            continue
        profile_url = urljoin(base_url, name_anchor.get("href", ""))
        key = profile_url.casefold()
        if key in seen:
            continue
        seen.add(key)

        title1_node = row.select_one(".views-field-job-title .field-content")
        title2_node = row.select_one(".views-field-job-title2 .field-content")
        email_anchor = row.select_one(".views-field-email a[href^='mailto:']")
        email = ""
        if email_anchor is not None:
            email = _clean(email_anchor.get("href", "")[len("mailto:"):])
        keywords_node = row.select_one(".views-field-keywords .field-content")
        interests = NOT_AVAILABLE
        if keywords_node is not None:
            text = _clean(keywords_node.get_text(" ", strip=True))
            if text:
                interests = sanitize_research_text(text)
        entries.append(
            UODirectoryEntry(
                name=name,
                title_field1=_clean(title1_node.get_text(" ", strip=True))
                if title1_node
                else "",
                title_field2=_clean(title2_node.get_text(" ", strip=True))
                if title2_node
                else "",
                email=email,
                research_interests=interests,
                profile_url=profile_url,
            )
        )
    return entries


def extract_uo_letter_paths(html_text: str) -> list[str]:
    """Collect the A-Z pager paths from a directory page (deduplicated)."""
    soup = BeautifulSoup(html_text, "html.parser")
    paths: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("li.pager-alphabetical__item a[href]"):
        path = anchor.get("href", "")
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def parse_uo_profile_details(html_text: str) -> UOProfileDetails:
    """Read email and a research-interests block from a UO person profile."""
    soup = BeautifulSoup(html_text, "html.parser")
    email = _choose_email(_email_candidates(soup), "", ("uoregon.edu",))
    interests = NOT_AVAILABLE
    heading = None
    for candidate in soup.find_all(["h2", "h3", "h4"]):
        if _clean(candidate.get_text(" ", strip=True)).casefold() == "research interests":
            heading = candidate
            break
    if heading is not None:
        parts: list[str] = []
        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) in {"h2", "h3", "h4"}:
                break
            text = _clean(
                sibling.get_text(" ", strip=True)
                if getattr(sibling, "name", None)
                else str(sibling)
            )
            if text and len(text) > 3:
                parts.append(text)
            if len(" ".join(parts)) > 900:
                break
        value = _clean(" ".join(parts))
        if value:
            interests = sanitize_research_text(value[:1000])
    return UOProfileDetails(email=email, research_interests=interests)


class UOCASDirectoryScraper(BaseUniversityScraper):
    """Base scraper for one University of Oregon CAS faculty directory."""

    university_name = UO_UNIVERSITY_NAME
    department = "Not publicly available"
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

    def scrape(self) -> list[ScrapedProfessor]:
        main_soup = self.get_soup(self.directory_url)
        entries = parse_uo_listing_page(str(main_soup), self.directory_url)
        seen_profiles = {entry.profile_url.casefold() for entry in entries}

        for letter_path in extract_uo_letter_paths(str(main_soup)):
            letter_url = urljoin(self.directory_url, letter_path)
            try:
                letter_soup = self.get_soup(letter_url)
            except requests.RequestException as exc:
                LOGGER.warning("UO %s letter page failed (%s): %s", self.department, letter_path, exc)
                continue
            for entry in parse_uo_listing_page(str(letter_soup), self.directory_url):
                if entry.profile_url.casefold() in seen_profiles:
                    continue
                seen_profiles.add(entry.profile_url.casefold())
                entries.append(entry)

        entries.sort(key=lambda entry: entry.name.casefold())
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking University of Oregon {self.department} entry "
                    f"{index} of {total}: {entry.name}"
                )
            email = entry.email
            research = entry.research_interests
            if not email and entry.profile_url != NOT_AVAILABLE:
                try:
                    profile_soup = self.get_soup(entry.profile_url)
                except requests.RequestException as exc:
                    LOGGER.warning(
                        "Could not inspect UO profile for %s: %s",
                        entry.name,
                        exc,
                    )
                    profile_soup = None
                if profile_soup is not None:
                    details = parse_uo_profile_details(str(profile_soup))
                    email = details.email
                    if details.research_interests != NOT_AVAILABLE:
                        research = details.research_interests
            if not email:
                continue
            title = compose_uo_title(entry.title_field1, entry.title_field2)
            if not title:
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
                        f"Official University of Oregon {self.department} "
                        "faculty directory"
                    ),
                )
            )
        return records


class UOComputerScienceScraper(UOCASDirectoryScraper):
    directory_url = UO_CS_DIRECTORY_URL
    department = "Computer Science"


class UODataScienceScraper(UOCASDirectoryScraper):
    directory_url = UO_DS_DIRECTORY_URL
    department = "Data Science"


class UniversityOfOregonScraper(BaseUniversityScraper):
    """Combined University of Oregon scraper (Computer Science + Data Science)."""

    university_name = UO_UNIVERSITY_NAME
    directory_url = UO_CS_DIRECTORY_URL
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.4,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.cs = UOComputerScienceScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.ds = UODataScienceScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.last_error = ""

    def scrape(self) -> list[ScrapedProfessor]:
        cs_records = self.cs.safe_scrape()
        ds_records = self.ds.safe_scrape()
        errors = [
            message
            for message in (self.cs.last_error, self.ds.last_error)
            if str(message or "").strip()
        ]
        if errors:
            self.last_error = " ".join(errors)
        unique = deduplicate(
            [record.as_record() for record in cs_records + ds_records]
        )
        return [ScrapedProfessor(**row) for row in unique]
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    EMAIL_RE,
    NOT_AVAILABLE,
    _clean,
    _clean_name,
    _profile_research,
    _profile_title,
    _website_from_soup,
    sanitize_research_text,
)
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)

# The department-specific page is intentionally used instead of the broad ICS
# people directory.  It publishes one bounded Computer Science faculty roster,
# then clearly separates lecturers, emeriti, and research staff.
DIRECTORY_URL = "https://cs.ics.uci.edu/faculty/"
PROFILE_PATH_RE = re.compile(r"^/people/[a-z0-9][a-z0-9-]*/?$", re.IGNORECASE)
FACULTY_STOP_HEADINGS = (
    "lecturer",
    "emeriti",
    "research scientists",
    "research scientist",
    "research associates",
    "staff",
)
FACULTY_TITLE_RE = re.compile(
    r"\b(?:Distinguished\s+Professor|Chancellor(?:'|’)?s\s+Professor|"
    r"University\s+Professor|Assistant\s+Professor(?:\s+of\s+Teaching)?|"
    r"Associate\s+Professor(?:\s+of\s+Teaching)?|Associate\s+Adjunct\s+Professor|"
    r"Adjunct\s+Professor|Professor(?:\s+of\s+Teaching)?)\b",
    re.IGNORECASE,
)
BLOCKED_ROLE_RE = re.compile(
    r"\b(?:emerit(?:us|a)|lecturer|instructor|postdoctoral|research\s+scientist|"
    r"research\s+associate|staff|administrator|manager|coordinator)\b",
    re.IGNORECASE,
)
GENERIC_EMAIL_LOCALS = {
    "info",
    "contact",
    "office",
    "admin",
    "webmaster",
    "support",
    "admissions",
    "computing",
    "help",
    "communications",
    "development",
}


@dataclass(slots=True)
class UCIDirectoryEntry:
    name: str
    title: str
    email: str
    profile_url: str


def _valid_uci_email(value: str) -> bool:
    value = value.casefold().strip(".,;:()[]{}<>\"'")
    if not EMAIL_RE.fullmatch(value) or "@" not in value:
        return False
    local, domain = value.split("@", 1)
    if local in GENERIC_EMAIL_LOCALS:
        return False
    return domain == "uci.edu" or domain.endswith(".uci.edu")


def _email_candidates_from_tag(tag: Tag) -> list[str]:
    values: list[str] = []
    for anchor in tag.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.casefold().startswith("mailto:"):
            value = href[7:].split("?", 1)[0].strip()
            if _valid_uci_email(value):
                values.append(value.casefold())
    for value in EMAIL_RE.findall(tag.get_text(" ", strip=True)):
        if _valid_uci_email(value):
            values.append(value.casefold())
    return list(dict.fromkeys(values))


def _profile_url(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, value.strip())
    parsed = urlparse(absolute)
    host = parsed.netloc.casefold()
    if not (host == "ics.uci.edu" or host.endswith(".ics.uci.edu")):
        return ""
    people_value = parse_qs(parsed.query).get("people", [""])[0].strip()
    if people_value and re.fullmatch(r"[a-z0-9][a-z0-9-]*", people_value, re.IGNORECASE):
        return absolute
    if PROFILE_PATH_RE.match(parsed.path):
        return absolute
    return ""


def _faculty_anchor_range(soup: BeautifulSoup) -> list[Tag]:
    """Return profile anchors only from the page's active Faculty section."""
    faculty_heading: Tag | None = None
    stop_heading: Tag | None = None
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        label = _clean(heading.get_text(" ", strip=True)).casefold()
        if faculty_heading is None and (
            label in {"faculty", "cs faculty", "computer science faculty"}
            or (label.endswith(" faculty") and not any(
                blocked in label for blocked in ("affiliated", "emeriti", "visiting")
            ))
        ):
            faculty_heading = heading
            continue
        if faculty_heading is not None and any(label.startswith(value) for value in FACULTY_STOP_HEADINGS):
            stop_heading = heading
            break

    tags = list(soup.find_all(True))
    start = tags.index(faculty_heading) if faculty_heading in tags else -1
    stop = tags.index(stop_heading) if stop_heading in tags else len(tags)
    anchors: list[Tag] = []
    for index, tag in enumerate(tags):
        if index <= start or index >= stop or tag.name != "a" or not tag.get("href"):
            continue
        if _profile_url(str(tag.get("href", "")), DIRECTORY_URL):
            anchors.append(tag)
    # Layout fallback: the current official page always has a Faculty heading,
    # but retaining a strict role filter is safer than returning nothing after a
    # harmless heading-style change.
    if not anchors and faculty_heading is None:
        anchors = [
            anchor
            for anchor in soup.find_all("a", href=True)
            if _profile_url(str(anchor.get("href", "")), DIRECTORY_URL)
        ]
    return anchors


def _nearest_person_card(anchor: Tag) -> Tag:
    best = anchor
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > 2200:
            break
        best = parent
        profile_links = {
            _profile_url(str(link.get("href", "")), DIRECTORY_URL)
            for link in parent.find_all("a", href=True)
        }
        profile_links.discard("")
        if (
            len(profile_links) <= 1
            and _email_candidates_from_tag(parent)
            and "computer science" in text.casefold()
            and FACULTY_TITLE_RE.search(text)
        ):
            return parent
    return best


def _name_from_card(anchor: Tag, card: Tag) -> str:
    for heading in card.find_all(["h2", "h3", "h4"], limit=6):
        candidate = _clean_name(heading.get_text(" ", strip=True))
        if _looks_like_person_name(candidate):
            return candidate
    candidate = re.sub(
        r"^\s*View\s+", "", _clean_name(anchor.get_text(" ", strip=True)), flags=re.IGNORECASE
    ).strip()
    return candidate if _looks_like_person_name(candidate) else ""


def _looks_like_person_name(value: str) -> bool:
    words = value.split()
    if not 2 <= len(words) <= 8 or len(value) > 100:
        return False
    if any(char.isdigit() for char in value) or "@" in value:
        return False
    lowered = value.casefold()
    if any(term in lowered for term in ("research scientists", "faculty", "directory", "view profile")):
        return False
    return sum(char.isalpha() for char in value) >= 5


def _title_from_card(card_text: str) -> str:
    match = FACULTY_TITLE_RE.search(card_text)
    if not match:
        return NOT_AVAILABLE
    # Keep the canonical professor role. Additional dean/chair wording remains
    # available on the profile page and can replace this value during enrichment.
    return _clean(match.group(0)).strip(" |–—-,:;")


def parse_uci_directory_html(
    html_text: str,
    page_url: str = DIRECTORY_URL,
) -> list[UCIDirectoryEntry]:
    """Parse the official UCI Computer Science Faculty section only."""
    soup = BeautifulSoup(html_text, "html.parser")
    entries: dict[str, UCIDirectoryEntry] = {}

    for anchor in _faculty_anchor_range(soup):
        profile = _profile_url(str(anchor.get("href", "")), page_url)
        if not profile:
            continue
        card = _nearest_person_card(anchor)
        card_text = _clean(card.get_text(" ", strip=True))
        if "computer science" not in card_text.casefold() or BLOCKED_ROLE_RE.search(card_text):
            continue
        title = _title_from_card(card_text)
        if title == NOT_AVAILABLE:
            continue
        emails = _email_candidates_from_tag(card)
        if not emails:
            continue
        name = _name_from_card(anchor, card)
        if not name:
            continue
        key = emails[0].casefold()
        entries[key] = UCIDirectoryEntry(
            name=name,
            title=title,
            email=emails[0],
            profile_url=profile,
        )

    return sorted(entries.values(), key=lambda row: row.name.casefold())


def parse_uci_profile_html(
    html_text: str,
    profile_url: str,
    entry: UCIDirectoryEntry,
) -> tuple[UCIDirectoryEntry, str, str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    main = soup.select_one("main") or soup
    main_soup = BeautifulSoup(str(main), "html.parser")

    title = _profile_title(main_soup, entry.name)
    if title == NOT_AVAILABLE or BLOCKED_ROLE_RE.search(title) or not FACULTY_TITLE_RE.search(title):
        title = entry.title
    email_values = _email_candidates_from_tag(main if isinstance(main, Tag) else soup)
    email = entry.email
    if entry.email.casefold() in {value.casefold() for value in email_values}:
        email = entry.email
    elif email_values:
        # The official profile is scoped to one person, but prefer the directory
        # address if it remains valid to avoid accidentally selecting footer mail.
        email = email_values[0]

    research = sanitize_research_text(_profile_research(main_soup), max_chars=1000)
    website = _website_from_soup(main_soup, profile_url, entry.name)
    source_text = _clean(main_soup.get_text(" ", strip=True))[:7000]
    enriched = UCIDirectoryEntry(entry.name, title, email, profile_url)
    return enriched, research, website, source_text


class UCIScraper(BaseUniversityScraper):
    university_name = "University of California, Irvine"
    directory_url = DIRECTORY_URL
    authoritative_roster = True
    minimum_authoritative_records = 35

    def __init__(
        self,
        request_delay: float = 0.35,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def scrape(self) -> list[ScrapedProfessor]:
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_uci_directory_html(str(directory_soup), self.directory_url)
        records: list[ScrapedProfessor] = []
        checked = 0

        for index, entry in enumerate(entries, start=1):
            checked += 1
            if self.progress_callback:
                self.progress_callback(
                    f"Checking UC Irvine profile {index} of {len(entries)}: {entry.name}"
                )
            research = NOT_AVAILABLE
            website = NOT_AVAILABLE
            source_text = ""
            enriched = entry
            try:
                profile_soup = self.get_soup(entry.profile_url)
                enriched, research, website, source_text = parse_uci_profile_html(
                    str(profile_soup), entry.profile_url, entry
                )
            except requests.RequestException as exc:
                # The official directory card still gives a valid name, title,
                # email, and stable profile URL. Preserve that record and leave
                # research for a targeted recheck instead of falling back to a
                # generic people page.
                LOGGER.warning("Could not inspect UC Irvine profile for %s: %s", entry.name, exc)

            if not enriched.email or not FACULTY_TITLE_RE.search(enriched.title):
                continue
            assessment = assess_outreach_potential(
                {
                    "title": enriched.title,
                    "research_interests": research,
                    "website_url": website,
                    "profile_url": enriched.profile_url,
                },
                source_text=source_text,
                source_url=website if website != NOT_AVAILABLE else enriched.profile_url,
            )
            records.append(
                ScrapedProfessor(
                    name=enriched.name,
                    university=self.university_name,
                    department="Computer Science",
                    title=enriched.title,
                    research_interests=research,
                    email=enriched.email,
                    website_url=website,
                    profile_url=enriched.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=(
                        "Official UCI Computer Science faculty roster and individual ICS profiles"
                    ),
                )
            )
            if self.max_profiles is not None and len(records) >= self.max_profiles:
                break

        if not records:
            self.last_error = (
                f"UC Irvine recognized {len(entries)} professor-level Computer Science faculty "
                f"entries and checked {checked}, but no complete official records were saved."
            )
        elif self.max_profiles is not None and len(records) < self.max_profiles:
            self.last_error = (
                f"UC Irvine saved {len(records)} usable record(s) after checking {checked} official "
                "Computer Science faculty entries. Lecturers, emeriti, research staff, and section "
                "headings were excluded."
            )
        return records

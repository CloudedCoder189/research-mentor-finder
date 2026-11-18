"""UC Berkeley Department of Statistics faculty (Phase 2).

V9.7 Phase 2 adds the official UC Berkeley Statistics faculty directory at
``https://statistics.berkeley.edu/people/faculty/``.  The Drupal list page
renders each current faculty member as an ``h3`` heading linking to the
person's own page under ``/people/{slug}`` (section headings such as
``Regular Faculty`` have no link and are ignored).  Each profile page carries
structured contact fields in an ``article.node--type-faculty`` element
(position, website, location, email) plus a narrative research section that is
read from the page content region with the shared research-text helpers.
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
    _concise_bio_research,
    _email_candidates,
    _looks_like_name,
    _website_from_soup,
    sanitize_research_text,
)

LOGGER = logging.getLogger(__name__)

BERKELEY_STATS_DIRECTORY_URL = "https://statistics.berkeley.edu/people/faculty/"

_PAST_OR_NON_FACULTY_MARKERS = (
    "/people/students/",
    "/people/past/",
    "/people/alumni",
    "/people/staff/",
    "/people/researchers/",
    "/people/postdocs/",
)

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)


def _email_from_field_text(value: str) -> str:
    """Extract the bare address from a field whose text prefixes ``email``."""
    match = _EMAIL_RE.search(value)
    if match:
        return match.group(0).rstrip(".,;").casefold()
    return value.casefold()


@dataclass(slots=True)
class BerkeleyStatsEntry:
    name: str
    profile_url: str


@dataclass(slots=True)
class BerkeleyStatsProfile:
    title: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    email: str = ""
    website_url: str = NOT_AVAILABLE


def _normalize(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.casefold())


def parse_berkeley_stats_directory_html(
    html_text: str,
    base_url: str = BERKELEY_STATS_DIRECTORY_URL,
) -> list[BerkeleyStatsEntry]:
    """Extract current faculty names and their profile links from the list page."""
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[BerkeleyStatsEntry] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href.startswith(("/", "http")):
            continue
        parsed_path = urljoin(base_url, href)
        if "/people/" not in parsed_path:
            continue
        lowered = parsed_path.casefold()
        if any(marker in lowered for marker in _PAST_OR_NON_FACULTY_MARKERS):
            continue
        name = _clean(anchor.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue
        if not _clean(anchor.get_text("", strip=True)) and not anchor.find("img", alt=True):
            continue
        absolute = urljoin(base_url, href)
        key = (_normalize(name), absolute)
        if key in seen:
            continue
        seen.add(key)
        entries.append(BerkeleyStatsEntry(name=name, profile_url=absolute))
    return entries


def _research_from_profile(soup: BeautifulSoup) -> str:
    """Pull the narrative research section from a Statistics profile page.

    Profiles contain labeled sections such as ``Research Expertise and
    Interests``, ``Research Interests``, or ``Research Areas`` whose contents
    (often comma-separated topics or a short paragraph) follow the label.  When
    no labeled section exists we fall back to research-sentence selection over
    the content region, and only when the text actually contains research
    language (contact-only profiles stay ``Not publicly available``).
    """
    region = soup.find(class_=re.compile(r"region-content"))
    target = region if region is not None else soup
    text = _clean(target.get_text(" ", strip=True))

    for label in (
        "Research Expertise and Interests",
        "Research Interests",
        "Research Areas",
        "Research Focus",
    ):
        index = text.find(label)
        if index < 0:
            continue
        chunk = text[index + len(label):].strip(" :–-;,")
        if not chunk:
            continue
        # Stop at the next prose sentence that starts like a bio paragraph.
        cut = re.search(r"\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+(?:is|are|was|has)\b", chunk)
        if cut and cut.start() >= 12:
            chunk = chunk[: cut.start()]
        value = sanitize_research_text(chunk)
        if value != NOT_AVAILABLE:
            return value
        break

    if not re.search(r"\b(research|statistics|studies|works on|focuses on|develops)\b", text, re.I):
        return NOT_AVAILABLE
    return _concise_bio_research(text)


def parse_berkeley_stats_profile_html(
    html_text: str,
    profile_url: str,
    name: str,
) -> BerkeleyStatsProfile:
    soup = BeautifulSoup(html_text, "html.parser")
    article = None
    for candidate in soup.find_all("article"):
        classes = candidate.get("class") or []
        if any("faculty" in cls for cls in classes):
            article = candidate
            break

    title = NOT_AVAILABLE
    email = ""
    website = NOT_AVAILABLE
    if article is not None:
        for field in article.find_all(attrs={"class": re.compile(r"\bfield\b")}):
            label = " ".join(field.get("class") or [])
            if "field-job-title" in label and title == NOT_AVAILABLE:
                value = _clean(field.get_text(" ", strip=True))
                value = _clean(
                    re.sub(
                        r"^(?:position|title|job\s*title|role|rank)\s*[:—-]?\s*",
                        "",
                        value,
                        flags=re.I,
                    )
                )
                if value and re.search(
                    r"\b(professor|lecturer|chair|director|researcher|scientist)\b",
                    value,
                    re.I,
                ):
                    title = value
            elif "field-email" in label and not email:
                email = _email_from_field_text(_clean(field.get_text(" ", strip=True)))
            elif "field-website" in label and website == NOT_AVAILABLE:
                anchor = field.find("a", href=True)
                if anchor:
                    website = urljoin(profile_url, str(anchor.get("href")))

    if not email:
        email = _choose_email(_email_candidates(soup), name, ("berkeley.edu",))
    if website == NOT_AVAILABLE:
        website = _website_from_soup(soup, profile_url, name)
    return BerkeleyStatsProfile(
        title=title,
        research_interests=_research_from_profile(soup),
        email=email,
        website_url=website,
    )


class BerkeleyStatsScraper(BaseUniversityScraper):
    university_name = "University of California, Berkeley"
    directory_url = BERKELEY_STATS_DIRECTORY_URL
    department = "Statistics"

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def scrape(self) -> list[ScrapedProfessor]:
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_berkeley_stats_directory_html(
            str(directory_soup), self.directory_url
        )
        entries.sort(key=lambda entry: entry.name.casefold())
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking UC Berkeley Statistics profile {index} of {total}: {entry.name}"
                )
            try:
                profile_soup = self.get_soup(entry.profile_url)
                profile = parse_berkeley_stats_profile_html(
                    str(profile_soup), entry.profile_url, entry.name
                )
            except requests.RequestException as exc:
                LOGGER.warning(
                    "Could not inspect UC Berkeley Statistics profile for %s: %s",
                    entry.name,
                    exc,
                )
                continue
            if not profile.email:
                continue
            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department=self.department,
                    title=profile.title,
                    research_interests=profile.research_interests,
                    email=profile.email,
                    website_url=profile.website_url,
                    profile_url=entry.profile_url,
                    source_type=(
                        "Official UC Berkeley Department of Statistics faculty "
                        "directory and profiles"
                    ),
                )
            )
        return records
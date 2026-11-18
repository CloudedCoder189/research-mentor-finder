from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None
from bs4 import BeautifulSoup, NavigableString, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    NOT_AVAILABLE,
    _clean,
    _clean_name,
    _concise_bio_research,
    _email_candidates,
    _extract_title,
    _looks_like_name,
    _obfuscated_email_candidates,
    _strict_person_email,
    _website_from_soup,
    FacultyDirectoryConfig,
)
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)
DIRECTORY_URL = "https://www.cms.caltech.edu/people/faculty"
PROFILE_RE = re.compile(r"^/people/[a-z0-9][a-z0-9_-]*/?$", re.IGNORECASE)
LEGACY_RESEARCH_SITE_OVERRIDES = {
    # The legacy host currently presents a certificate for a different name.
    # Use Aaron Ames's current official Caltech CAST profile instead of letting
    # one broken linked site cancel the entire Caltech refresh.
    "ames.caltech.edu": "https://cast.caltech.edu/people/aaron-ames",
}

PROFILE_EXCLUSIONS = {
    "/people/faculty",
    "/people/visitors",
    "/people/grads",
    "/people/graduate-students",
    "/people/postdocs",
    "/people/research-staff",
    "/people/administration",
}


@dataclass(slots=True)
class CaltechEntry:
    name: str
    profile_url: str
    title: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE


def _nearest_listing(anchor: Tag) -> Tag:
    """Find the smallest ancestor containing one Caltech person listing."""
    best: Tag = anchor
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > 2200:
            break
        best = parent
        if _extract_title(text) != NOT_AVAILABLE:
            person_links = [
                link
                for link in parent.find_all("a", href=True)
                if PROFILE_RE.match(
                    urlparse(urljoin(DIRECTORY_URL, str(link.get("href", "")))).path
                )
            ]
            unique_paths = {
                urlparse(urljoin(DIRECTORY_URL, str(link.get("href", ""))))
                .path.rstrip("/")
                .casefold()
                for link in person_links
            }
            if len(unique_paths) <= 1:
                return parent
    return best


def parse_caltech_directory_html(
    html_text: str,
    page_url: str = DIRECTORY_URL,
) -> list[CaltechEntry]:
    """Parse the official CMS faculty list using stable ``/people/<slug>`` links."""
    soup = BeautifulSoup(html_text, "html.parser")
    host = urlparse(page_url).netloc.casefold()
    entries: dict[str, CaltechEntry] = {}

    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlparse(absolute)
        path = parsed.path.rstrip("/")
        if parsed.netloc.casefold() != host or not PROFILE_RE.match(parsed.path):
            continue
        if path.casefold() in PROFILE_EXCLUSIONS:
            continue
        name = _clean_name(anchor.get_text(" ", strip=True))
        if not _looks_like_name(name):
            image = anchor.find("img")
            if isinstance(image, Tag):
                name = _clean_name(str(image.get("alt", "")))
        if not _looks_like_name(name):
            continue

        block = _nearest_listing(anchor)
        block_soup = BeautifulSoup(str(block), "html.parser")
        title = _extract_title(block.get_text(" ", strip=True))
        website = _website_from_soup(block_soup, page_url, name)
        key = absolute.rstrip("/").casefold()
        existing = entries.get(key)
        if existing is None:
            entries[key] = CaltechEntry(name, absolute, title, website)
        else:
            if existing.title == NOT_AVAILABLE and title != NOT_AVAILABLE:
                existing.title = title
            if existing.website_url == NOT_AVAILABLE and website != NOT_AVAILABLE:
                existing.website_url = website

    return sorted(entries.values(), key=lambda item: item.name.casefold())


def _caltech_person_email(soup: BeautifulSoup, name: str) -> str:
    """Return only an explicitly published Caltech address belonging to the person."""
    candidates = set(_email_candidates(soup))
    candidates.update(_obfuscated_email_candidates(str(soup)))
    return _strict_person_email(candidates, name, ("caltech.edu",))


def _text_after_heading(soup: BeautifulSoup, heading_pattern: str, max_chars: int = 1300) -> str:
    heading = soup.find(
        ["h2", "h3", "h4", "h5", "strong"],
        string=re.compile(heading_pattern, re.IGNORECASE),
    )
    if not isinstance(heading, Tag):
        return ""
    values: list[str] = []
    for node in heading.next_siblings:
        if isinstance(node, NavigableString):
            text = _clean(node)
        elif isinstance(node, Tag):
            if node.name in {"h1", "h2", "h3", "h4", "h5"}:
                break
            text = _clean(node.get_text(" ", strip=True))
        else:
            continue
        if text and text not in values:
            values.append(text)
        if sum(len(value) for value in values) >= max_chars:
            break
    return _clean(" ".join(values))[:max_chars]


def parse_caltech_profile_html(
    html_text: str,
    profile_url: str,
    fallback: CaltechEntry,
) -> tuple[CaltechEntry, str, str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    name = _clean_name(heading.get_text(" ", strip=True)) if isinstance(heading, Tag) else fallback.name
    if not _looks_like_name(name):
        name = fallback.name

    title = NOT_AVAILABLE
    for node in soup.find_all(["h4", "h5", "p", "div"], limit=100):
        candidate = _extract_title(node.get_text(" ", strip=True))
        if candidate != NOT_AVAILABLE:
            title = candidate
            break
    if title == NOT_AVAILABLE:
        title = fallback.title

    website = _website_from_soup(soup, profile_url, name)
    if website == NOT_AVAILABLE:
        website = fallback.website_url

    email = _caltech_person_email(soup, name)

    overview = _text_after_heading(soup, r"^Overview$")
    topic_text = ""
    overview_heading = soup.find(
        ["h2", "h3", "h4", "h5"], string=re.compile(r"^Overview$", re.IGNORECASE)
    )
    if isinstance(overview_heading, Tag):
        previous = overview_heading.find_previous(["h3", "h4", "h5", "p"])
        if isinstance(previous, Tag):
            value = _clean(previous.get_text(" ", strip=True))
            if 10 <= len(value) <= 500 and value.casefold() != "overview":
                topic_text = value
    research = _clean("; ".join(value for value in (topic_text, overview) if value))
    if not research:
        research = _concise_bio_research(soup.get_text(" ", strip=True))

    return (
        CaltechEntry(name, profile_url, title, website),
        email,
        research,
        _clean(soup.get_text(" ", strip=True))[:7000],
    )


def _caltech_priority(entry: CaltechEntry) -> tuple[int, int, str]:
    title = entry.title.casefold()
    website_penalty = 0 if entry.website_url != NOT_AVAILABLE else 1
    role_penalty = 0
    if any(term in title for term in ("teaching", "lecturer", "instructor")):
        role_penalty = 2
    if "emeritus" in title:
        role_penalty = 3
    return website_penalty, role_penalty, entry.name.casefold()


def _prefer_https(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host in LEGACY_RESEARCH_SITE_OVERRIDES:
        return LEGACY_RESEARCH_SITE_OVERRIDES[host]
    if parsed.scheme == "http" and host.endswith("caltech.edu"):
        return parsed._replace(scheme="https").geturl()
    return url


class CaltechScraper(BaseUniversityScraper):
    config = FacultyDirectoryConfig(
        university_name="California Institute of Technology",
        directory_url=DIRECTORY_URL,
        department="Computing and Mathematical Sciences",
        source_type="Official Caltech CMS faculty directory and linked public profiles",
        expected_email_domains=("caltech.edu",),
        city="Pasadena",
        profile_path_hints=("/people/",),
    )
    university_name = "California Institute of Technology"
    directory_url = DIRECTORY_URL

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

    def get_soup(self, url: str) -> BeautifulSoup:
        """Fetch Caltech pages with a browser transport fallback.

        Some older ``users.cms.caltech.edu`` and ``www.cs.caltech.edu`` research
        sites fail in the Windows requests certificate chain even though they
        load in a normal browser. We never disable TLS verification; instead we
        retry with curl_cffi's browser-compatible transport.
        """
        target = _prefer_https(url)
        try:
            return super().get_soup(target)
        except (requests.exceptions.SSLError, requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if curl_requests is None:
                raise
            response = curl_requests.get(
                target,
                impersonate="chrome",
                timeout=self.timeout,
                allow_redirects=True,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            if int(response.status_code) >= 400:
                raise requests.HTTPError(
                    f"HTTP {response.status_code} for {target}", response=response
                )
            return BeautifulSoup(str(response.text), "html.parser")

    def scrape(self) -> list[ScrapedProfessor]:
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_caltech_directory_html(str(directory_soup), self.directory_url)
        entries.sort(key=_caltech_priority)
        if not entries:
            self.last_error = (
                "The official Caltech CMS faculty page loaded, but no faculty profile links were recognized."
            )
            return []

        # A small refresh targets saved public-contact records, not merely the first
        # alphabetic profiles.  Check a bounded buffer because some official Caltech
        # profiles publish only an administrative assistant rather than the professor's
        # own email.
        check_limit = len(entries)
        if self.max_profiles is not None:
            check_limit = min(len(entries), max(self.max_profiles * 5, self.max_profiles))

        records: list[ScrapedProfessor] = []
        checked = 0
        profiles_with_websites = 0
        profiles_with_public_email = 0
        profiles_with_title = 0

        for index, entry in enumerate(entries[:check_limit], start=1):
            checked += 1
            if self.progress_callback:
                self.progress_callback(
                    f"Checking Caltech profile {index} of {check_limit}: {entry.name}"
                )
            enriched = entry
            email = ""
            research = NOT_AVAILABLE
            source_text = ""
            try:
                soup = self.get_soup(entry.profile_url)
                enriched, email, research, source_text = parse_caltech_profile_html(
                    str(soup), entry.profile_url, entry
                )
            except Exception as exc:
                # curl_cffi raises its own transport exceptions, which are not
                # subclasses of requests.RequestException. A single profile or
                # linked site failure must never abort the university refresh.
                LOGGER.warning("Could not inspect Caltech profile for %s: %s", entry.name, exc)

            if enriched.website_url != NOT_AVAILABLE:
                enriched.website_url = _prefer_https(enriched.website_url)
                profiles_with_websites += 1

            # Many CMS profiles link to a public research homepage rather than
            # publishing the professor's address directly. Inspect that page, while
            # rejecting assistant and generic addresses and never guessing an email.
            if not email and enriched.website_url != NOT_AVAILABLE:
                try:
                    website_soup = self.get_soup(enriched.website_url)
                    email = _caltech_person_email(website_soup, enriched.name)
                    if research == NOT_AVAILABLE:
                        research = _concise_bio_research(
                            website_soup.get_text(" ", strip=True)
                        )
                    source_text = (
                        f"{source_text} "
                        f"{_clean(website_soup.get_text(' ', strip=True))[:5000]}"
                    )
                except Exception as exc:
                    LOGGER.warning(
                        "Could not inspect Caltech research site for %s: %s",
                        enriched.name,
                        exc,
                    )

            if email:
                profiles_with_public_email += 1
            if enriched.title != NOT_AVAILABLE:
                profiles_with_title += 1
            if not email or enriched.title == NOT_AVAILABLE:
                continue

            base_record = {
                "title": enriched.title,
                "research_interests": research,
                "website_url": enriched.website_url,
                "profile_url": enriched.profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=source_text,
                source_url=(
                    enriched.website_url
                    if enriched.website_url != NOT_AVAILABLE
                    else enriched.profile_url
                ),
            )
            records.append(
                ScrapedProfessor(
                    name=enriched.name,
                    university=self.university_name,
                    department="Computing and Mathematical Sciences",
                    title=enriched.title,
                    research_interests=research,
                    email=email,
                    website_url=enriched.website_url,
                    profile_url=enriched.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=(
                        "Official Caltech CMS faculty directory, profiles, and linked public research sites"
                    ),
                )
            )
            if self.max_profiles is not None and len(records) >= self.max_profiles:
                break

        if not records:
            self.last_error = (
                f"Caltech recognized {len(entries)} faculty profiles and checked {checked}; "
                f"{profiles_with_websites} linked to research sites, "
                f"{profiles_with_public_email} exposed a professor-matching public Caltech email, "
                f"and {profiles_with_title} exposed an academic title. No email addresses were guessed, "
                "and administrative-assistant addresses were rejected."
            )
        elif self.max_profiles is not None and len(records) < self.max_profiles:
            self.last_error = (
                f"Caltech saved {len(records)} usable public-contact record(s) after checking {checked} "
                "profiles. Other checked profiles did not publish the professor's own Caltech email."
            )
        return records

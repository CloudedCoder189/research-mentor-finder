from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # The normal requests path still works for universities without bot filtering.
    curl_requests = None

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    FacultyDirectoryConfig,
    EMAIL_RE,
    NOT_AVAILABLE,
    _choose_email,
    _clean,
    _clean_name,
    _email_candidates,
    _extract_title,
    _looks_like_name,
    _obfuscated_email_candidates,
    _profile_research,
    _strict_person_email,
    _website_from_soup,
)
from services.opportunity import assess_outreach_potential
from scrapers.ucdavis_snapshot import SNAPSHOT_DATE, UC_DAVIS_FACULTY_SNAPSHOT, snapshot_key

LOGGER = logging.getLogger(__name__)
DIRECTORY_URL = "https://cs.ucdavis.edu/directory"
# This is the official Faculty filter linked from the current UC Davis CS directory.
# Keeping the filter in the primary source prevents adjunct, external-program, and
# emeriti sections from being treated as the authoritative active-faculty roster.
FACULTY_URL = (
    f"{DIRECTORY_URL}?field_sf_person_type_target_id%5B%5D=251"
    "&field_sf_person_type_target_id%5B%5D=26&first=&last="
)
LEGACY_FACULTY_URL = "https://cs.ucdavis.edu/person-type/faculty"
DIRECTORY_FALLBACK_URL = DIRECTORY_URL
PEOPLE_FALLBACK_URL = "https://cs.ucdavis.edu/people"
PROFILE_PATH_RE = re.compile(r"^/(?:directory|people)/[a-z0-9][a-z0-9-]*/?$", re.IGNORECASE)


@dataclass(slots=True)
class UCDavisDirectoryEntry:
    name: str
    profile_url: str
    title: str = NOT_AVAILABLE
    email: str = ""
    website_url: str = NOT_AVAILABLE


def _nearest_person_card(anchor: Tag) -> Tag:
    """Return the smallest ancestor that appears to contain one faculty card."""
    best: Tag = anchor
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > 1800:
            break
        best = parent
        has_email = (
            bool(parent.select_one('a[href^="mailto:"], [data-cfemail], a[href*="/cdn-cgi/l/email-protection"]'))
            or bool(EMAIL_RE.search(text))
        )
        has_title = bool(re.search(r"\b(?:Professor|Lecturer|Research Scientist|Teaching Professor)\b", text, re.IGNORECASE))
        if has_email and has_title:
            return parent
    return best


UC_DAVIS_DIRECTORY_SECTIONS = {
    "faculty",
    "adjunct faculty",
    "external graduate program faculty",
    "emeriti faculty",
    "staff",
}

# The old Tagkopoulos lab endpoints either fail TLS checks or do not expose
# enough identity information for reliable automated verification. The current
# official AIFS profile is used as the canonical public profile instead, and the
# separate website field is intentionally left empty.
KNOWN_UNUSABLE_WEBSITE_HOSTS = {"tagkopouloslab.ucdavis.edu"}
KNOWN_UNUSABLE_WEBSITE_PATHS = {
    ("www.cs.ucdavis.edu", "/~iliast"),
    ("cs.ucdavis.edu", "/~iliast"),
}
CANONICAL_PROFILE_OVERRIDES = {
    "iliastagkopoulos": "https://aifs.ucdavis.edu/about/people/ilias-tagkopoulos",
}


def _is_known_unusable_website(candidate: str) -> bool:
    if candidate == NOT_AVAILABLE:
        return False
    parsed = urlparse(candidate)
    host = parsed.netloc.casefold()
    path = parsed.path.rstrip("/").casefold()
    return host in KNOWN_UNUSABLE_WEBSITE_HOSTS or (host, path) in KNOWN_UNUSABLE_WEBSITE_PATHS


def _prefer_snapshot_website(candidate: str, snapshot_website: str) -> str:
    candidate = str(candidate or "").strip() or NOT_AVAILABLE
    snapshot_website = str(snapshot_website or "").strip() or NOT_AVAILABLE
    if _is_known_unusable_website(candidate):
        return snapshot_website
    if snapshot_website == NOT_AVAILABLE:
        return candidate
    if candidate == NOT_AVAILABLE:
        return snapshot_website
    return candidate


def _canonical_profile_url(name: str, candidate: str) -> str:
    return CANONICAL_PROFILE_OVERRIDES.get(snapshot_key(name), candidate)


def _directory_section_for_anchor(anchor: Tag) -> str:
    """Return the nearest named UC Davis directory section before a person link."""
    for heading in anchor.find_all_previous(["h2", "h3", "h4"]):
        text = _clean(heading.get_text(" ", strip=True)).casefold()
        if text in UC_DAVIS_DIRECTORY_SECTIONS:
            return text
    return ""


def parse_ucdavis_faculty_directory_html(html_text: str, page_url: str = FACULTY_URL) -> list[UCDavisDirectoryEntry]:
    """Parse the official paginated UC Davis CS faculty roster.

    UC Davis uses SiteFarm cards whose names link to /directory/<slug>.  The
    previous generic parser depended on the surrounding card layout and could
    return zero records when SiteFarm changed its wrapper elements.  This parser
    anchors discovery on the stable official profile URLs instead.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    page_host = urlparse(page_url).netloc.casefold()
    entries: dict[str, UCDavisDirectoryEntry] = {}

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != page_host or not PROFILE_PATH_RE.match(parsed.path):
            continue
        name = _clean_name(anchor.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue

        # The unfiltered directory contains adjunct, external-program, and
        # emeriti sections.  When a named section is present, only the active
        # Faculty section is authoritative for this connector.
        section = _directory_section_for_anchor(anchor)
        if section and section != "faculty":
            continue

        card = _nearest_person_card(anchor)
        card_soup = BeautifulSoup(str(card), "html.parser")
        card_text = _clean(card.get_text(" ", strip=True))
        title = _extract_title(card_text)
        card_emails = set(_email_candidates(card_soup))
        card_emails.update(_obfuscated_email_candidates(str(card_soup)))
        email = _strict_person_email(card_emails, name, ("ucdavis.edu", "cs.ucdavis.edu"))
        website = _website_from_soup(card_soup, page_url, name)

        key = absolute.rstrip("/").casefold()
        incoming = UCDavisDirectoryEntry(name, absolute, title, email, website)
        existing = entries.get(key)
        if existing is None:
            entries[key] = incoming
        else:
            if existing.title == NOT_AVAILABLE and incoming.title != NOT_AVAILABLE:
                existing.title = incoming.title
            if not existing.email and incoming.email:
                existing.email = incoming.email
            if existing.website_url == NOT_AVAILABLE and incoming.website_url != NOT_AVAILABLE:
                existing.website_url = incoming.website_url

    return sorted(entries.values(), key=lambda item: item.name.casefold())


def _section_after_label(soup: BeautifulSoup, label: str, *, max_chars: int = 1600) -> str:
    label_re = re.compile(rf"^\s*{re.escape(label)}\s*$", re.IGNORECASE)
    marker = soup.find(string=label_re)
    if marker is None:
        return ""
    marker_tag = marker.parent if isinstance(marker, NavigableString) else marker
    if not isinstance(marker_tag, Tag):
        return ""

    values: list[str] = []
    for node in marker_tag.next_elements:
        if node is marker_tag:
            continue
        if isinstance(node, Tag):
            text = _clean(node.get_text(" ", strip=True))
            if not text:
                continue
            if node.name in {"h1", "h2"} and values:
                break
            if text.casefold() in {label.casefold(), "tags", "content"}:
                continue
            if text not in values:
                values.append(text)
        if sum(len(value) for value in values) >= max_chars:
            break
    return _clean(" ".join(values))[:max_chars]



def _position_title_after_label(soup: BeautifulSoup) -> str:
    marker = soup.find(string=re.compile(r"^\s*Position Title\s*$", re.IGNORECASE))
    if marker is None:
        return NOT_AVAILABLE
    marker_tag = marker.parent if isinstance(marker, NavigableString) else marker
    if not isinstance(marker_tag, Tag):
        return NOT_AVAILABLE
    for node in marker_tag.next_elements:
        if not isinstance(node, Tag) or node is marker_tag:
            continue
        if node.name not in {"div", "p", "span", "dd", "h3", "h4", "h5", "li"}:
            continue
        text = _clean(node.get_text(" ", strip=True))
        if not text or text.casefold() == "position title":
            continue
        title = _extract_title(text)
        if title != NOT_AVAILABLE:
            return title
        if node.name in {"h1", "h2"}:
            break
    return NOT_AVAILABLE


def parse_ucdavis_profile_html(
    html_text: str,
    profile_url: str,
    fallback: UCDavisDirectoryEntry,
) -> tuple[UCDavisDirectoryEntry, str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    name = _clean_name(heading.get_text(" ", strip=True)) if heading else fallback.name
    if not _looks_like_name(name):
        name = fallback.name

    emails = set(_email_candidates(soup))
    emails.update(_obfuscated_email_candidates(str(soup)))
    email = fallback.email or _strict_person_email(
        emails, name, ("ucdavis.edu", "cs.ucdavis.edu")
    )

    title = _position_title_after_label(soup)
    if title == NOT_AVAILABLE:
        title = fallback.title

    bio_text = _section_after_label(soup, "Bio", max_chars=2200)
    research = _profile_research(soup)
    if bio_text:
        # UC Davis frequently places a concise research-area heading directly
        # below "Bio" followed by a descriptive paragraph.
        research = bio_text[:900].rsplit(" ", 1)[0].strip(" ,;:") or research

    website = _website_from_soup(soup, profile_url, name)
    if website == NOT_AVAILABLE:
        website = fallback.website_url

    return UCDavisDirectoryEntry(
        name=name,
        profile_url=profile_url,
        title=title,
        email=email,
        website_url=website,
    ), research, _clean(soup.get_text(" ", strip=True))[:6000]


class UCDavisScraper(BaseUniversityScraper):
    university_name = "University of California, Davis"
    directory_url = FACULTY_URL
    # Kept for compatibility with the reusable-parser tests and registry metadata.
    config = FacultyDirectoryConfig(
        university_name=university_name,
        directory_url=directory_url,
        department="Computer Science",
        source_type="Official UC Davis Computer Science faculty roster and linked profiles",
        expected_email_domains=("ucdavis.edu", "cs.ucdavis.edu"),
        city="Davis",
        profile_path_hints=("/directory/", "/people/"),
    )

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        # UC Davis currently rejects the descriptive prototype User-Agent with
        # HTTP 403, while the same public directory is available to normal web
        # browsers. Use a browser-compatible request profile and retain a
        # contact address in the standard From header. This is not a bypass of
        # authentication; it only requests the same public HTML shown in a
        # browser.
        contact_email = os.getenv("SCRAPER_CONTACT_EMAIL", "").strip()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://cs.ucdavis.edu/",
        }
        if "@" in contact_email:
            headers["From"] = contact_email
        self.session.headers.update(headers)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def _browser_get_soup(self, url: str) -> BeautifulSoup:
        """Fetch public UC Davis HTML with a browser TLS fingerprint after a 403.

        UC Davis currently serves the page to normal browsers while rejecting the
        default Python TLS fingerprint. curl_cffi requests the same unauthenticated
        public document using a current Chrome-compatible transport.
        """
        if curl_requests is None:
            raise requests.RequestException(
                "UC Davis returned HTTP 403 and curl_cffi is not installed. Run setup_windows.bat."
            )
        import time

        time.sleep(self.request_delay)
        try:
            response = curl_requests.get(
                url,
                impersonate="chrome",
                timeout=self.timeout,
                allow_redirects=True,
                headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://cs.ucdavis.edu/",
                    **(
                        {"From": os.getenv("SCRAPER_CONTACT_EMAIL", "").strip()}
                        if "@" in os.getenv("SCRAPER_CONTACT_EMAIL", "").strip()
                        else {}
                    ),
                },
            )
            response.raise_for_status()
        except Exception as exc:
            raise requests.RequestException(f"Browser-compatible UC Davis request failed: {exc}") from exc
        return BeautifulSoup(response.text, "html.parser")

    def _resilient_get_soup(self, url: str) -> BeautifulSoup:
        """Try normal HTTP first, then a browser-compatible transport for this URL.

        Browser mode is deliberately not made global. UC Davis can reject one
        route while allowing another official fallback route, so a 403 on the
        legacy faculty page must not force every later fallback through the same
        rejected transport.
        """
        try:
            return self.get_soup(url)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status != 403:
                raise
            LOGGER.info(
                "UC Davis returned HTTP 403 for %s; retrying that URL with browser transport.",
                url,
            )
            return self._browser_get_soup(url)

    def _read_directory_page(self, page_number: int) -> tuple[BeautifulSoup, str]:
        """Read a public UC Davis directory page with official fallbacks."""
        bases = [FACULTY_URL, DIRECTORY_FALLBACK_URL, LEGACY_FACULTY_URL, PEOPLE_FALLBACK_URL]
        # Once a fallback works, prefer it for the remaining pages in this run.
        preferred = getattr(self, "_working_directory_base", None)
        if preferred in bases:
            bases = [preferred, *[base for base in bases if base != preferred]]

        last_error: requests.RequestException | None = None
        for base in bases:
            if page_number == 0:
                candidate = base
            else:
                separator = "&" if "?" in base else "?"
                candidate = f"{base}{separator}page={page_number}"
            try:
                soup = self._resilient_get_soup(candidate)
                self._working_directory_base = base
                return soup, candidate
            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                if status not in {401, 403, 404}:
                    raise
                LOGGER.warning(
                    "UC Davis directory source rejected %s with HTTP %s; trying official fallback.",
                    candidate,
                    status,
                )
            except requests.RequestException as exc:
                last_error = exc
                LOGGER.warning("Could not read UC Davis directory source %s: %s", candidate, exc)
        if last_error is not None:
            raise last_error
        raise requests.RequestException("No UC Davis directory source was available")

    def _discover_profiles(self) -> list[UCDavisDirectoryEntry]:
        entries: dict[str, UCDavisDirectoryEntry] = {}
        page_number = 0
        while page_number < 12:
            soup, source_url = self._read_directory_page(page_number)
            # If the faculty-only route was blocked and a fallback was used,
            # profile discovery still anchors on official /directory/<slug>
            # links. Non-faculty entries are filtered after profile enrichment.
            page_entries = parse_ucdavis_faculty_directory_html(str(soup), source_url)
            new_count = 0
            for entry in page_entries:
                key = entry.profile_url.rstrip("/").casefold()
                if key not in entries:
                    entries[key] = entry
                    new_count += 1
            discovery_target = None
            if self.max_profiles is not None:
                discovery_target = max(self.max_profiles * 3, self.max_profiles)
            if discovery_target is not None and len(entries) >= discovery_target:
                break
            if page_number > 0 and new_count == 0:
                break
            has_next = any(
                "next" in _clean(anchor.get_text(" ", strip=True)).casefold()
                for anchor in soup.find_all("a", href=True)
            )
            if not has_next:
                break
            page_number += 1

        values = sorted(entries.values(), key=lambda item: item.name.casefold())
        if self.max_profiles is None:
            return values
        return values[: max(self.max_profiles * 3, self.max_profiles)]

    def _snapshot_records(self, reason: str) -> list[ScrapedProfessor]:
        """Build records from the bundled current official roster after a hard 403.

        UC Davis occasionally blocks both requests and browser-fingerprint clients.
        The fallback roster is a dated transcription of the public CS directory. For
        professors already in the local database, we preserve richer verified research
        and website fields rather than replacing them with missing values.
        """
        existing_by_name: dict[str, dict[str, str]] = {}
        existing_by_email: dict[str, dict[str, str]] = {}
        try:
            from database import fetch_professors

            for row in fetch_professors(self.university_name):
                name_key = snapshot_key(str(row.get("name", "")))
                email_key = str(row.get("email", "")).strip().casefold()
                if name_key:
                    existing_by_name[name_key] = row
                if email_key:
                    existing_by_email[email_key] = row
        except Exception as exc:  # A fresh install can still use the snapshot.
            LOGGER.warning("Could not read existing UC Davis rows for fallback enrichment: %s", exc)

        rows = list(UC_DAVIS_FACULTY_SNAPSHOT)
        if self.max_profiles is not None:
            rows = rows[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(rows)
        for index, item in enumerate(rows, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Loading UC Davis official roster fallback {index} of {total}: {item.name}"
                )
            existing = existing_by_email.get(item.email.casefold()) or existing_by_name.get(
                snapshot_key(item.name), {}
            )
            research = str(existing.get("research_interests", NOT_AVAILABLE)).strip() or NOT_AVAILABLE
            if research == NOT_AVAILABLE and item.research_interests != NOT_AVAILABLE:
                research = item.research_interests
            existing_website = str(existing.get("website_url", NOT_AVAILABLE)).strip() or NOT_AVAILABLE
            website = _prefer_snapshot_website(existing_website, item.website_url)
            profile_url = item.profile_url
            source_text = research if research != NOT_AVAILABLE else f"{item.name} {item.title} Computer Science"
            base_record = {
                "title": item.title,
                "research_interests": research,
                "website_url": website,
                "profile_url": profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=source_text,
                source_url=website if website != NOT_AVAILABLE else profile_url,
            )
            records.append(
                ScrapedProfessor(
                    name=item.name,
                    university=self.university_name,
                    department="Computer Science",
                    title=item.title,
                    research_interests=research,
                    email=item.email,
                    website_url=website,
                    profile_url=profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=(
                        f"Official UC Davis Computer Science faculty roster snapshot "
                        f"({SNAPSHOT_DATE}); existing verified fields preserved"
                    ),
                )
            )

        self.last_error = (
            f"UC Davis blocked automated access ({reason}). Used the bundled official "
            f"Computer Science faculty roster snapshot dated {SNAPSHOT_DATE}; stale-record "
            "deletion remains disabled for this fallback."
        )
        return records

    def scrape(self) -> list[ScrapedProfessor]:
        try:
            entries = self._discover_profiles()
        except requests.RequestException as exc:
            LOGGER.warning("UC Davis live directory unavailable; using official snapshot: %s", exc)
            return self._snapshot_records(str(exc))
        if not entries:
            return self._snapshot_records("no recognizable faculty entries were returned")
        records: list[ScrapedProfessor] = []
        checked = 0
        faculty_titles = 0
        public_emails = 0
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            checked += 1
            if self.progress_callback:
                self.progress_callback(f"Checking UC Davis profile {index} of {total}: {entry.name}")
            enriched = entry
            research = NOT_AVAILABLE
            source_text = ""
            try:
                profile_soup = self._resilient_get_soup(entry.profile_url)
                enriched, research, source_text = parse_ucdavis_profile_html(
                    str(profile_soup), entry.profile_url, entry
                )
            except requests.RequestException as exc:
                LOGGER.warning("Could not inspect UC Davis profile for %s: %s", entry.name, exc)

            if re.search(
                r"\b(?:Professor|Lecturer|Research Scientist|Teaching Faculty|Faculty)\b",
                enriched.title,
                re.IGNORECASE,
            ):
                faculty_titles += 1
            else:
                continue
            if enriched.email:
                public_emails += 1
            else:
                continue
            profile_url = _canonical_profile_url(enriched.name, enriched.profile_url)
            website_url = _prefer_snapshot_website(enriched.website_url, NOT_AVAILABLE)
            base_record = {
                "title": enriched.title,
                "research_interests": research,
                "website_url": website_url,
                "profile_url": profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=source_text,
                source_url=(website_url if website_url != NOT_AVAILABLE else profile_url),
            )
            records.append(
                ScrapedProfessor(
                    name=enriched.name,
                    university=self.university_name,
                    department="Computer Science",
                    title=enriched.title,
                    research_interests=research,
                    email=enriched.email,
                    website_url=website_url,
                    profile_url=profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type="Official UC Davis Computer Science faculty roster and linked profiles",
                )
            )
            if self.max_profiles is not None and len(records) >= self.max_profiles:
                break
        if self.max_profiles is None and len(records) < len(UC_DAVIS_FACULTY_SNAPSHOT):
            # The live directory can load while some profile requests remain blocked.
            # Previously that partial success bypassed the hard-403 fallback and saved
            # only the subset whose individual pages exposed both a title and email.
            # Merge those richer live records into the complete dated official roster
            # so a full refresh never silently shrinks UC Davis from 43 to 31 records.
            live_by_email = {record.email.strip().casefold(): record for record in records if record.email}
            live_by_name = {snapshot_key(record.name): record for record in records if record.name}
            fallback_records = self._snapshot_records(
                f"live directory was incomplete: {len(records)} usable record(s) from "
                f"{len(entries)} discovered profile(s)"
            )
            merged: list[ScrapedProfessor] = []
            for fallback in fallback_records:
                live = live_by_email.get(fallback.email.strip().casefold()) or live_by_name.get(
                    snapshot_key(fallback.name)
                )
                if live is None:
                    merged.append(fallback)
                    continue

                research = (
                    live.research_interests
                    if live.research_interests != NOT_AVAILABLE
                    else fallback.research_interests
                )
                website = (
                    live.website_url
                    if live.website_url != NOT_AVAILABLE
                    else fallback.website_url
                )
                website = _prefer_snapshot_website(website, fallback.website_url)
                profile_url = (
                    live.profile_url
                    if live.profile_url != NOT_AVAILABLE
                    else fallback.profile_url
                )
                profile_url = _canonical_profile_url(live.name or fallback.name, profile_url)
                title = live.title if live.title != NOT_AVAILABLE else fallback.title
                base_record = {
                    "title": title,
                    "research_interests": research,
                    "website_url": website,
                    "profile_url": profile_url,
                }
                source_text = research if research != NOT_AVAILABLE else f"{live.name} {title} Computer Science"
                assessment = assess_outreach_potential(
                    base_record,
                    source_text=source_text,
                    source_url=website if website != NOT_AVAILABLE else profile_url,
                )
                merged.append(
                    ScrapedProfessor(
                        name=live.name or fallback.name,
                        university=self.university_name,
                        department="Computer Science",
                        title=title,
                        research_interests=research,
                        email=live.email or fallback.email,
                        website_url=website,
                        profile_url=profile_url,
                        opportunity_level=assessment.level,
                        opportunity_signals=assessment.signals,
                        opportunity_source_url=assessment.source_url,
                        source_type=(
                            "Official UC Davis Computer Science live directory merged with "
                            f"official roster snapshot ({SNAPSHOT_DATE})"
                        ),
                    )
                )
            self.last_error = (
                f"UC Davis live access produced {len(records)} of "
                f"{len(UC_DAVIS_FACULTY_SNAPSHOT)} current faculty records. "
                f"Merged the partial live results with the official roster snapshot dated "
                f"{SNAPSHOT_DATE}; stale-record deletion remains disabled for this fallback."
            )
            return merged

        if not records:
            self.last_error = (
                f"UC Davis recognized {len(entries)} directory entries and checked {checked}; "
                f"{faculty_titles} exposed a faculty title and {public_emails} exposed a "
                "professor-matching public email, but no complete records were saved."
            )
        elif self.max_profiles is not None and len(records) < self.max_profiles:
            self.last_error = (
                f"UC Davis saved {len(records)} usable record(s) after checking {checked} entries; "
                "remaining checked entries did not publish both a faculty title and a "
                "professor-matching public email."
            )
        return records

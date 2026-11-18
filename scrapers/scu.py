from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    NOT_AVAILABLE,
    _choose_email,
    _clean,
    _clean_name,
    _concise_bio_research,
    _email_candidates,
    _extract_labeled_research,
    _extract_title,
    _looks_like_name,
    _normalize,
    _obfuscated_email_candidates,
    _strict_person_email,
    _website_from_soup,
    FacultyDirectoryConfig,
)
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)
DIRECTORY_URL = (
    "https://www.scu.edu/engineering/academic-programs/"
    "department-of-computer-engineering/faculty--staff/"
)
CONTACT_DIRECTORY_URL = (
    "https://www.scu.edu/engineering/academic-programs/"
    "department-of-computer-engineering/faculty--staff-directory/"
)
PROFILE_RE = re.compile(r"^/engineering/faculty/[a-z0-9][a-z0-9-]*/?$", re.IGNORECASE)
ACADEMIC_TITLE_RE = re.compile(
    r"\b(?:Distinguished |Endowed |Research |Teaching |Assistant |Associate )*"
    r"(?:Professor|Lecturer|Instructor|Faculty|Chair)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class SCUEntry:
    name: str
    profile_url: str
    title: str = NOT_AVAILABLE


@dataclass(slots=True)
class SCUContact:
    name: str
    email: str
    title: str = NOT_AVAILABLE
    profile_url: str = NOT_AVAILABLE


def _nearest_listing(anchor: Tag, *, max_chars: int = 1600) -> Tag:
    best: Tag = anchor
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > max_chars:
            break
        best = parent
        person_links = [
            link
            for link in parent.find_all("a", href=True)
            if PROFILE_RE.match(
                urlparse(urljoin(DIRECTORY_URL, str(link.get("href", "")))).path
            )
        ]
        unique = {
            urlparse(urljoin(DIRECTORY_URL, str(link.get("href", ""))))
            .path.rstrip("/")
            .casefold()
            for link in person_links
        }
        if (_extract_title(text) != NOT_AVAILABLE or _email_candidates(BeautifulSoup(str(parent), "html.parser"))) and len(unique) <= 1:
            return parent
    return best


def _name_from_profile_anchor(anchor: Tag, absolute_url: str) -> str:
    values = [_clean_name(anchor.get_text(" ", strip=True))]
    image = anchor.find("img")
    if isinstance(image, Tag):
        values.append(_clean_name(str(image.get("alt", ""))))
    block = _nearest_listing(anchor)
    for heading in block.find_all(["h2", "h3", "h4", "h5"], limit=5):
        values.append(_clean_name(heading.get_text(" ", strip=True)))
    for value in values:
        if _looks_like_name(value):
            return value

    slug = urlparse(absolute_url).path.rstrip("/").split("/")[-1]
    parts = [part for part in slug.split("-") if part]
    if len(parts) >= 2:
        # SCU profile slugs normally use last-first ordering.
        candidate = " ".join([*parts[1:], parts[0]]).title()
        if _looks_like_name(candidate):
            return candidate
    return ""


def parse_scu_directory_html(html_text: str, page_url: str = DIRECTORY_URL) -> list[SCUEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    host = urlparse(page_url).netloc.casefold()
    entries: dict[str, SCUEntry] = {}
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(page_url, str(anchor.get("href", "")).strip())
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() != host or not PROFILE_RE.match(parsed.path):
            continue
        name = _name_from_profile_anchor(anchor, absolute)
        if not name:
            continue
        block = _nearest_listing(anchor)
        title = _extract_title(block.get_text(" ", strip=True))
        key = absolute.rstrip("/").casefold()
        current = entries.get(key)
        if current is None:
            entries[key] = SCUEntry(name, absolute, title)
        elif current.title == NOT_AVAILABLE and title != NOT_AVAILABLE:
            current.title = title
    return sorted(entries.values(), key=lambda item: item.name.casefold())


def _contact_name_from_block(block: Tag, profile_url: str = "") -> str:
    values: list[str] = []
    for selector in (".name", ".person-name", ".faculty-name", "h2", "h3", "h4", "h5", "strong"):
        for node in block.select(selector)[:4]:
            values.append(_clean_name(node.get_text(" ", strip=True)))
    for anchor in block.find_all("a", href=True, limit=8):
        absolute = urljoin(CONTACT_DIRECTORY_URL, str(anchor.get("href", "")))
        if PROFILE_RE.match(urlparse(absolute).path):
            values.append(_name_from_profile_anchor(anchor, absolute))
    for value in values:
        if _looks_like_name(value):
            return value
    if profile_url:
        slug = urlparse(profile_url).path.rstrip("/").split("/")[-1]
        pieces = [piece for piece in slug.split("-") if piece]
        if len(pieces) >= 2:
            value = " ".join([*pieces[1:], pieces[0]]).title()
            if _looks_like_name(value):
                return value
    return ""


def _smallest_contact_block(node: Tag) -> Tag:
    best = node
    for parent in node.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > 1800:
            break
        best = parent
        soup = BeautifulSoup(str(parent), "html.parser")
        emails = _email_candidates(soup) | _obfuscated_email_candidates(str(parent))
        title = _extract_title(text)
        if emails and title != NOT_AVAILABLE:
            return parent
    return best


def parse_scu_contact_directory_html(
    html_text: str,
    page_url: str = CONTACT_DIRECTORY_URL,
) -> list[SCUContact]:
    """Parse SCU's official contact directory.

    The visual faculty roster links to profiles, but some profiles do not expose a
    public email.  SCU's separate official faculty/staff directory publishes those
    professional addresses.  Records are accepted only when the address local part
    resembles the person, which rejects department and staff mailboxes.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    candidate_nodes: list[Tag] = []
    candidate_nodes.extend(soup.select('a[href^="mailto:"]'))
    for text_node in soup.find_all(string=re.compile(r"\b(?:at|@)\b", re.IGNORECASE)):
        if isinstance(text_node.parent, Tag):
            candidate_nodes.append(text_node.parent)

    contacts: dict[str, SCUContact] = {}
    seen_blocks: set[int] = set()
    for node in candidate_nodes:
        block = _smallest_contact_block(node)
        marker = id(block)
        if marker in seen_blocks:
            continue
        seen_blocks.add(marker)

        profile_url = NOT_AVAILABLE
        for anchor in block.find_all("a", href=True):
            absolute = urljoin(page_url, str(anchor.get("href", "")).strip())
            if PROFILE_RE.match(urlparse(absolute).path):
                profile_url = absolute
                break
        name = _contact_name_from_block(
            block,
            "" if profile_url == NOT_AVAILABLE else profile_url,
        )
        if not name:
            continue
        emails = _email_candidates(BeautifulSoup(str(block), "html.parser"))
        emails.update(_obfuscated_email_candidates(str(block)))
        email = _strict_person_email(emails, name, ("scu.edu",))
        if not email:
            continue
        title = _extract_title(block.get_text(" ", strip=True))
        if title == NOT_AVAILABLE or not ACADEMIC_TITLE_RE.search(title):
            continue
        key = _normalize(name)
        existing = contacts.get(key)
        incoming = SCUContact(name, email, title, profile_url)
        if existing is None:
            contacts[key] = incoming
        else:
            if existing.title == NOT_AVAILABLE and title != NOT_AVAILABLE:
                existing.title = title
            if existing.profile_url == NOT_AVAILABLE and profile_url != NOT_AVAILABLE:
                existing.profile_url = profile_url
    return sorted(contacts.values(), key=lambda row: row.name.casefold())


def parse_scu_profile_html(
    html_text: str,
    profile_url: str,
    fallback: SCUEntry,
) -> tuple[SCUEntry, str, str, str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    heading = soup.find("h1")
    name = _clean_name(heading.get_text(" ", strip=True)) if isinstance(heading, Tag) else fallback.name
    if not _looks_like_name(name):
        name = fallback.name

    main = soup.find("main") or soup
    page_text = _clean(main.get_text(" ", strip=True))

    title = fallback.title
    if title == NOT_AVAILABLE:
        # Search the profile content near the name before considering the full page,
        # which contains navigation phrases such as "Department Chair".
        for node in main.find_all(["h3", "h4", "h5", "p", "div"], limit=100):
            candidate = _extract_title(node.get_text(" ", strip=True))
            if candidate != NOT_AVAILABLE and ACADEMIC_TITLE_RE.search(candidate):
                title = candidate
                break

    public_emails = set(_email_candidates(main if isinstance(main, BeautifulSoup) else BeautifulSoup(str(main), "html.parser")))
    public_emails.update(_obfuscated_email_candidates(str(main)))
    email = _strict_person_email(public_emails, name, ("scu.edu",))
    if not email:
        candidate = _choose_email(_email_candidates(soup), name, ("scu.edu",))
        if candidate == _strict_person_email({candidate}, name, ("scu.edu",)):
            email = candidate

    website = _website_from_soup(soup, profile_url, name)
    research = _extract_labeled_research(page_text)
    if research == NOT_AVAILABLE:
        research = _concise_bio_research(page_text)
    return SCUEntry(name, profile_url, title), email, website, research, page_text[:7000]


class SCUScraper(BaseUniversityScraper):
    config = FacultyDirectoryConfig(
        university_name="Santa Clara University",
        directory_url=DIRECTORY_URL,
        department="Computer Science and Engineering",
        source_type="Official SCU Computer Science and Engineering faculty directory and profiles",
        expected_email_domains=("scu.edu",),
        city="Santa Clara",
        profile_path_hints=("/engineering/faculty/",),
    )
    university_name = "Santa Clara University"
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

    def _contact_map(self) -> dict[str, SCUContact]:
        try:
            soup = self.get_soup(CONTACT_DIRECTORY_URL)
        except requests.RequestException as exc:
            LOGGER.warning("Could not read SCU contact directory: %s", exc)
            return {}
        return {
            _normalize(row.name): row
            for row in parse_scu_contact_directory_html(str(soup), CONTACT_DIRECTORY_URL)
        }

    def scrape(self) -> list[ScrapedProfessor]:
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_scu_directory_html(str(directory_soup), self.directory_url)
        contacts = self._contact_map()

        # Add official contact-directory people that the visual roster failed to link.
        existing_names = {_normalize(entry.name) for entry in entries}
        for key, contact in contacts.items():
            if key in existing_names or contact.profile_url == NOT_AVAILABLE:
                continue
            entries.append(SCUEntry(contact.name, contact.profile_url, contact.title))
            existing_names.add(key)

        # Faculty first; lecturers remain eligible on a full refresh.
        entries.sort(
            key=lambda row: (
                any(term in row.title.casefold() for term in ("lecturer", "instructor", "emeritus")),
                row.name.casefold(),
            )
        )
        if not entries:
            self.last_error = (
                "The official SCU CSE pages loaded, but no faculty profile links were recognized."
            )
            return []

        records: list[ScrapedProfessor] = []
        checked = 0
        profiles_with_email = 0
        profiles_with_title = 0
        check_limit = len(entries)
        if self.max_profiles is not None:
            check_limit = min(len(entries), max(self.max_profiles * 4, self.max_profiles))

        for index, entry in enumerate(entries[:check_limit], start=1):
            checked += 1
            if self.progress_callback:
                self.progress_callback(f"Checking SCU profile {index} of {len(entries)}: {entry.name}")
            enriched = entry
            email = ""
            website = NOT_AVAILABLE
            research = NOT_AVAILABLE
            source_text = ""
            try:
                soup = self.get_soup(entry.profile_url)
                enriched, email, website, research, source_text = parse_scu_profile_html(
                    str(soup), entry.profile_url, entry
                )
            except requests.RequestException as exc:
                LOGGER.warning("Could not inspect SCU profile for %s: %s", entry.name, exc)

            contact = contacts.get(_normalize(enriched.name)) or contacts.get(_normalize(entry.name))
            if contact is not None:
                email = email or contact.email
                if enriched.title == NOT_AVAILABLE:
                    enriched.title = contact.title

            if email:
                profiles_with_email += 1
            if enriched.title != NOT_AVAILABLE:
                profiles_with_title += 1
            if not email or enriched.title == NOT_AVAILABLE:
                continue
            if not ACADEMIC_TITLE_RE.search(enriched.title):
                continue

            base_record = {
                "title": enriched.title,
                "research_interests": research,
                "website_url": website,
                "profile_url": enriched.profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=source_text,
                source_url=website if website != NOT_AVAILABLE else enriched.profile_url,
            )
            records.append(
                ScrapedProfessor(
                    name=enriched.name,
                    university=self.university_name,
                    department="Computer Science and Engineering",
                    title=enriched.title,
                    research_interests=research,
                    email=email,
                    website_url=website,
                    profile_url=enriched.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=(
                        "Official SCU Computer Science and Engineering faculty roster, "
                        "contact directory, and linked profiles"
                    ),
                )
            )
            if self.max_profiles is not None and len(records) >= self.max_profiles:
                break

        if not records:
            self.last_error = (
                f"SCU recognized {len(entries)} faculty profile link(s), found {len(contacts)} "
                f"academic contact-directory record(s), and checked {checked}; "
                f"{profiles_with_email} exposed a professor-matching public email and "
                f"{profiles_with_title} exposed an academic title, but no complete records were saved."
            )
        elif self.max_profiles is not None and len(records) < self.max_profiles:
            self.last_error = (
                f"SCU saved {len(records)} usable record(s) after checking {checked} profiles and "
                f"{len(contacts)} contact-directory entries; remaining people did not publish both "
                "a professor-matching email and academic title."
            )
        return records

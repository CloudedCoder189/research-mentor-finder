"""UC San Diego Electrical and Computer Engineering faculty (Phase 2).

V9.7 Phase 2 broadens UC San Diego with the official ECE faculty directory at
``https://www.ece.ucsd.edu/people/faculty``.  The directory is a server-rendered
Drupal page whose person cards are ``h2`` headings carrying the public email
inline and linking to the faculty member's Jacobs School of Engineering profile
(legacy ``.../faculty_bios/index.sfe?fmp_recid=N`` URLs redirect to the current
``/faculty/profile?id=N`` pages).  Those profiles supply the position title and
a narrative research summary.

The scraper reuses the shared person-name/email/website helpers from
:mod:`scrapers.configurable`, so shared or role mailbox addresses (for example
the chancellor's office address on the ECE founding roster) never become
professor records.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import (
    NOT_AVAILABLE,
    TITLE_PATTERN,
    _choose_email,
    _clean,
    _concise_bio_research,
    _email_candidates,
    _looks_like_name,
    _normalize,
    _website_from_soup,
    sanitize_research_text,
)

LOGGER = logging.getLogger(__name__)

UCSD_ECE_DIRECTORY_URL = "https://www.ece.ucsd.edu/people/faculty"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
JACOBS_HINTS = (
    "jacobsschool.ucsd.edu/faculty",
    "jacobsschool.ucsd.edu/people",
    "faculty_bios",
)


@dataclass(slots=True)
class UCSDECEEntry:
    name: str
    title: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    email: str = ""
    profile_url: str = NOT_AVAILABLE


@dataclass(slots=True)
class UCSDJacobsDetails:
    title: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    email: str = ""
    website_url: str = NOT_AVAILABLE


def _heading_name(value: str) -> str:
    cleaned = _clean(value)
    cleaned = re.sub(r"^(\d+)\s+\.\s*", "", cleaned).strip()
    return cleaned


def _heading_container(heading: Tag) -> Tag:
    for parent_name in ("tr", "article", "li", "section", "div"):
        parent = heading.find_parent(parent_name)
        if parent is not None and len(_clean(parent.get_text(" ", strip=True))) <= 3500:
            return parent
    return heading


def _profile_link_from_block(block: Tag, base_url: str, name: str) -> str:
    name_key = _normalize(name)
    candidates: list[tuple[int, str]] = []
    for anchor in block.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.lower().startswith(("mailto:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        lowered = absolute.casefold()
        if not any(fragment in lowered for fragment in JACOBS_HINTS):
            continue
        parsed_label = _clean(anchor.get_text(" ", strip=True))
        label_key = _normalize(parsed_label)
        score = 6
        if name_key and (name_key in label_key or label_key in name_key):
            score += 10
        if "faculty_bios" in lowered or "faculty/profile" in lowered:
            score += 4
        # Prefer links that carry a valid record id over template placeholders.
        if re.search(r"(?:fmp_recid|id)=\s*\d", lowered):
            score += 8
        elif re.search(r"(?:fmp_recid|id)=\s*$", lowered):
            score -= 12
        if lowered.endswith((".pdf", ".jpg", ".png", ".doc", ".docx")):
            score -= 20
        candidates.append((score, absolute))
    if not candidates:
        return NOT_AVAILABLE
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1]


def parse_ucsd_ece_directory_html(
    html_text: str,
    base_url: str = UCSD_ECE_DIRECTORY_URL,
) -> list[UCSDECEEntry]:
    """Extract ECE faculty cards from the official directory page.

    Person names are ``h2`` headings (the page also uses ``h2`` for a few
    navigation labels and section headings like ``Faculty``; those are rejected
    by the person-name check and the strict email matcher).
    """
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[UCSDECEEntry] = []
    seen: set[tuple[str, str]] = set()

    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        name = _heading_name(heading.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue
        block = _heading_container(heading)
        block_text = _clean(block.get_text(" ", strip=True))
        if block_text == name or not 30 <= len(block_text) <= 3500:
            continue
        email = _choose_email(
            EMAIL_RE.findall(block_text),
            name,
            ("ucsd.edu",),
        )
        profile_url = _profile_link_from_block(block, base_url, name)
        if not email and profile_url == NOT_AVAILABLE:
            continue
        key = (_normalize(name), profile_url)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            UCSDECEEntry(
                name=name,
                email=email,
                profile_url=profile_url,
            )
        )
    return entries


def _jacobs_title_and_research(soup: BeautifulSoup, name: str) -> tuple[str, str]:
    """Read title and research summary from a Jacobs School faculty profile.

    The profiles open with ``<h3>Name</h3>`` (often dropping middle initials,
    so matching is done on first and last tokens) followed by short lines such
    as ``Associate Teaching Professor, ECE`` and ``Discovery-based lab design,
    hands-on educational programming`` and then a long narrative bio paragraph.
    The line containing ``Professor`` is the title and any remaining short lines
    are the research summary; the bio paragraph itself is skipped.  If no short
    summary exists we fall back to research-sentence selection over the content
    region only, never the shared navigation.
    """
    root = soup.find(["main", "article"]) or soup
    name_parts = [part for part in re.findall(r"[a-z]+", name.casefold()) if len(part) > 1]
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if name_parts else ""

    heading: Tag | None = None
    heading_key = ""
    for candidate in root.find_all(["h1", "h2", "h3", "h4"]):
        heading_key = _normalize(_clean(candidate.get_text(" ", strip=True)))
        if not heading_key or not last or last not in heading_key:
            continue
        if (first and first in heading_key) or (first and first[0] in heading_key):
            heading = candidate
            break
    if heading is None:
        cleaned = _clean(root.get_text(" ", strip=True))
        research = (
            _concise_bio_research(cleaned[:5000])
            if re.search(r"\b(research|studies|works on|focuses on|develops)\b", cleaned, re.I)
            else NOT_AVAILABLE
        )
        return NOT_AVAILABLE, research

    lines: list[str] = []
    seen_lines: set[str] = set()
    for element in heading.next_elements:
        if isinstance(element, Tag):
            if element is not heading and re.match(r"h[1-4]$", element.name or ""):
                break
            value = _clean(element.get_text(" ", strip=True))
        else:
            value = _clean(str(element))
        key = _normalize(value)
        if (
            not value
            or not key
            or key == _normalize(name)
            or key == heading_key
            or key in seen_lines
        ):
            continue
        seen_lines.add(key)
        if "capsule bio" in value.casefold() or len(value) > 400:
            break
        lines.append(value)
        if len(" ".join(lines)) > 600:
            break

    title = NOT_AVAILABLE
    summary_parts: list[str] = []
    for value in lines[:10]:
        if title == NOT_AVAILABLE:
            match = TITLE_PATTERN.search(value)
            if match:
                title = _clean(match.group(0)).strip(" ,;:|–—-")
                continue
        oneline = " ".join(value.split())
        if len(oneline) < 6:
            continue
        if title != NOT_AVAILABLE and (
            re.match(r"(?:[A-Z][a-z]*\s)*Professor\b", oneline)
            or re.match(r"(?:[A-Z][a-z]*\s)*(?:Lecturer|Instructor)\b", oneline)
            or oneline.casefold().startswith("calit2")
        ):
            continue
        summary_parts.append(oneline)
    research = _clean("; ".join(summary_parts))
    if len(research) < 12:
        full = _clean(root.get_text(" ", strip=True))
        research = (
            _concise_bio_research(full[:5000])
            if re.search(r"\b(research|studies|works on|focuses on|develops)\b", full, re.I)
            else NOT_AVAILABLE
        )
    return title, sanitize_research_text(research)


def parse_jacobs_profile_html(
    html_text: str,
    profile_url: str,
    name: str,
) -> UCSDJacobsDetails:
    soup = BeautifulSoup(html_text, "html.parser")
    email = _choose_email(
        _email_candidates(soup),
        name,
        ("ucsd.edu",),
    )
    title, research = _jacobs_title_and_research(soup, name)
    website = _website_from_soup(soup, profile_url, name)
    return UCSDJacobsDetails(
        title=title,
        research_interests=research,
        email=email,
        website_url=website,
    )


class UCSDECEScraper(BaseUniversityScraper):
    university_name = "University of California, San Diego"
    directory_url = UCSD_ECE_DIRECTORY_URL

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
        entries = parse_ucsd_ece_directory_html(
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
                    f"Checking UC San Diego ECE profile {index} of {total}: {entry.name}"
                )
            enriched = None
            if entry.profile_url != NOT_AVAILABLE:
                try:
                    profile_soup = self.get_soup(entry.profile_url)
                    enriched = parse_jacobs_profile_html(
                        str(profile_soup), entry.profile_url, entry.name
                    )
                except requests.RequestException as exc:
                    LOGGER.warning(
                        "Could not inspect UCSD ECE profile for %s: %s",
                        entry.name,
                        exc,
                    )
            email = (enriched.email if enriched and enriched.email else "") or entry.email
            if not email:
                continue
            title = entry.title
            research = entry.research_interests
            website = NOT_AVAILABLE
            if enriched is not None:
                title = enriched.title if enriched.title != NOT_AVAILABLE else title
                research = (
                    enriched.research_interests
                    if enriched.research_interests != NOT_AVAILABLE
                    else research
                )
                website = enriched.website_url
            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department="Electrical and Computer Engineering",
                    title=title,
                    research_interests=research,
                    email=email,
                    website_url=website,
                    profile_url=entry.profile_url,
                    source_type=(
                        "Official UC San Diego Electrical and Computer Engineering "
                        "faculty directory and Jacobs School profiles"
                    ),
                )
            )
        return records
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor

BERKELEY_CS_DIRECTORY_URL = "https://www2.eecs.berkeley.edu/Faculty/Lists/CS/faculty.html"
BERKELEY_EE_DIRECTORY_URL = "https://www2.eecs.berkeley.edu/Faculty/Lists/EE/faculty.html"
LOGGER = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

GENERIC_EMAIL_WORDS = {
    "admin", "assistant", "contact", "coordinator", "info", "office", "support",
    "webmaster", "roster", "no_email", "theoryadmin",
}

TITLE_WORDS = (
    "professor", "lecturer", "research scientist", "scientist", "director",
    "instructor", "fellow",
)

STOP_LABELS = (
    "education:", "office hours:", "assistants:", "teaching schedule",
    "research interests:",
)


@dataclass(slots=True)
class BerkeleyDirectoryEntry:
    name: str
    title: str
    research_interests: str
    email: str
    profile_url: str
    website_url: str = "Not publicly available"


def _normalize_name(name: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return [part for part in re.findall(r"[a-z]+", ascii_text.lower()) if len(part) >= 2]


def _looks_like_name(text: str) -> bool:
    cleaned = " ".join(text.split())
    words = cleaned.split()
    return 2 <= len(words) <= 7 and not any(char.isdigit() for char in cleaned)


def _content_until_next_heading(heading: Tag) -> str:
    pieces: list[str] = []
    for element in heading.next_elements:
        if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3"}:
            break
        if isinstance(element, NavigableString):
            parent = element.parent
            if isinstance(parent, Tag) and parent.name in {"script", "style", "noscript"}:
                continue
            text = " ".join(str(element).split())
            if text and text not in pieces:
                pieces.append(text)
    return "\n".join(pieces)


def _extract_title(block: str) -> str:
    for line in block.splitlines():
        cleaned = " ".join(line.split()).strip(" ;")
        cleaned = re.sub(
            r"^\s*(?:above|below)\s+the\s+line\s*[,;:|–—-]*\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        if len(cleaned) <= 180 and any(word in cleaned.lower() for word in TITLE_WORDS):
            return cleaned
    return "Not publicly available"


def _extract_interests(block: str) -> str:
    match = re.search(
        r"Research Interests:\s*(.+?)(?=\s*(?:Education:|Office Hours:|Assistants:|Teaching Schedule|$))",
        " ".join(block.split()),
        flags=re.IGNORECASE,
    )
    if not match:
        return "Not publicly available"
    interests = re.sub(r"\s*\([A-Z&/ -]{2,8}\)", "", match.group(1))
    interests = re.sub(r"\s*;\s*", ", ", interests)
    return " ".join(interests.split()).strip(" ,;") or "Not publicly available"


def _choose_email(emails: Iterable[str], person_name: str) -> str:
    name_parts = _normalize_name(person_name)
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if name_parts else ""
    best = ""
    best_score = -100

    for raw_email in emails:
        email = raw_email.strip(".,;:()[]{}<>\"'").lower()
        if "@" not in email:
            continue
        local, domain = email.split("@", 1)
        score = 0
        if domain.endswith("berkeley.edu"):
            score += 5
        elif domain.endswith(".edu"):
            score += 1
        compact = re.sub(r"[^a-z0-9]", "", local)
        if last and last in compact:
            score += 5
        if first and first in compact:
            score += 3
        if first and last and compact.startswith(first[0]) and last in compact:
            score += 2
        if any(word in local for word in GENERIC_EMAIL_WORDS):
            score -= 12
        if score > best_score and score >= 6:
            best_score = score
            best = email
    return best


WEBSITE_LABEL_SCORES = (
    ("personal homepage", 100),
    ("personal website", 100),
    ("faculty homepage", 95),
    ("home page", 90),
    ("homepage", 90),
    ("lab website", 85),
    ("research lab", 82),
    ("laboratory", 80),
    (" lab", 75),
    ("website", 65),
)

WEBSITE_BLOCKED_LABELS = {
    "publications", "selected publications", "dissertations", "larger photo",
    "research areas", "research centers", "courses", "teaching schedule",
}


def extract_berkeley_website_url(
    html_text: str,
    profile_url: str,
) -> str:
    """Choose a professor's public personal or lab site from a Berkeley profile.

    Berkeley's faculty list points to an official profile page. That profile often
    contains a separate "Personal Homepage" link or, when no personal site is
    listed, one or more lab/research-center links. We prefer the personal site and
    reject publication, dissertation, navigation, mail, and file-download links.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[tuple[int, str]] = []
    profile_host = urlparse(profile_url).netloc.lower()

    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get_text(" ", strip=True).lower().split())
        href = str(anchor.get("href", "")).strip()
        if not label or not href:
            continue
        if label in WEBSITE_BLOCKED_LABELS:
            continue
        if href.lower().startswith(("mailto:", "javascript:", "#")):
            continue

        absolute = urljoin(profile_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if absolute.rstrip("/") == profile_url.rstrip("/"):
            continue
        if "/research/areas/centers" in parsed.path.lower().rstrip("/"):
            continue
        if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            continue

        score = 0
        for phrase, phrase_score in WEBSITE_LABEL_SCORES:
            if phrase in f" {label}":
                score = max(score, phrase_score)

        # Berkeley profile pages also list named research centers such as BAIR.
        # Treat an external link whose visible name contains "lab" as a fallback.
        if score == 0 and "lab" in label:
            score = 72

        if score == 0:
            continue

        # Prefer a distinct personal/lab domain over another generic Berkeley
        # navigation page when the labels have otherwise equal priority.
        if parsed.netloc.lower() != profile_host:
            score += 3
        candidates.append((score, absolute))

    if not candidates:
        return "Not publicly available"

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def parse_berkeley_directory_html(
    html_text: str,
    base_url: str = BERKELEY_CS_DIRECTORY_URL,
) -> list[BerkeleyDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[BerkeleyDirectoryEntry] = []
    seen: set[tuple[str, str]] = set()

    for heading in soup.find_all(["h2", "h3"]):
        name = " ".join(heading.get_text(" ", strip=True).split())
        if not _looks_like_name(name):
            continue

        block = _content_until_next_heading(heading)
        title = _extract_title(block)
        emails = EMAIL_RE.findall(block)
        email = _choose_email(emails, name)
        if not email:
            continue

        interests = _extract_interests(block)
        link = heading.find("a", href=True)
        profile_url = urljoin(base_url, str(link.get("href"))) if link else base_url
        key = (name.lower(), email)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            BerkeleyDirectoryEntry(
                name=name,
                title=title,
                research_interests=interests,
                email=email,
                profile_url=profile_url,
            )
        )

    return entries


class BerkeleyScraper(BaseUniversityScraper):
    university_name = "University of California, Berkeley"
    department = "Electrical Engineering and Computer Sciences"
    directory_url = BERKELEY_CS_DIRECTORY_URL
    source_type = "Official UC Berkeley EECS faculty list and faculty profile"

    def __init__(
        self,
        request_delay: float = 0.5,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def scrape(self) -> list[ScrapedProfessor]:
        soup = self.get_soup(self.directory_url)
        entries = parse_berkeley_directory_html(str(soup), self.directory_url)
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking Berkeley profile {index} of {total}: {entry.name}"
                )

            website_url = entry.website_url
            try:
                profile_soup = self.get_soup(entry.profile_url)
                website_url = extract_berkeley_website_url(
                    str(profile_soup),
                    entry.profile_url,
                )
            except requests.RequestException as exc:
                # One inaccessible profile should not cancel the entire import.
                LOGGER.warning(
                    "Could not inspect Berkeley profile for %s: %s",
                    entry.name,
                    exc,
                )

            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department=self.department,
                    title=entry.title,
                    research_interests=entry.research_interests,
                    email=entry.email,
                    website_url=website_url,
                    profile_url=entry.profile_url,
                    source_type=self.source_type,
                )
            )
        return records


class BerkeleyEEScraper(BerkeleyScraper):
    """Electrical Engineering faculty from the same official EECS list.

    V9.7 Phase 2 broadens UC Berkeley with the EE list while keeping the CS
    list canonical. The EE page uses the exact page generator as the CS list,
    so it is parsed by the identical ``parse_berkeley_directory_html`` logic.
    """

    department = "Electrical Engineering and Computer Sciences"
    directory_url = BERKELEY_EE_DIRECTORY_URL
    source_type = (
        "Official UC Berkeley EECS Electrical Engineering faculty list and "
        "faculty profile"
    )

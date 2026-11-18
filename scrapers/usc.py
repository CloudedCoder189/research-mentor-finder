from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)

USC_DIRECTORY_URL = "https://www.cs.usc.edu/directory/faculty/"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

# The legacy USC CS directory can still publish retired query-string profile
# routes for a small number of current faculty. Keep explicit official Viterbi
# replacements here so full refreshes do not restore a known stale URL.
USC_PROFILE_OVERRIDES = {
    "wenshengwu": "https://viterbi.usc.edu/directory/faculty/Wu/Wensheng",
}

TITLE_PATTERN = re.compile(
    r"\b(?:Henry Salvatori Chair|University Professor|Distinguished Professor|"
    r"Research Associate Professor|Research Assistant Professor|Research Professor|"
    r"Adjunct Research Professor|Adjunct Research Assistant Professor|"
    r"Assistant Professor|Associate Professor|Professor Emeritus|Professor|"
    r"Senior Lecturer|Part[- ]?Time Lecturer|Adjunct Lecturer|Lecturer|"
    r"Research Scientist|Senior Research Associate|Principal Scientist)\b",
    re.IGNORECASE,
)

WEBSITE_LABEL_SCORES = (
    # Prefer a professor's own academic page when the official USC profile
    # publishes both a personal page and a broader center/research site.
    ("personal website", 112),
    ("personal homepage", 112),
    ("academic website", 110),
    ("homepage", 108),
    ("lab website", 105),
    ("laboratory", 103),
    ("research website", 100),
    ("website", 80),
)

BLOCKED_WEBSITE_LABELS = {
    "publications",
    "google scholar",
    "curriculum vitae",
    "cv",
    "return to faculty directory",
    "open faculty positions",
    "open staff positions",
}


@dataclass(slots=True)
class USCDirectoryEntry:
    name: str
    title: str
    profile_url: str


@dataclass(slots=True)
class USCProfileDetails:
    name: str
    title: str
    department: str
    email: str
    research_interests: str
    website_url: str
    source_text: str


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _normalize_name(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return [part for part in re.findall(r"[a-z]+", ascii_text.lower()) if len(part) > 1]


def _split_directory_label(label: str) -> tuple[str, str] | None:
    cleaned = _clean(label)
    match = TITLE_PATTERN.search(cleaned)
    if not match:
        return None
    name = cleaned[: match.start()].strip(" |–—-,:;")
    title = cleaned[match.start() :].strip()
    words = name.split()
    if not 2 <= len(words) <= 8 or any(char.isdigit() for char in name):
        return None
    return name, title


def parse_usc_directory_html(
    html_text: str,
    base_url: str = USC_DIRECTORY_URL,
) -> list[USCDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[USCDirectoryEntry] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        absolute = urljoin(base_url, href)
        lowered = absolute.lower()
        if "/directory/faculty/profile" not in lowered and "/directory/faculty/" not in lowered:
            continue
        if absolute.rstrip("/") == base_url.rstrip("/"):
            continue

        label = _clean(anchor.get_text(" ", strip=True))
        query = parse_qs(urlparse(absolute).query)
        first = _clean(query.get("fname", [""])[0])
        last = _clean(query.get("lname", [""])[0])
        if first and last:
            name = f"{first} {last}"
            title = label[len(name):].strip(" |–—-,:;") if label.lower().startswith(name.lower()) else ""
            if not title or not TITLE_PATTERN.search(title):
                parsed_label = _split_directory_label(label)
                title = parsed_label[1] if parsed_label else "Not publicly available"
        else:
            parsed_label = _split_directory_label(label)
            if not parsed_label:
                # Some layouts put name and title in nested siblings inside one card.
                parent = anchor.find_parent(["article", "li", "div"])
                parsed_label = _split_directory_label(parent.get_text(" ", strip=True)) if parent else None
            if not parsed_label:
                continue
            name, title = parsed_label
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in seen:
            continue
        seen.add(key)
        profile_url = USC_PROFILE_OVERRIDES.get(key, absolute)
        entries.append(USCDirectoryEntry(name=name, title=title, profile_url=profile_url))
    return entries


def _section_text(soup: BeautifulSoup, heading_label: str, max_chars: int = 2200) -> str:
    for heading in soup.find_all(["h2", "h3", "h4"]):
        label = _clean(heading.get_text(" ", strip=True)).lower()
        if heading_label not in label:
            continue
        pieces: list[str] = []
        for element in heading.next_siblings:
            if isinstance(element, Tag) and element.name in {"h2", "h3", "h4"}:
                break
            if isinstance(element, Tag):
                text = _clean(element.get_text(" ", strip=True))
            else:
                text = _clean(str(element))
            if text and text not in pieces:
                pieces.append(text)
            if sum(len(piece) for piece in pieces) >= max_chars:
                break
        return " ".join(pieces)[:max_chars].strip()
    return "Not publicly available"


def _concise_research_text(value: str, max_chars: int = 760, max_sentences: int = 4) -> str:
    """Keep the public research description useful without copying an entire bio."""

    cleaned = _clean(value)
    if cleaned == "Not publicly available" or len(cleaned) <= max_chars:
        return cleaned

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    selected: list[str] = []
    for sentence in sentences:
        sentence = _clean(sentence)
        if not sentence:
            continue
        proposed = " ".join([*selected, sentence])
        if selected and len(proposed) > max_chars:
            break
        selected.append(sentence)
        if len(selected) >= max_sentences or len(" ".join(selected)) >= max_chars:
            break

    result = " ".join(selected).strip()
    if result:
        return result[:max_chars].rstrip(" ,;:-")
    return cleaned[:max_chars].rstrip(" ,;:-") + "…"


def _choose_email(emails: list[str], name: str) -> str:
    parts = _normalize_name(name)
    first = parts[0] if parts else ""
    last = parts[-1] if parts else ""
    best = ""
    best_score = -100
    for raw in emails:
        email = raw.lower().strip(".,;:()[]{}<>\"'")
        if "@" not in email:
            continue
        local, domain = email.split("@", 1)
        compact = re.sub(r"[^a-z0-9]", "", local)
        score = 0
        if domain.endswith("usc.edu"):
            score += 7
        elif domain.endswith(".edu"):
            score += 2
        if last and last in compact:
            score += 5
        if first and first in compact:
            score += 3
        if first and last and compact.startswith(first[0]) and last in compact:
            score += 2
        if any(word in local for word in ("admin", "info", "contact", "office", "support", "webmaster")):
            score -= 15
        if score > best_score and score >= 7:
            best_score = score
            best = email
    return best


def _extract_profile_website(soup: BeautifulSoup, profile_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    profile_host = urlparse(profile_url).netloc.lower()
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True)).lower()
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if label in BLOCKED_WEBSITE_LABELS or any(token in label for token in ("publication", "scholar profile")):
            continue
        absolute = urljoin(profile_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if absolute.rstrip("/") == profile_url.rstrip("/"):
            continue
        if "/research/research-areas-labs" in parsed.path.lower().rstrip("/"):
            continue
        if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            continue

        score = 0
        for phrase, phrase_score in WEBSITE_LABEL_SCORES:
            if phrase in label:
                score = max(score, phrase_score)
        if score == 0 and "lab" in label:
            score = 90
        if score == 0:
            continue
        if parsed.netloc.lower() != profile_host:
            score += 3
        candidates.append((score, absolute))

    if not candidates:
        return "Not publicly available"
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def parse_usc_profile_html(
    html_text: str,
    profile_url: str,
    fallback_name: str,
    fallback_title: str,
) -> USCProfileDetails:
    soup = BeautifulSoup(html_text, "html.parser")
    h1 = soup.find("h1")
    name = _clean(h1.get_text(" ", strip=True)) if h1 else fallback_name

    title = fallback_title
    if h1:
        for element in h1.next_elements:
            if isinstance(element, Tag) and element is not h1 and element.name in {"h2", "h3"}:
                break
            if isinstance(element, Tag):
                text = _clean(element.get_text(" ", strip=True))
                if text and TITLE_PATTERN.search(text) and len(text) <= 240:
                    title = text
                    break

    full_text = _clean(soup.get_text(" ", strip=True))
    email = _choose_email(EMAIL_RE.findall(full_text), name)
    research = _section_text(soup, "research summary", max_chars=1600)
    if research == "Not publicly available":
        research = _section_text(soup, "research interests", max_chars=1600)
    if research == "Not publicly available":
        research = _section_text(soup, "biography", max_chars=1200)
    research = _concise_research_text(research)

    appointments = _section_text(soup, "appointments", max_chars=500)
    department = "Computer Science"
    if appointments != "Not publicly available":
        if "electrical and computer engineering" in appointments.lower():
            department = "Computer Science and Electrical and Computer Engineering"
        elif "computer science" in appointments.lower():
            department = "Computer Science"

    website_url = _extract_profile_website(soup, profile_url)
    return USCProfileDetails(
        name=name,
        title=title,
        department=department,
        email=email,
        research_interests=research,
        website_url=website_url,
        source_text=full_text,
    )


def _entry_priority(entry: USCDirectoryEntry) -> tuple[int, str]:
    lowered = entry.title.lower()
    if "assistant professor" in lowered or "associate professor" in lowered:
        return (0, entry.name.lower())
    if "research" in lowered or "distinguished professor" in lowered or lowered.startswith("professor"):
        return (1, entry.name.lower())
    if "lecturer" in lowered or "practice" in lowered:
        return (3, entry.name.lower())
    return (2, entry.name.lower())


class USCScraper(BaseUniversityScraper):
    university_name = "University of Southern California"
    directory_url = USC_DIRECTORY_URL

    def __init__(
        self,
        request_delay: float = 0.55,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def scrape(self) -> list[ScrapedProfessor]:
        soup = self.get_soup(self.directory_url)
        entries = parse_usc_directory_html(str(soup), self.directory_url)
        entries.sort(key=_entry_priority)
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking USC profile {index} of {total}: {entry.name}")
            try:
                profile_soup = self.get_soup(entry.profile_url)
                details = parse_usc_profile_html(
                    str(profile_soup),
                    entry.profile_url,
                    entry.name,
                    entry.title,
                )
            except requests.RequestException as exc:
                LOGGER.warning("Could not inspect USC profile for %s: %s", entry.name, exc)
                continue

            if not details.email:
                continue
            base_record = {
                "title": details.title,
                "research_interests": details.research_interests,
                "website_url": details.website_url,
                "profile_url": entry.profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=details.source_text,
                source_url=(
                    details.website_url
                    if details.website_url != "Not publicly available"
                    else entry.profile_url
                ),
            )
            records.append(
                ScrapedProfessor(
                    name=details.name,
                    university=self.university_name,
                    department=details.department,
                    title=details.title,
                    research_interests=details.research_interests,
                    email=details.email,
                    website_url=details.website_url,
                    profile_url=entry.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type="Official USC Computer Science faculty directory and Viterbi profile",
                )
            )
        return records

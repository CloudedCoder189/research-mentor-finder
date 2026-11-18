from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import EMAIL_RE, NOT_AVAILABLE, _clean, _clean_name, sanitize_research_text
from services.opportunity import assess_outreach_potential

DIRECTORY_URL = "https://csc.calpoly.edu/faculty/"
FACULTY_TITLE_RE = re.compile(
    r"\b(?:Distinguished\s+Professor|Research\s+Professor|Teaching\s+Professor|"
    r"Assistant\s+Professor|Associate\s+Professor|Professor)\b",
    re.IGNORECASE,
)
BLOCKED_ROLE_RE = re.compile(
    r"\b(?:lecturer|emerit(?:us|a)|staff|affiliate|adjunct|visiting|"
    r"postdoctoral|research\s+associate|manager|coordinator|administrator)\b",
    re.IGNORECASE,
)
STOP_HEADINGS = (
    "affiliated faculty",
    "active emeriti",
    "emeriti",
    "staff",
    "faculty office hours",
    "spring",
    "fall",
    "winter",
)
BLOCKED_PERSONAL_HOSTS = {
    "calpoly.zoom.us",
    "zoom.us",
    "docs.google.com",
    "drive.google.com",
    "calendly.com",
}
OFFICE_RE = re.compile(r"\b\d{1,3}(?:[-–][A-Z0-9]{1,8}){1,3}\b", re.IGNORECASE)


@dataclass(slots=True)
class CalPolyFacultyEntry:
    name: str
    title: str
    email: str
    research_interests: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE


def _valid_email(value: str) -> bool:
    value = value.casefold().strip(".,;:()[]{}<>\"'")
    return bool(EMAIL_RE.fullmatch(value) and value.endswith("@calpoly.edu"))


def _emails(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            cleaned
            for raw in EMAIL_RE.findall(value)
            if _valid_email(cleaned := raw.casefold().strip(".,;:()[]{}<>\"'"))
        )
    )


def _title(value: str) -> str:
    text = _clean(value)
    if BLOCKED_ROLE_RE.search(text):
        return NOT_AVAILABLE
    match = FACULTY_TITLE_RE.search(text)
    if not match:
        return NOT_AVAILABLE
    role = _clean(match.group(0))
    if re.search(r"\b(?:department\s+chair|chair)\b", text, re.IGNORECASE):
        return f"{role} and Department Chair"
    return role


def _looks_like_name(value: str) -> bool:
    value = _clean_name(value)
    words = value.split()
    if not 2 <= len(words) <= 8 or len(value) > 100:
        return False
    if any(char.isdigit() for char in value) or "@" in value:
        return False
    lowered = value.casefold()
    if any(
        phrase in lowered
        for phrase in (
            "faculty",
            "research interests",
            "computer science",
            "software engineering",
            "office hours",
            "department",
        )
    ):
        return False
    return sum(character.isalpha() for character in value) >= 5


def _personal_link(container: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for anchor in container.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.casefold().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        host = parsed.netloc.casefold()
        if any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_PERSONAL_HOSTS):
            continue
        if absolute.rstrip("/").casefold() == DIRECTORY_URL.rstrip("/").casefold():
            continue
        label = _clean(anchor.get_text(" ", strip=True)).casefold()
        score = 0
        if host.endswith("users.csc.calpoly.edu"):
            score += 30
        if host not in {
            "csc.calpoly.edu",
            "www.csc.calpoly.edu",
            "calpoly.edu",
            "www.calpoly.edu",
        }:
            score += 15
        if any(word in label for word in ("website", "homepage", "home page", "lab", "research")):
            score += 10
        if score:
            candidates.append((score, absolute))
    if not candidates:
        return NOT_AVAILABLE
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1]


def _faculty_bounds(soup: BeautifulSoup) -> tuple[int, int, list[Tag]]:
    tags = list(soup.find_all(True))
    start = -1
    stop = len(tags)
    for index, tag in enumerate(tags):
        if tag.name not in {"h1", "h2", "h3", "h4"}:
            continue
        label = _clean(tag.get_text(" ", strip=True)).casefold()
        if start < 0 and label == "faculty":
            start = index
            continue
        if start >= 0 and any(label.startswith(value) for value in STOP_HEADINGS):
            stop = index
            break
    return start, stop, tags


def _in_faculty_range(tag: Tag, start: int, stop: int, tags: list[Tag]) -> bool:
    try:
        index = tags.index(tag)
    except ValueError:
        return False
    return start < index < stop


def _header_indexes(table: Tag) -> dict[str, int]:
    header_row = table.find("tr")
    if header_row is None:
        return {}
    values = [
        _clean(cell.get_text(" ", strip=True)).casefold()
        for cell in header_row.find_all(["th", "td"], recursive=False)
    ]
    indexes: dict[str, int] = {}
    for index, value in enumerate(values):
        if "name" in value and "name" not in indexes:
            indexes["name"] = index
        elif "title" in value or "position" in value:
            indexes["title"] = index
        elif "email" in value:
            indexes["email"] = index
        elif "research" in value or "interest" in value:
            indexes["research"] = index
    return indexes


def _name_from_cell(cell: Tag, title: str, email: str) -> str:
    for tag in cell.find_all(["a", "strong", "b", "h2", "h3", "h4"], limit=8):
        candidate = _clean_name(tag.get_text(" ", strip=True))
        if _looks_like_name(candidate):
            return candidate
    text = _clean(cell.get_text(" ", strip=True))
    text = re.sub(re.escape(email), " ", text, flags=re.IGNORECASE)
    text = re.sub(re.escape(title), " ", text, flags=re.IGNORECASE)
    text = re.split(r"\b(?:Office|Research Interests?)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    candidate = _clean_name(text)
    return candidate if _looks_like_name(candidate) else ""


def _research_from_row(cells: list[Tag], indexes: dict[str, int], name: str, title: str, email: str) -> str:
    research_index = indexes.get("research")
    if research_index is not None and research_index < len(cells):
        value = sanitize_research_text(cells[research_index].get_text(" ", strip=True))
        if value != NOT_AVAILABLE:
            return value

    # Current Cal Poly markup occasionally leaves the research field in an
    # unlabeled trailing cell.  Reject contact/office-only cells rather than
    # treating an office number as a research topic.
    for cell in reversed(cells):
        raw = _clean(cell.get_text(" ", strip=True))
        value = sanitize_research_text(raw)
        if value == NOT_AVAILABLE or len(value) < 12:
            continue
        if value.casefold() in {name.casefold(), title.casefold(), email.casefold()}:
            continue
        if EMAIL_RE.search(raw) or OFFICE_RE.fullmatch(raw):
            continue
        if re.search(r"\b(?:office hours|zoom|appointment|in person|canvas)\b", value, re.IGNORECASE):
            continue
        return value
    return NOT_AVAILABLE


def _parse_faculty_table(table: Tag, page_url: str) -> list[CalPolyFacultyEntry]:
    indexes = _header_indexes(table)
    entries: list[CalPolyFacultyEntry] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        row_text = _clean(row.get_text(" ", strip=True))
        row_emails = _emails(row_text)
        if len(row_emails) != 1:
            continue
        title_text = (
            _clean(cells[indexes["title"]].get_text(" ", strip=True))
            if "title" in indexes and indexes["title"] < len(cells)
            else row_text
        )
        academic_title = _title(title_text or row_text)
        if academic_title == NOT_AVAILABLE:
            continue
        name_index = indexes.get("name", 0)
        name_cell = cells[name_index] if name_index < len(cells) else cells[0]
        name = _name_from_cell(name_cell, academic_title, row_emails[0])
        if not name:
            continue
        entries.append(
            CalPolyFacultyEntry(
                name=name,
                title=academic_title,
                email=row_emails[0],
                research_interests=_research_from_row(
                    cells, indexes, name, academic_title, row_emails[0]
                ),
                website_url=_personal_link(name_cell, page_url),
            )
        )
    return entries


def _nearest_flat_record(email_node: Tag) -> Tag | None:
    best: Tag | None = None
    for parent in email_node.parents:
        if not isinstance(parent, Tag):
            continue
        text = _clean(parent.get_text(" ", strip=True))
        if len(text) > 1800:
            break
        if len(_emails(text)) != 1:
            continue
        if _title(text) != NOT_AVAILABLE:
            best = parent
            # Prefer a row/card wrapper rather than the mailto anchor itself.
            if parent.name in {"tr", "li", "article", "section"} or any(
                token in " ".join(parent.get("class", [])).casefold()
                for token in ("person", "faculty", "profile", "card", "row")
            ):
                return parent
    return best


def _research_from_flat_text(text: str, name: str, title: str, email: str) -> str:
    value = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    value = re.sub(re.escape(title), " ", value, flags=re.IGNORECASE)
    value = re.sub(re.escape(email), " ", value, flags=re.IGNORECASE)
    value = OFFICE_RE.sub(" ", value)
    value = re.sub(r"\b(?:Research Interests?)\s*[:\-]?\s*", " ", value, flags=re.IGNORECASE)
    value = sanitize_research_text(value)
    if value == NOT_AVAILABLE or len(value) < 12:
        return NOT_AVAILABLE
    if re.search(r"\b(?:office hours|zoom|appointment|in person|canvas)\b", value, re.IGNORECASE):
        return NOT_AVAILABLE
    return value


def _parse_flat_records(section: BeautifulSoup, page_url: str) -> list[CalPolyFacultyEntry]:
    entries: list[CalPolyFacultyEntry] = []
    seen_blocks: set[int] = set()
    for anchor in section.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href.casefold().startswith("mailto:"):
            continue
        email = href[7:].split("?", 1)[0].casefold().strip()
        if not _valid_email(email):
            continue
        block = _nearest_flat_record(anchor)
        if block is None or id(block) in seen_blocks:
            continue
        seen_blocks.add(id(block))
        block_text = _clean(block.get_text(" ", strip=True))
        academic_title = _title(block_text)
        if academic_title == NOT_AVAILABLE:
            continue
        name = ""
        for tag in block.find_all(["h2", "h3", "h4", "strong", "b", "a"], limit=12):
            if tag is anchor:
                continue
            candidate = _clean_name(tag.get_text(" ", strip=True))
            if _looks_like_name(candidate):
                name = candidate
                break
        if not name:
            prefix = block_text.split(email, 1)[0]
            prefix = re.sub(re.escape(academic_title), " ", prefix, flags=re.IGNORECASE)
            candidate = _clean_name(prefix)
            if _looks_like_name(candidate):
                name = candidate
        if not name:
            continue
        entries.append(
            CalPolyFacultyEntry(
                name=name,
                title=academic_title,
                email=email,
                research_interests=_research_from_flat_text(
                    block_text, name, academic_title, email
                ),
                website_url=_personal_link(block, page_url),
            )
        )
    return entries


def parse_calpoly_faculty_html(
    html_text: str,
    page_url: str = DIRECTORY_URL,
) -> list[CalPolyFacultyEntry]:
    """Parse only the official professor-level Cal Poly Faculty section."""
    soup = BeautifulSoup(html_text, "html.parser")
    start, stop, tags = _faculty_bounds(soup)
    if start < 0:
        return []

    candidates: list[CalPolyFacultyEntry] = []
    for table in soup.find_all("table"):
        if not _in_faculty_range(table, start, stop, tags):
            continue
        header_text = _clean(table.get_text(" ", strip=True)).casefold()
        if "email" in header_text and "name" in header_text:
            candidates.extend(_parse_faculty_table(table, page_url))

    # Build a bounded fragment for card/flat layouts and as a fallback if the
    # site's table markup changes.
    fragment = BeautifulSoup(
        "".join(str(tag) for index, tag in enumerate(tags) if start < index < stop and tag.parent in {soup, soup.body, soup.main}),
        "html.parser",
    )
    if not fragment.get_text(" ", strip=True):
        faculty_heading = tags[start]
        values: list[str] = []
        for sibling in faculty_heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h1", "h2", "h3", "h4"}:
                label = _clean(sibling.get_text(" ", strip=True)).casefold()
                if any(label.startswith(value) for value in STOP_HEADINGS):
                    break
            values.append(str(sibling))
        fragment = BeautifulSoup("".join(values), "html.parser")
    candidates.extend(_parse_flat_records(fragment, page_url))

    deduped: dict[str, CalPolyFacultyEntry] = {}
    for candidate in candidates:
        key = candidate.email.casefold()
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = candidate
            continue
        if existing.research_interests == NOT_AVAILABLE and candidate.research_interests != NOT_AVAILABLE:
            existing.research_interests = candidate.research_interests
        if existing.website_url == NOT_AVAILABLE and candidate.website_url != NOT_AVAILABLE:
            existing.website_url = candidate.website_url
    return sorted(deduped.values(), key=lambda row: row.name.casefold())


class CalPolySLOScraper(BaseUniversityScraper):
    university_name = "California Polytechnic State University, San Luis Obispo"
    directory_url = DIRECTORY_URL
    authoritative_roster = True
    minimum_authoritative_records = 25

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
        soup = self.get_soup(self.directory_url)
        entries = parse_calpoly_faculty_html(str(soup), self.directory_url)
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Reading Cal Poly faculty record {index} of {len(entries)}: {entry.name}"
                )
            assessment = assess_outreach_potential(
                {
                    "title": entry.title,
                    "research_interests": entry.research_interests,
                    "website_url": entry.website_url,
                    "profile_url": self.directory_url,
                },
                source_text=f"{entry.name} {entry.title} {entry.research_interests}",
                source_url=(
                    entry.website_url if entry.website_url != NOT_AVAILABLE else self.directory_url
                ),
            )
            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department="Computer Science and Software Engineering",
                    title=entry.title,
                    research_interests=entry.research_interests,
                    email=entry.email,
                    website_url=entry.website_url,
                    # Cal Poly publishes one official department roster rather
                    # than a separate university profile for every professor.
                    profile_url=self.directory_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=(
                        "Official Cal Poly Computer Science and Software Engineering Faculty section"
                    ),
                )
            )

        if not records:
            self.last_error = (
                "Cal Poly did not return any professor-level records from the official Faculty "
                "section. Lecturers, affiliated faculty, emeriti, staff, and office-hours rows "
                "were excluded."
            )
        elif self.max_profiles is not None and len(records) < self.max_profiles:
            self.last_error = (
                f"Cal Poly saved {len(records)} professor-level record(s); lecturers, affiliated "
                "faculty, emeriti, staff, and office-hours rows were intentionally excluded."
            )
        return records

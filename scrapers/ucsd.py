from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor

LOGGER = logging.getLogger(__name__)

UCSD_FACULTY_DIRECTORY_URL = "https://cse.ucsd.edu/people/faculty-profiles/faculty"
UCSD_AI_FACULTY_URL = "https://ai.ucsd.edu/faculty"
UCSD_NLP_PEOPLE_URL = "https://ucsd-nlp.github.io/people/"
UCSD_ROBOTICS_FACULTY_URL = (
    "https://www.ece.ucsd.edu/faculty-research/ece-research-areas/"
    "intelligent-systems-robotics-control-impacted"
)
UCSD_VISUAL_FACULTY_URL = "https://viscomp.ucsd.edu/faculty.shtml"

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
TITLE_RE = re.compile(
    r"\b((?:assistant|associate|distinguished|adjunct|full|research)?\s*professor"
    r"(?:\s+(?:in|of|at)\s+[A-Za-z &-]+)?|research scientist|scientist|lecturer|director)\b",
    re.IGNORECASE,
)
GENERIC_EMAIL_WORDS = {
    "admin", "assistant", "contact", "coordinator", "info", "office", "support", "webmaster",
}


@dataclass(slots=True)
class UCSDDirectoryEntry:
    name: str
    profile_url: str


@dataclass(slots=True)
class UCSDProfileDetails:
    email: str = ""
    website_url: str = "Not publicly available"
    title: str = "Faculty"


@dataclass(slots=True)
class UCSDResearchDetails:
    title: str = "Not publicly available"
    interests: list[str] = field(default_factory=list)
    website_url: str = "Not publicly available"


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _looks_like_name(text: str) -> bool:
    cleaned = _clean(text).strip(" |–—-")
    words = cleaned.split()
    if not 2 <= len(words) <= 8 or len(cleaned) > 90:
        return False
    if any(char.isdigit() for char in cleaned):
        return False
    blocked = {
        "faculty profiles", "department leadership", "continuing lecturers", "faculty",
        "researcher", "adjunct", "affiliated", "emeritus", "primary faculty", "affiliated faculty",
        "computer science and engineering", "electrical and computer engineering",
    }
    return cleaned.lower() not in blocked and sum(char.isalpha() for char in cleaned) >= 4


def _choose_email(emails: list[str], name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    parts = [part for part in re.findall(r"[a-z]+", ascii_text.lower()) if len(part) > 1]
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
        if domain.endswith("ucsd.edu"):
            score += 6
        elif domain.endswith(".edu"):
            score += 2
        if last and last in compact:
            score += 5
        if first and first in compact:
            score += 3
        if first and last and compact.startswith(first[0]) and last in compact:
            score += 2
        if any(word in local for word in GENERIC_EMAIL_WORDS):
            score -= 15
        if score > best_score and score >= 6:
            best_score = score
            best = email
    return best


def parse_ucsd_directory_html(
    html_text: str,
    base_url: str = UCSD_FACULTY_DIRECTORY_URL,
) -> list[UCSDDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[UCSDDirectoryEntry] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href")))
        parsed = urlparse(href)
        path = parsed.path.rstrip("/")
        marker = "/people/faculty-profiles/"
        if marker not in path or path.endswith("/faculty-profiles") or path.endswith("/faculty"):
            continue
        name = _clean(anchor.get_text(" ", strip=True))
        if not _looks_like_name(name):
            image = anchor.find("img", alt=True)
            name = _clean(str(image.get("alt", ""))) if image else ""
        if not _looks_like_name(name) or href in seen_urls:
            continue
        seen_urls.add(href)
        entries.append(UCSDDirectoryEntry(name=name, profile_url=href))
    return entries


def parse_ucsd_profile_html(html_text: str, profile_url: str, name: str) -> UCSDProfileDetails:
    soup = BeautifulSoup(html_text, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    email = _choose_email(EMAIL_RE.findall(text), name)
    website = "Not publicly available"

    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True)).lower()
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(profile_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        score = 0
        if label == "website":
            score = 100
        elif "lab" in label:
            score = 95
        elif "homepage" in label or "personal" in label:
            score = 90
        if score:
            candidates.append((score, absolute))
    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1]))
        website = candidates[0][1]

    return UCSDProfileDetails(email=email, website_url=website, title="Faculty")


def _merge_detail(
    details: dict[str, UCSDResearchDetails],
    name: str,
    *,
    interests: str,
    title: str = "Not publicly available",
    website_url: str = "Not publicly available",
) -> None:
    key = _normalize_name(name)
    if not key:
        return
    detail = details.setdefault(key, UCSDResearchDetails())
    clean_interest = _clean(interests)
    if clean_interest and clean_interest != "Not publicly available" and clean_interest not in detail.interests:
        detail.interests.append(clean_interest)
    if detail.title == "Not publicly available" and title != "Not publicly available":
        detail.title = _clean(title)
    if detail.website_url == "Not publicly available" and website_url != "Not publicly available":
        detail.website_url = website_url


def parse_ucsd_ai_faculty_html(
    html_text: str,
    base_url: str = UCSD_AI_FACULTY_URL,
) -> dict[str, UCSDResearchDetails]:
    soup = BeautifulSoup(html_text, "html.parser")
    details: dict[str, UCSDResearchDetails] = {}

    # Names may be headings or ordinary links. The page itself identifies all of them
    # as CSE-affiliated AI faculty, so the published area is a reliable fallback.
    for tag in soup.find_all(["h4", "h5", "a"]):
        name = _clean(tag.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue
        href = "Not publicly available"
        if tag.name == "a" and tag.get("href"):
            href = urljoin(base_url, str(tag.get("href")))
        elif isinstance(tag, Tag):
            link = tag.find("a", href=True)
            if link:
                href = urljoin(base_url, str(link.get("href")))
        _merge_detail(
            details,
            name,
            interests="Artificial intelligence and machine learning",
            title="Faculty",
            website_url=href,
        )
    return details


def parse_ucsd_nlp_people_html(
    html_text: str,
    base_url: str = UCSD_NLP_PEOPLE_URL,
) -> dict[str, UCSDResearchDetails]:
    soup = BeautifulSoup(html_text, "html.parser")
    details: dict[str, UCSDResearchDetails] = {}

    for block in soup.find_all(["p", "div", "li"]):
        text = _clean(block.get_text(" ", strip=True))
        if not 70 <= len(text) <= 1800:
            continue
        lowered = text.lower()
        if not any(phrase in lowered for phrase in ("research", "works on", "studies", "focused on")):
            continue
        anchor = block.find("a", href=True)
        if not anchor:
            continue
        name = _clean(anchor.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue
        title_match = TITLE_RE.search(text)
        title = _clean(title_match.group(1)) if title_match else "Not publicly available"
        website = urljoin(base_url, str(anchor.get("href")))
        # Remove stale recruiting status from the research summary.
        summary = re.split(r"\b(?:He|She|They) is (?:not )?currently (?:accepting|recruiting)", text)[0]
        _merge_detail(
            details,
            name,
            interests=f"Natural language processing; {_clean(summary)}",
            title=title,
            website_url=website,
        )
    return details


def _text_lines(soup: BeautifulSoup) -> list[str]:
    return [
        _clean(line)
        for line in soup.get_text("\n").splitlines()
        if _clean(line)
    ]


def _summary_before_faculty(soup: BeautifulSoup) -> str:
    heading = soup.find(["h1", "h2"], string=lambda value: value and "intelligent systems" in _clean(value).lower())
    if not heading:
        return "Intelligent systems, robotics, autonomous systems, machine learning, and control"

    paragraphs: list[str] = []
    for element in heading.next_elements:
        if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3"}:
            label = _clean(element.get_text(" ", strip=True)).lower()
            if label in {"faculty", "adjunct faculty", "affiliated faculty", "emeritus faculty"}:
                break
        if isinstance(element, Tag) and element.name == "p":
            text = _clean(element.get_text(" ", strip=True))
            if 30 <= len(text) <= 900 and text not in paragraphs:
                paragraphs.append(text)
    if not paragraphs:
        return "Intelligent systems, robotics, autonomous systems, machine learning, and control"
    return " ".join(paragraphs[:2])


def _parse_ucsd_ece_robotics_cards(
    soup: BeautifulSoup,
    base_url: str,
) -> dict[str, UCSDResearchDetails]:
    details: dict[str, UCSDResearchDetails] = {}
    page_summary = _summary_before_faculty(soup)

    for heading in soup.find_all("h3"):
        name = _clean(heading.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue

        block_parts: list[str] = []
        links: list[Tag] = []
        for element in heading.next_elements:
            if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3"}:
                break
            if isinstance(element, Tag) and element.name == "a" and element.get("href"):
                links.append(element)
            if isinstance(element, NavigableString):
                parent = element.parent
                if isinstance(parent, Tag) and parent.name in {"script", "style", "noscript"}:
                    continue
                text = _clean(str(element))
                if text and text not in block_parts:
                    block_parts.append(text)

        block_text = " ".join(block_parts)
        title_match = TITLE_RE.search(block_text)
        email = _choose_email(EMAIL_RE.findall(block_text), name)
        if not title_match and not email:
            continue

        title = _clean(title_match.group(1)) if title_match else "Faculty"
        website = "Not publicly available"
        website_candidates: list[tuple[int, str]] = []
        for anchor in links:
            label = _clean(anchor.get_text(" ", strip=True)).lower()
            href = str(anchor.get("href", "")).strip()
            if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            host = parsed.netloc.lower()
            if any(
                blocked in host
                for blocked in (
                    "linkedin.com", "facebook.com", "instagram.com",
                    "twitter.com", "x.com", "youtube.com", "marktechpost.com",
                )
            ):
                continue
            score = 0
            if "lab" in label:
                score = 110
            elif label in {"website", "web page", "homepage", "personal website"}:
                score = 105
            elif "website" in label or "web page" in label:
                score = 100
            elif "full profile" in label:
                score = 40
            if score:
                website_candidates.append((score, absolute))
        if website_candidates:
            website_candidates.sort(key=lambda item: (-item[0], item[1]))
            website = website_candidates[0][1]

        _merge_detail(
            details,
            name,
            interests=f"Intelligent systems, robotics, and control; {page_summary}",
            title=title,
            website_url=website,
        )
    return details


def _parse_ucsd_legacy_robotics_page(
    soup: BeautifulSoup,
    base_url: str,
) -> dict[str, UCSDResearchDetails]:
    lines = _text_lines(soup)
    details: dict[str, UCSDResearchDetails] = {}
    try:
        start = lines.index("Computer Science and Engineering") + 1
        end = lines.index("Electrical and Computer Engineering", start)
    except ValueError:
        return details

    section = lines[start:end]
    title_phrase = "Computer Science and Engineering Professor"
    for index, line in enumerate(section):
        if line != title_phrase or index == 0:
            continue
        name = section[index - 1]
        if not _looks_like_name(name):
            continue
        summary_parts: list[str] = []
        cursor = index + 1
        while cursor < len(section):
            candidate = section[cursor]
            if candidate == title_phrase or (
                cursor + 1 < len(section) and section[cursor + 1] == title_phrase
            ):
                break
            if candidate.lower() not in {"website", "lab website"} and len(candidate) > 20:
                summary_parts.append(candidate)
            cursor += 1
        summary = " ".join(summary_parts[:4]) or "Robotics, autonomous systems, and intelligent machines"

        website = "Not publicly available"
        string_node = soup.find(string=lambda value: value and _clean(value) == name)
        if string_node:
            current = string_node.parent if isinstance(string_node.parent, Tag) else None
            for _ in range(6):
                if not current:
                    break
                for anchor in current.find_all("a", href=True):
                    label = _clean(anchor.get_text(" ", strip=True)).lower()
                    if "lab" in label or "website" in label or "center" in label:
                        website = urljoin(base_url, str(anchor.get("href")))
                        break
                if website != "Not publicly available":
                    break
                current = current.parent if isinstance(current.parent, Tag) else None

        _merge_detail(
            details,
            name,
            interests=f"Robotics; {summary}",
            title=title_phrase,
            website_url=website,
        )
    return details


def parse_ucsd_robotics_html(
    html_text: str,
    base_url: str = UCSD_ROBOTICS_FACULTY_URL,
) -> dict[str, UCSDResearchDetails]:
    """Parse the current official ECE robotics page, with legacy CRI support for tests/caches."""
    soup = BeautifulSoup(html_text, "html.parser")
    current = _parse_ucsd_ece_robotics_cards(soup, base_url)
    if current:
        return current
    return _parse_ucsd_legacy_robotics_page(soup, base_url)


def parse_ucsd_visual_html(
    html_text: str,
    base_url: str = UCSD_VISUAL_FACULTY_URL,
) -> dict[str, UCSDResearchDetails]:
    soup = BeautifulSoup(html_text, "html.parser")
    details: dict[str, UCSDResearchDetails] = {}
    current_department = "Not publicly available"

    for tag in soup.find_all(["h4", "h5"]):
        if tag.name == "h4":
            current_department = _clean(tag.get_text(" ", strip=True))
            continue
        name = _clean(tag.get_text(" ", strip=True))
        if not _looks_like_name(name):
            continue
        link = tag.find("a", href=True)
        website = urljoin(base_url, str(link.get("href"))) if link else "Not publicly available"
        paragraphs: list[str] = []
        for sibling in tag.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h4", "h5"}:
                break
            if isinstance(sibling, Tag):
                text = _clean(sibling.get_text(" ", strip=True))
                if 25 <= len(text) <= 1200:
                    paragraphs.append(text)
            elif isinstance(sibling, NavigableString):
                text = _clean(str(sibling))
                if len(text) >= 25:
                    paragraphs.append(text)
        summary = " ".join(paragraphs[:3]) or "Computer vision, computer graphics, and visual computing"
        title = (
            f"{current_department} Faculty"
            if current_department != "Not publicly available"
            else "Faculty"
        )
        _merge_detail(
            details,
            name,
            interests=f"Computer vision, computer graphics, and visual computing; {summary}",
            title=title,
            website_url=website,
        )
    return details


def merge_research_sources(*sources: dict[str, UCSDResearchDetails]) -> dict[str, UCSDResearchDetails]:
    merged: dict[str, UCSDResearchDetails] = {}
    for source in sources:
        for key, detail in source.items():
            target = merged.setdefault(key, UCSDResearchDetails())
            for interest in detail.interests:
                if interest not in target.interests:
                    target.interests.append(interest)
            if target.title in {"Not publicly available", "Faculty"} and detail.title != "Not publicly available":
                target.title = detail.title
            if target.website_url == "Not publicly available" and detail.website_url != "Not publicly available":
                target.website_url = detail.website_url
    return merged


class UCSDScraper(BaseUniversityScraper):
    university_name = "University of California, San Diego"
    directory_url = UCSD_FACULTY_DIRECTORY_URL

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

    def _safe_source(self, url: str, parser) -> dict[str, UCSDResearchDetails]:
        try:
            soup = self.get_soup(url)
            return parser(str(soup), url)
        except requests.RequestException as exc:
            LOGGER.warning("Could not read UCSD research source %s: %s", url, exc)
            return {}

    def scrape(self) -> list[ScrapedProfessor]:
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_ucsd_directory_html(str(directory_soup), self.directory_url)

        if self.progress_callback:
            self.progress_callback("Reading UC San Diego AI, NLP, robotics, and visual-computing sources...")
        research = merge_research_sources(
            self._safe_source(UCSD_AI_FACULTY_URL, parse_ucsd_ai_faculty_html),
            self._safe_source(UCSD_NLP_PEOPLE_URL, parse_ucsd_nlp_people_html),
            self._safe_source(UCSD_ROBOTICS_FACULTY_URL, parse_ucsd_robotics_html),
            self._safe_source(UCSD_VISUAL_FACULTY_URL, parse_ucsd_visual_html),
        )

        # During a smaller test refresh, prioritize faculty with an official research summary.
        entries.sort(key=lambda entry: (_normalize_name(entry.name) not in research, entry.name.lower()))
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking UC San Diego profile {index} of {total}: {entry.name}")
            try:
                profile_soup = self.get_soup(entry.profile_url)
                profile = parse_ucsd_profile_html(str(profile_soup), entry.profile_url, entry.name)
            except requests.RequestException as exc:
                LOGGER.warning("Could not inspect UCSD profile for %s: %s", entry.name, exc)
                continue
            if not profile.email:
                continue

            detail = research.get(_normalize_name(entry.name), UCSDResearchDetails())
            interests = (
                "; ".join(detail.interests)
                if detail.interests
                else "Computer Science and Engineering"
            )
            title = detail.title if detail.title != "Not publicly available" else profile.title
            website_url = profile.website_url
            if website_url == "Not publicly available":
                website_url = detail.website_url

            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department="Computer Science and Engineering",
                    title=title,
                    research_interests=interests,
                    email=profile.email,
                    website_url=website_url,
                    profile_url=entry.profile_url,
                    source_type=(
                        "Official UC San Diego CSE faculty profile and official research-group pages"
                    ),
                )
            )
        return records

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)

SJSU_FACULTY_URL = "https://www.sjsu.edu/cs/faculty/faculty.php"
SJSU_LECTURERS_URL = "https://www.sjsu.edu/cs/faculty/lecturers.php"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")

TITLE_TERMS = (
    "distinguished professor",
    "assistant professor",
    "associate professor",
    "professor and chair",
    "professor",
    "research scientist",
    "staff scientist",
    "lecturer",
    "instructor",
    "postdoctoral",
    "postdoc",
    "director",
)

BLOCKED_LINK_TEXT = {
    "office hours",
    "email",
    "research interests",
    "read more",
    "directory",
    "faculty",
    "cs faculty",
}

WEBSITE_LABEL_TERMS = (
    "personal website",
    "personal homepage",
    "academic website",
    "faculty website",
    "research website",
    "lab website",
    "laboratory",
    "research lab",
    "homepage",
    "website",
)


@dataclass(slots=True)
class SJSUDirectoryEntry:
    name: str
    title: str
    research_interests: str
    email: str
    profile_url: str
    website_url: str = "Not publicly available"
    source_text: str = ""


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip()




def _clean_person_name(value: str) -> str:
    """Remove image-label text that SJSU places next to lecturer names."""
    cleaned = _clean(value).strip(" |–—-,:;")
    patterns = (
        r"\s+image$",
        r"\s+thumbnail$",
        r"\s+photo$",
        r"['’]s\s+(?:image|thumbnail|photo)$",
    )
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _normalize_profile_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("sjsu.edu") and parsed.path.lower().startswith("/people/"):
        path = re.sub(r"/index\.html?$", "/", parsed.path, flags=re.IGNORECASE)
        if not path.endswith("/"):
            path += "/"
        return parsed._replace(path=path, params="", query="", fragment="").geturl()
    return url

def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _looks_like_name(value: str) -> bool:
    cleaned = _clean(value).strip("|–—-,:;")
    words = cleaned.split()
    if not 2 <= len(words) <= 8 or len(cleaned) > 90:
        return False
    if any(char.isdigit() for char in cleaned) or "@" in cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in BLOCKED_LINK_TEXT or any(term == lowered for term in TITLE_TERMS):
        return False
    return sum(char.isalpha() for char in cleaned) >= 5


def _choose_person_link(block: Tag, base_url: str) -> tuple[str, str]:
    candidates: list[tuple[int, str, str]] = []
    for anchor in block.find_all("a", href=True):
        label = _clean_person_name(anchor.get_text(" ", strip=True))
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if not _looks_like_name(label):
            image = anchor.find("img", alt=True)
            label = _clean_person_name(str(image.get("alt", ""))) if image else label
        if not _looks_like_name(label):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        score = 4
        if parsed.netloc.endswith("sjsu.edu"):
            score += 3
        if "/people/" in parsed.path.lower() or "/faculty/" in parsed.path.lower():
            score += 2
        candidates.append((score, label, absolute))

    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1].lower()))
        _, name, url = candidates[0]
        return name, url

    for image in block.find_all("img", alt=True):
        alt = _clean_person_name(str(image.get("alt", "")))
        alt = re.sub(r"^(?:prof\.?|professor|dr\.?)\s+", "", alt, flags=re.IGNORECASE)
        if _looks_like_name(alt):
            return alt, base_url

    return "", base_url


TITLE_CANONICAL = {
    "distinguished professor": "Distinguished Professor",
    "assistant professor": "Assistant Professor",
    "associate professor": "Associate Professor",
    "professor and chair": "Professor and Chair",
    "professor": "Professor",
    "research scientist": "Research Scientist",
    "staff scientist": "Staff Scientist",
    "lecturer": "Lecturer",
    "instructor": "Instructor",
    "postdoctoral": "Postdoctoral Researcher",
    "postdoc": "Postdoctoral Researcher",
    "director": "Director",
}


def _extract_title(text: str, default_title: str) -> str:
    """Return only the academic title, even when a directory row is flattened.

    SJSU faculty cards are often converted into one long text line by HTML
    parsers. Returning the whole line would accidentally mix the professor's
    name, phone, email, and research interests into the title field.
    """
    lowered = _clean(text).lower()
    for term in sorted(TITLE_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            return TITLE_CANONICAL.get(term, term.title())
    return default_title


def _extract_research(block: Tag, name: str, title: str, email: str) -> str:
    cells = block.find_all(["td", "th"], recursive=False) if block.name == "tr" else []
    if len(cells) >= 2:
        candidate = _clean(cells[-1].get_text(" ", strip=True))
        candidate = EMAIL_RE.sub("", candidate)
        candidate = PHONE_RE.sub("", candidate)
        if len(candidate) >= 3 and candidate.lower() not in {"research interests", "n/a"}:
            return candidate.strip(" ,;|")

    lines = []
    for raw in block.get_text("\n", strip=True).splitlines():
        line = _clean(raw)
        if not line or line in lines:
            continue
        if line.lower() in {name.lower(), title.lower(), "research interests"}:
            continue
        if email.lower() in line.lower() or EMAIL_RE.search(line) or PHONE_RE.fullmatch(line):
            continue
        if _looks_like_name(line):
            continue
        if any(term == line.lower() for term in TITLE_TERMS):
            continue
        lines.append(line)

    if lines:
        joined = "; ".join(lines)
        joined = re.sub(r"\s*[|•]\s*", "; ", joined)
        return joined[:1400].strip(" ,;") or "Not publicly available"
    return "Not publicly available"


def _smallest_email_block(email_node: Tag) -> Tag:
    current: Tag = email_node
    best: Tag = email_node
    for _ in range(8):
        parent = current.parent
        if not isinstance(parent, Tag):
            break
        current = parent
        text = _clean(current.get_text(" ", strip=True))
        emails = set(value.lower() for value in EMAIL_RE.findall(text))
        if current.name == "tr":
            return current
        if len(emails) == 1 and 20 <= len(text) <= 1800:
            best = current
        if len(emails) > 1 or current.name in {"main", "body", "html"}:
            break
    return best


def _directory_blocks(soup: BeautifulSoup) -> list[Tag]:
    blocks: list[Tag] = []
    seen: set[int] = set()

    for row in soup.find_all("tr"):
        if EMAIL_RE.search(row.get_text(" ", strip=True)):
            blocks.append(row)
            seen.add(id(row))

    for anchor in soup.find_all("a", href=re.compile(r"^mailto:", re.IGNORECASE)):
        block = _smallest_email_block(anchor)
        if id(block) not in seen:
            blocks.append(block)
            seen.add(id(block))

    if not blocks:
        for text_node in soup.find_all(string=EMAIL_RE):
            parent = text_node.parent
            if isinstance(parent, Tag):
                block = _smallest_email_block(parent)
                if id(block) not in seen:
                    blocks.append(block)
                    seen.add(id(block))
    return blocks


def parse_sjsu_directory_html(
    html_text: str,
    base_url: str = SJSU_FACULTY_URL,
    default_title: str = "Not publicly available",
) -> list[SJSUDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    entries: list[SJSUDirectoryEntry] = []
    seen_emails: set[str] = set()

    for block in _directory_blocks(soup):
        block_text = _clean(block.get_text(" ", strip=True))
        emails = [email.lower().strip(".,;:()[]{}<>\"'") for email in EMAIL_RE.findall(block_text)]
        emails = [email for email in emails if email.endswith("sjsu.edu") or "@" in email]
        if not emails:
            continue
        email = emails[0]
        if email in seen_emails:
            continue

        name, person_url = _choose_person_link(block, base_url)
        name = _clean_person_name(name)
        if not name:
            # Plain-text names usually appear before the title/email in a compact row.
            lines = [_clean(line) for line in block.get_text("\n", strip=True).splitlines()]
            name = next((line for line in lines if _looks_like_name(line)), "")
        if not name:
            continue

        title = _extract_title(block_text, default_title)
        interests = _extract_research(block, name, title, email)
        if interests == "Not publicly available":
            continue

        parsed = urlparse(person_url)
        looks_personal = (
            "~" in parsed.path
            or parsed.netloc.lower().startswith("www.cs.sjsu.edu")
            or (parsed.netloc and not parsed.netloc.endswith("sjsu.edu"))
        )
        if looks_personal:
            profile_url = base_url
            website_url = person_url
        else:
            profile_url = _normalize_profile_url(person_url)
            website_url = "Not publicly available"

        seen_emails.add(email)
        entries.append(
            SJSUDirectoryEntry(
                name=name,
                title=title,
                research_interests=interests,
                email=email,
                profile_url=profile_url,
                website_url=website_url,
                source_text=block_text,
            )
        )
    return entries


def extract_sjsu_website_url(html_text: str, profile_url: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[tuple[int, str]] = []
    profile_host = urlparse(profile_url).netloc.lower()

    for anchor in soup.find_all("a", href=True):
        label = _clean_person_name(anchor.get_text(" ", strip=True)).lower()
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(profile_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if absolute.rstrip("/") == profile_url.rstrip("/"):
            continue
        if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            continue
        if any(blocked in label for blocked in ("publication", "scholar", "linkedin", "cv", "curriculum vitae")):
            continue

        score = 0
        for position, term in enumerate(WEBSITE_LABEL_TERMS):
            if term in label:
                score = max(score, 100 - position * 4)
        if score == 0 and any(word in label for word in ("lab", "research group", "homepage")):
            score = 70
        if score == 0:
            continue
        if parsed.netloc.lower() != profile_host:
            score += 3
        candidates.append((score, absolute))

    if not candidates:
        return "Not publicly available"
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


class SJSUScraper(BaseUniversityScraper):
    university_name = "San Jose State University"
    directory_url = SJSU_FACULTY_URL

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
        all_entries: list[SJSUDirectoryEntry] = []
        sources = (
            (SJSU_FACULTY_URL, "Not publicly available"),
            (SJSU_LECTURERS_URL, "Lecturer"),
        )
        for url, default_title in sources:
            if self.progress_callback:
                self.progress_callback(f"Reading SJSU source: {url}")
            try:
                soup = self.get_soup(url)
                all_entries.extend(parse_sjsu_directory_html(str(soup), url, default_title))
            except requests.RequestException as exc:
                LOGGER.warning("Could not read SJSU faculty source %s: %s", url, exc)

        # Research-focused faculty first for smaller test refreshes.
        all_entries.sort(
            key=lambda entry: (
                "lecturer" in entry.title.lower(),
                -sum(
                    keyword in entry.research_interests.lower()
                    for keyword in ("artificial intelligence", "machine learning", "robotics", "nlp", "computer vision")
                ),
                entry.name.lower(),
            )
        )
        if self.max_profiles is not None:
            all_entries = all_entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(all_entries)
        for index, entry in enumerate(all_entries, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking SJSU record {index} of {total}: {entry.name}")

            website_url = entry.website_url
            opportunity_text = entry.source_text
            source_url = entry.profile_url
            if entry.profile_url != SJSU_FACULTY_URL and entry.profile_url != SJSU_LECTURERS_URL:
                try:
                    profile_soup = self.get_soup(entry.profile_url)
                    profile_html = str(profile_soup)
                    profile_text = _clean(profile_soup.get_text(" ", strip=True))
                    opportunity_text = f"{opportunity_text} {profile_text}"
                    discovered = extract_sjsu_website_url(profile_html, entry.profile_url)
                    if discovered != "Not publicly available":
                        website_url = discovered
                        source_url = discovered
                except requests.RequestException as exc:
                    LOGGER.warning("Could not inspect SJSU profile for %s: %s", entry.name, exc)

            base_record = {
                "title": entry.title,
                "research_interests": entry.research_interests,
                "website_url": website_url,
                "profile_url": entry.profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=opportunity_text,
                source_url=source_url,
            )
            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department="Computer Science",
                    title=entry.title,
                    research_interests=entry.research_interests,
                    email=entry.email,
                    website_url=website_url,
                    profile_url=entry.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type="Official SJSU Computer Science faculty and lecturer directories",
                )
            )
        return records

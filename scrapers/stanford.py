from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor


AI_DIRECTORY_URL = "https://ai.stanford.edu/faculty/"
CS_DIRECTORY_URL = "https://www.cs.stanford.edu/people-cs/faculty-name"

STANFORD_PROFILE_OVERRIDES = {
    "christopherpiech": "https://profiles.stanford.edu/christopher-piech",
    "chrispiech": "https://profiles.stanford.edu/christopher-piech",
    "danyamins": "https://profiles.stanford.edu/daniel-yamins",
    "danielyamins": "https://profiles.stanford.edu/daniel-yamins",
    "emmabrunskill": "https://profiles.stanford.edu/emma-brunskill",
    "ehsanadeli": "https://profiles.stanford.edu/ehsan-adeli",
    "jameszou": "https://profiles.stanford.edu/james-zou",
}


BLOCKED_HEADING_WORDS = {
    "faculty",
    "people",
    "research",
    "artificial intelligence",
    "machine learning",
    "computer science",
    "former faculty",
    "former & emeritus faculty",
    "emeritus faculty",
    "about",
    "contact",
    "news",
    "read more",
}

GENERIC_EMAIL_LOCALS = {
    "admin",
    "admissions",
    "assistant",
    "communications",
    "contact",
    "coordinator",
    "events",
    "info",
    "media",
    "office",
    "support",
    "webmaster",
}

EMAIL_RE = re.compile(
    r"(?<![A-Z0-9._%+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![A-Z0-9._%+-])",
    re.IGNORECASE,
)

WEBSITE_LABEL_SCORES = (
    ("academic website", 110),
    ("personal homepage", 105),
    ("personal website", 105),
    ("faculty homepage", 100),
    ("home page", 95),
    ("homepage", 95),
    ("lab website", 92),
    ("research lab", 90),
    ("laboratory", 88),
    ("research group", 85),
    ("website", 70),
)

WEBSITE_BLOCKED_LABELS = {
    "google scholar", "publications", "selected publications", "cv", "curriculum vitae",
    "linkedin", "twitter", "x", "github", "contact", "email", "profile",
    "faculty profile", "stanford profile", "read more",
}


@dataclass(slots=True)
class StanfordDirectoryEntry:
    name: str
    research_interests: str = "Not publicly available"
    title: str = "Not publicly available"
    website_url: str = "Not publicly available"
    profile_url: str = "Not publicly available"


def normalize_person_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _clean_stanford_title(title: str) -> str:
    cleaned = " ".join(str(title).split()).strip(" |–—-,:;")
    cleaned = re.sub(r"\s+Stanford University$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or "Not publicly available"


def _official_profile_url(name: str, fallback: str) -> str:
    return STANFORD_PROFILE_OVERRIDES.get(normalize_person_name(name), fallback)


def looks_like_person_name(value: str) -> bool:
    cleaned = " ".join(value.split()).strip(" |–—-")
    lowered = cleaned.lower()
    if not cleaned or lowered in BLOCKED_HEADING_WORDS:
        return False
    if any(blocked in lowered for blocked in ("former faculty", "research focus")):
        return False
    words = cleaned.split()
    if not 2 <= len(words) <= 7:
        return False
    if len(cleaned) > 80 or any(char.isdigit() for char in cleaned):
        return False
    letter_count = sum(char.isalpha() for char in cleaned)
    return letter_count >= 4


def _closest_card(heading: Tag, require_read_more: bool = False) -> Tag:
    current: Tag | None = heading
    fallback = heading.parent if isinstance(heading.parent, Tag) else heading

    for _ in range(7):
        parent = current.parent if isinstance(current, Tag) else None
        if not isinstance(parent, Tag):
            break
        current = parent
        headings = parent.find_all(["h2", "h3", "h4", "h5"])
        links = parent.find_all("a", href=True)
        text_length = len(parent.get_text(" ", strip=True))
        has_read_more = any("read more" in link.get_text(" ", strip=True).lower() for link in links)

        if links and len(headings) <= 2 and text_length <= 1600:
            fallback = parent
            if not require_read_more or has_read_more:
                return parent

    return fallback


def _best_link(card: Tag, base_url: str, *, prefer_read_more: bool = False) -> str:
    links = card.find_all("a", href=True)
    if prefer_read_more:
        for link in links:
            if "read more" in link.get_text(" ", strip=True).lower():
                return BaseUniversityScraper.absolute_url(base_url, link.get("href"))

    for link in links:
        href = str(link.get("href", "")).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        if href.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")):
            continue
        return BaseUniversityScraper.absolute_url(base_url, href)
    return "Not publicly available"


def _card_summary(card: Tag, name: str) -> str:
    chunks: list[str] = []
    for paragraph in card.find_all(["p", "div", "span"], recursive=True):
        text = " ".join(paragraph.get_text(" ", strip=True).split())
        lowered = text.lower()
        if not text or text == name or lowered == "read more":
            continue
        if len(text) > 500:
            continue
        if text not in chunks:
            chunks.append(text)

    for text in chunks:
        candidate = text.replace(name, "").replace("Read More", "").strip(" |–—-")
        if 3 <= len(candidate) <= 350 and looks_like_research_text(candidate):
            return candidate

    full_text = " ".join(card.get_text(" ", strip=True).split())
    candidate = full_text.replace(name, "").replace("Read More", "").strip(" |–—-")
    return candidate[:350] if candidate else "Not publicly available"


def looks_like_research_text(text: str) -> bool:
    lowered = text.lower()
    research_terms = (
        "learning",
        "robot",
        "vision",
        "language",
        "intelligence",
        "comput",
        "data",
        "graphics",
        "reasoning",
        "systems",
        "networks",
        "genomics",
        "health",
        "optimization",
        "interaction",
        "science",
        "control",
        "security",
    )
    return any(term in lowered for term in research_terms) or "," in text or "&" in text


def parse_ai_directory_html(html_text: str, base_url: str = AI_DIRECTORY_URL) -> list[StanfordDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    merged: dict[str, StanfordDirectoryEntry] = {}

    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        name = " ".join(heading.get_text(" ", strip=True).split())
        if not looks_like_person_name(name):
            continue

        card = _closest_card(heading, require_read_more=True)
        website_url = _best_link(card, base_url, prefer_read_more=True)
        interests = _card_summary(card, name)
        key = normalize_person_name(name)
        if not key:
            continue

        existing = merged.get(key)
        if not existing:
            merged[key] = StanfordDirectoryEntry(
                name=name,
                research_interests=interests,
                website_url=website_url,
                profile_url=base_url,
            )
            continue

        if existing.research_interests == "Not publicly available" and interests != "Not publicly available":
            existing.research_interests = interests
        if existing.website_url == "Not publicly available" and website_url != "Not publicly available":
            existing.website_url = website_url

    return list(merged.values())


def _content_until_next_heading(heading: Tag) -> list[str]:
    pieces: list[str] = []
    for element in heading.next_elements:
        if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3", "h4", "h5"}:
            break
        if isinstance(element, NavigableString):
            parent = element.parent
            if isinstance(parent, Tag) and parent.name in {"script", "style", "noscript"}:
                continue
            text = " ".join(str(element).split())
            if text and text not in pieces:
                pieces.append(text)
    return pieces


def parse_cs_directory_html(html_text: str, base_url: str = CS_DIRECTORY_URL) -> dict[str, StanfordDirectoryEntry]:
    soup = BeautifulSoup(html_text, "html.parser")
    entries: dict[str, StanfordDirectoryEntry] = {}

    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        name = " ".join(heading.get_text(" ", strip=True).split())
        if not looks_like_person_name(name):
            continue

        link = heading.find("a", href=True)
        profile_url = (
            BaseUniversityScraper.absolute_url(base_url, link.get("href"))
            if link else "Not publicly available"
        )
        title = _extract_title_from_lines(_content_until_next_heading(heading), name)
        key = normalize_person_name(name)
        if key:
            entries[key] = StanfordDirectoryEntry(
                name=name,
                title=title,
                profile_url=profile_url,
            )

    return entries


def _extract_title_from_lines(lines: list[str], name: str) -> str:
    title_terms = ("professor", "lecturer", "research", "director", "scientist", "fellow")
    for line in lines:
        cleaned = line.replace(name, "").strip(" |–—-")
        if not cleaned or len(cleaned) > 600:
            continue
        if any(term in cleaned.lower() for term in title_terms):
            return cleaned
    return "Not publicly available"


def _extract_title(card: Tag, name: str) -> str:
    return _extract_title_from_lines(_content_until_next_heading(card), name)



def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_generic_stanford_profile_url(url: str) -> bool:
    """Return True for directory/profile pages rather than personal or lab sites."""
    if not _is_http_url(url):
        return True
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/").lower()

    if host == "ai.stanford.edu" and (path.startswith("/~") or path.startswith("/groups/") or "lab" in path):
        return False
    if host.endswith("stanford.edu") and (path.startswith("/~") or "/lab" in path or "/labs/" in path):
        return False

    generic_patterns = (
        "/people/", "/people-cs/", "/faculty/", "/profiles/", "/profile/",
    )
    return any(pattern in f"{path}/" for pattern in generic_patterns) or url.rstrip("/") in {
        AI_DIRECTORY_URL.rstrip("/"), CS_DIRECTORY_URL.rstrip("/")
    }


def extract_stanford_website_url(
    html_text: str,
    page_url: str,
    profile_url: str = "Not publicly available",
) -> str:
    """Find a professor's public academic homepage or lab from a Stanford page.

    Stanford pages use labels such as "Academic website", "Homepage", and
    "Research Lab". We reject social profiles, publication links, files, and the
    official faculty profile itself. A direct Stanford tilde page is treated as a
    personal homepage even when the page does not contain a labeled website link.
    """
    page_url = page_url.strip()
    profile_url = profile_url.strip()

    if _is_http_url(page_url) and not _is_generic_stanford_profile_url(page_url):
        return page_url

    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[tuple[int, str]] = []
    page_host = urlparse(page_url).netloc.lower()

    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.get_text(" ", strip=True).lower().split())
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "javascript:", "tel:", "#")):
            continue
        if label in WEBSITE_BLOCKED_LABELS:
            continue

        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx")):
            continue
        if absolute.rstrip("/") in {page_url.rstrip("/"), profile_url.rstrip("/")}:
            continue

        score = 0
        padded_label = f" {label} "
        for phrase, phrase_score in WEBSITE_LABEL_SCORES:
            if phrase in padded_label:
                score = max(score, phrase_score)

        if score == 0 and any(word in label for word in (" lab", "lab ", "group", "center")):
            score = 72
        if score == 0:
            continue

        if parsed.netloc.lower() != page_host:
            score += 3
        if parsed.path.startswith("/~"):
            score += 8
        candidates.append((score, absolute))

    if not candidates:
        return "Not publicly available"

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]

def infer_stanford_department(title: str) -> str:
    departments = ["Computer Science"]
    lowered = title.lower()
    mappings = [
        ("electrical engineering", "Electrical Engineering"),
        ("psychology", "Psychology"),
        ("linguistics", "Linguistics"),
        ("statistics", "Statistics"),
        ("medicine", "Medicine"),
        ("genetics", "Genetics"),
        ("biomedical data science", "Biomedical Data Science"),
        ("education", "Education"),
    ]
    for phrase, label in mappings:
        if phrase in lowered and label not in departments:
            departments.append(label)
    return "; ".join(departments)

def deobfuscate_email_text(text: str) -> str:
    result = text
    # Handle common forms such as name [at] cs [dot] stanford [dot] edu
    # without replacing the letters "at" or "dot" inside ordinary words.
    replacements = [
        (r"(?i)(?<=\w)\s*(?:\[|\()\s*at\s*(?:\]|\))\s*(?=\w)", "@"),
        (r"(?i)(?<=\w)\s+at\s+(?=\w)", "@"),
        (r"(?i)(?<=\w)\s*(?:\[|\()\s*dot\s*(?:\]|\))\s*(?=\w)", "."),
        (r"(?i)(?<=\w)\s+dot\s+(?=\w)", "."),
    ]
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)
    return result


def extract_public_emails(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[str] = []

    for link in soup.select('a[href^="mailto:"]'):
        value = str(link.get("href", "")).split(":", 1)[-1].split("?", 1)[0]
        candidates.extend(EMAIL_RE.findall(value))

    visible_text = soup.get_text(" ", strip=True)
    candidates.extend(EMAIL_RE.findall(visible_text))
    candidates.extend(EMAIL_RE.findall(deobfuscate_email_text(visible_text)))

    cleaned: list[str] = []
    for email in candidates:
        normalized = email.strip(".,;:()[]{}<>\"'").lower()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def choose_professional_email(emails: Iterable[str], person_name: str) -> str:
    name_parts = [
        part
        for part in re.sub(r"[^a-zA-Z\s-]", " ", unicodedata.normalize("NFKD", person_name)).lower().split()
        if len(part) >= 2
    ]
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if name_parts else ""

    best_email = ""
    best_score = -100
    for email in emails:
        if "@" not in email:
            continue
        local, domain = email.lower().split("@", 1)
        if not re.fullmatch(r"[a-z0-9._%+-]+", local):
            continue
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
            continue

        score = 0
        if domain.endswith("stanford.edu"):
            # A current Stanford-domain address should outrank an older email
            # that may still appear on a personal page from a previous institution.
            score += 12
        elif domain.endswith(".edu"):
            score += 2

        compact_local = re.sub(r"[^a-z0-9]", "", local)
        if last and last in compact_local:
            score += 5
        if first and first in compact_local:
            score += 3
        if first and last and compact_local.startswith(first[0]) and last in compact_local:
            score += 2
        if first and last and compact_local.startswith(first[0] + last[:4]):
            score += 4
        if local in GENERIC_EMAIL_LOCALS or any(word in local for word in GENERIC_EMAIL_LOCALS):
            score -= 10

        # Avoid choosing unrelated addresses collected from navigation/footer content.
        if score > best_score and score >= 7:
            best_score = score
            best_email = email.lower()

    return best_email


def _name_tokens(name: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.findall(r"[a-z]+", ascii_text.lower())


def _find_cs_entry(
    name: str, cs_entries: dict[str, StanfordDirectoryEntry]
) -> StanfordDirectoryEntry | None:
    exact = cs_entries.get(normalize_person_name(name))
    if exact:
        return exact

    target_tokens = _name_tokens(name)
    if len(target_tokens) < 2:
        return None
    target_last = target_tokens[-1]
    target_given = target_tokens[:-1]
    matches: list[StanfordDirectoryEntry] = []

    for candidate in cs_entries.values():
        candidate_tokens = _name_tokens(candidate.name)
        if len(candidate_tokens) < 2 or candidate_tokens[-1] != target_last:
            continue
        candidate_given = candidate_tokens[:-1]
        given_match = any(
            left == right or left.startswith(right) or right.startswith(left)
            for left in target_given
            for right in candidate_given
            if len(left) >= 2 and len(right) >= 2
        )
        if given_match:
            matches.append(candidate)

    return matches[0] if len(matches) == 1 else None


def merge_directory_entries(
    ai_entries: Iterable[StanfordDirectoryEntry],
    cs_entries: dict[str, StanfordDirectoryEntry],
) -> list[StanfordDirectoryEntry]:
    merged: list[StanfordDirectoryEntry] = []
    for entry in ai_entries:
        cs_entry = _find_cs_entry(entry.name, cs_entries)
        if cs_entry:
            entry.title = _clean_stanford_title(cs_entry.title)
            if cs_entry.profile_url != "Not publicly available":
                entry.profile_url = cs_entry.profile_url
        entry.title = _clean_stanford_title(entry.title)
        entry.profile_url = _official_profile_url(entry.name, entry.profile_url)
        merged.append(entry)
    return merged


class StanfordScraper(BaseUniversityScraper):
    university_name = "Stanford University"
    directory_url = AI_DIRECTORY_URL

    def __init__(
        self,
        request_delay: float = 0.6,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback

    def scrape(self) -> list[ScrapedProfessor]:
        ai_soup = self.get_soup(AI_DIRECTORY_URL)
        cs_soup = self.get_soup(CS_DIRECTORY_URL)

        ai_entries = parse_ai_directory_html(str(ai_soup), AI_DIRECTORY_URL)
        cs_entries = parse_cs_directory_html(str(cs_soup), CS_DIRECTORY_URL)
        directory_entries = merge_directory_entries(ai_entries, cs_entries)

        if self.max_profiles is not None:
            directory_entries = directory_entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(directory_entries)
        for index, entry in enumerate(directory_entries, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking Stanford profile {index} of {total}: {entry.name}")
            emails: list[str] = []
            website_url = "Not publicly available"

            # Read the Stanford AI directory destination when available, but do
            # not discard the record when a personal page is blocked or stale.
            if entry.website_url != "Not publicly available":
                try:
                    source_soup = self.get_soup(entry.website_url)
                    source_html = str(source_soup)
                    emails.extend(extract_public_emails(source_html))
                    website_url = extract_stanford_website_url(
                        source_html,
                        entry.website_url,
                        entry.profile_url,
                    )
                except Exception:
                    pass

            # Always inspect the official Stanford profile when one is available.
            # This lets current Stanford emails and officially listed homepages
            # outrank stale addresses or websites left on older personal pages.
            if entry.profile_url != "Not publicly available":
                try:
                    official_soup = self.get_soup(entry.profile_url)
                    official_html = str(official_soup)
                    emails.extend(extract_public_emails(official_html))
                    official_website = extract_stanford_website_url(
                        official_html,
                        entry.profile_url,
                        entry.profile_url,
                    )
                    if official_website != "Not publicly available":
                        website_url = official_website
                except Exception:
                    pass

            email = choose_professional_email(emails, entry.name)
            if not email:
                continue

            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department=infer_stanford_department(entry.title),
                    title=entry.title,
                    research_interests=entry.research_interests,
                    email=email,
                    website_url=website_url,
                    profile_url=entry.profile_url,
                    source_type="Official Stanford directories and public academic website",
                )
            )

        return records

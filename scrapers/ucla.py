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

UCLA_RESEARCH_AREAS_URL = "https://www.cs.ucla.edu/research-areas/"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)

TITLE_TERMS = (
    "assistant professor",
    "associate professor",
    "distinguished professor",
    "chancellor's professor",
    "chancellors professor",
    "professor emeritus",
    "professor",
    "research scientist",
    "researcher",
    "lecturer",
    "postdoctoral",
    "postdoc",
    "director",
)

GENERIC_EMAIL_WORDS = {
    "admin",
    "admissions",
    "assistant",
    "contact",
    "coordinator",
    "info",
    "office",
    "support",
    "webmaster",
    "cssi",
}

BLOCKED_LINK_LABELS = {
    "google scholar profile",
    "curriculum vitae",
    "cv",
    "bibtex",
    "publications",
    "selected publications",
    "open the bio in a new tab",
    "read more",
}

RESEARCH_HEADING_PHRASES = (
    "research and interests",
    "research interests",
    "research areas",
    "research",
)

# Reviewed spellings/nicknames on these exact official profile URLs. Keep
# unrelated people and pages subject to the strict identity check.
PROFILE_NAME_ALIASES = {
    "/people/nanyun-peng/": {"nanyunpeng", "nanyunvioletpeng"},
    "/people/jason-jingsheng-cong/": {"jasonjinshengcong", "jasonjingshengcong"},
}


def _profile_name_matches(actual: str, expected: str, page_url: str) -> bool:
    actual_key = _normalize_person_name(actual)
    expected_key = _normalize_person_name(expected)
    if actual_key == expected_key:
        return True
    url = urlparse(page_url)
    aliases = PROFILE_NAME_ALIASES.get(url.path.rstrip("/") + "/", set())
    return url.scheme == "https" and url.hostname == "samueli.ucla.edu" and actual_key in aliases and expected_key in aliases


@dataclass(slots=True)
class UCLAResearchEntry:
    name: str
    profile_url: str
    website_url: str = "Not publicly available"
    areas: list[str] = field(default_factory=list)
    area_descriptions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class UCLAProfileDetails:
    title: str = "Not publicly available"
    department: str = "Computer Science"
    email: str = ""
    research_interests: str = "Not publicly available"
    website_url: str = "Not publicly available"


def _clean(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _normalize_person_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _looks_like_person_name(text: str) -> bool:
    cleaned = _clean(text).strip(" |–—-")
    words = cleaned.split()
    if not 2 <= len(words) <= 8:
        return False
    if len(cleaned) > 90 or any(char.isdigit() for char in cleaned):
        return False
    blocked = {
        "artificial intelligence",
        "computer science theory",
        "computer system architecture & cad",
        "computational systems biology",
        "graphics & vision",
        "human computer interaction",
        "information & data management",
        "network systems",
        "software systems",
        "terms of use",
        "privacy policy",
        "accessibility",
        "contact us",
        "research areas",
        "faculty directory",
    }
    return cleaned.lower() not in blocked and sum(ch.isalpha() for ch in cleaned) >= 4


def _section_nodes(heading: Tag):
    for element in heading.next_elements:
        if isinstance(element, Tag) and element is not heading and element.name == heading.name:
            break
        yield element


def _section_description(heading: Tag) -> str:
    for element in _section_nodes(heading):
        if isinstance(element, Tag) and element.name in {"p", "div"}:
            text = _clean(element.get_text(" ", strip=True))
            if 30 <= len(text) <= 900:
                return text
    return "Not publicly available"


def parse_ucla_research_areas_html(
    html_text: str,
    base_url: str = UCLA_RESEARCH_AREAS_URL,
) -> list[UCLAResearchEntry]:
    """Parse UCLA CS research-area membership into one merged entry per person."""
    soup = BeautifulSoup(html_text, "html.parser")
    merged: dict[str, UCLAResearchEntry] = {}

    for heading in soup.find_all(["h2", "h3"]):
        area = _clean(heading.get_text(" ", strip=True))
        if not area or area.lower() in {"research areas", "in the news", "education", "courses"}:
            continue

        description = _section_description(heading)
        for element in _section_nodes(heading):
            if not isinstance(element, Tag) or element.name != "a" or not element.get("href"):
                continue
            name = _clean(element.get_text(" ", strip=True))
            if not _looks_like_person_name(name):
                continue

            href = urljoin(base_url, str(element.get("href")))
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            if any(token in href.lower() for token in ("facebook.com", "twitter.com", "instagram.com", "linkedin.com")):
                continue

            key = _normalize_person_name(name)
            if not key:
                continue
            existing = merged.get(key)
            is_official_profile = "samueli.ucla.edu/people/" in href.lower()
            if not existing:
                existing = UCLAResearchEntry(
                    name=name,
                    profile_url=href if is_official_profile else base_url,
                    website_url="Not publicly available" if is_official_profile else href,
                )
                merged[key] = existing
            else:
                if is_official_profile:
                    existing.profile_url = href
                elif existing.website_url == "Not publicly available":
                    existing.website_url = href

            if area not in existing.areas:
                existing.areas.append(area)
            if description != "Not publicly available" and description not in existing.area_descriptions:
                existing.area_descriptions.append(description)

    return list(merged.values())


def _choose_email(emails: list[str], name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    name_parts = [part for part in re.findall(r"[a-z]+", ascii_text.lower()) if len(part) > 1]
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if name_parts else ""
    best = ""
    best_score = -100

    for raw in emails:
        email = raw.lower().strip(".,;:()[]{}<>\"'")
        if "@" not in email:
            continue
        local, domain = email.split("@", 1)
        compact = re.sub(r"[^a-z0-9]", "", local)
        score = 0
        if domain.endswith("ucla.edu"):
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


def _lines_after_h1(soup: BeautifulSoup | Tag, name: str, max_lines: int = 60) -> list[str]:
    heading = next((h for h in soup.find_all("h1")
                    if _normalize_person_name(h.get_text(" ", strip=True)) == _normalize_person_name(name)), None)
    if not heading:
        return []
    lines: list[str] = []
    for element in heading.next_elements:
        if soup not in element.parents:
            break
        if isinstance(element, Tag) and element is not heading and element.name == "h2":
            break
        if isinstance(element, NavigableString):
            parent = element.parent
            if isinstance(parent, Tag) and (
                parent.name in {"nav", "footer", "script", "style", "noscript"}
                or parent.find_parent(["nav", "footer", "script", "style", "noscript"])
            ):
                continue
            text = _clean(str(element))
            if text and text not in lines:
                lines.append(text)
            if len(lines) >= max_lines:
                break
    return lines


def _extract_title(lines: list[str]) -> str:
    for line in lines:
        lowered = line.lower()
        if any(re.search(r"\b" + re.escape(term) + r"\b", lowered) for term in TITLE_TERMS) and len(line) <= 160:
            return line.title() if line.isupper() else line
    return "Not publicly available"


def _extract_department(lines: list[str]) -> str:
    department_names = (
        "Computer Science",
        "Electrical and Computer Engineering",
        "Computational Medicine",
        "Bioengineering",
        "Data Science",
    )
    for line in lines:
        for department in department_names:
            if department.lower() in line.lower():
                return department
    return "Not publicly available"


def _extract_research_section(soup: BeautifulSoup | Tag) -> str:
    # Samueli's current template uses <details>/<summary>, not section headings.
    for section in soup.find_all("details"):
        summary = section.find("summary", recursive=False)
        if not summary:
            continue
        label = _clean(summary.get_text(" ", strip=True)).lower()
        if not any(phrase in label for phrase in RESEARCH_HEADING_PHRASES):
            continue
        items = []
        for item in section.find_all(["li", "p"]):
            if item.find_parent("details") is not section:
                continue
            text = _clean(item.get_text(" ", strip=True))
            if 3 <= len(text) <= 700 and text not in items:
                items.append(text)
        if items:
            return "; ".join(items[:8])
        content = section.find(class_="seas-profile-content")
        if content and content.find_parent("details") is section:
            fragment = BeautifulSoup(str(content), "html.parser")
            for nested in fragment.find_all("details"):
                nested.decompose()
            text = _clean(fragment.get_text(" ", strip=True))
            if 3 <= len(text) <= 700:
                return text
    for heading in soup.find_all(["h2", "h3", "h4"]):
        label = _clean(heading.get_text(" ", strip=True)).lower()
        if not any(phrase == label or phrase in label for phrase in RESEARCH_HEADING_PHRASES):
            continue
        items: list[str] = []
        for element in heading.next_elements:
            if soup not in element.parents:
                break
            if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3", "h4"}:
                break
            if isinstance(element, Tag) and element.name == "li":
                text = _clean(element.get_text(" ", strip=True))
                if 3 <= len(text) <= 500 and text not in items:
                    items.append(text)
            elif isinstance(element, Tag) and element.name == "p" and not items:
                text = _clean(element.get_text(" ", strip=True))
                if 20 <= len(text) <= 700 and text not in items:
                    items.append(text)
        if items:
            return "; ".join(items[:8])
    return "Not publicly available"


def _website_candidate(anchor: Tag, page_url: str) -> tuple[str, str] | None:
    """Return a cleaned (label, absolute URL) pair for a plausible academic website."""
    label = _clean(anchor.get_text(" ", strip=True))
    lowered = label.lower()
    href = str(anchor.get("href", "")).strip()
    if not href or lowered in BLOCKED_LINK_LABELS:
        return None
    if href.lower().startswith(("mailto:", "javascript:", "#", "tel:")):
        return None

    absolute = urljoin(page_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.path.lower().endswith((".pdf", ".doc", ".docx")):
        return None
    if absolute.rstrip("/") == page_url.rstrip("/"):
        return None

    host = parsed.netloc.lower()
    blocked_host_fragments = (
        "marktechpost.com",
        "amazon.science",
        "nbcnews.com",
        "news.yahoo.com",
        "forbes.com",
        "focustaiwan.tw",
        "newsroom.ucla.edu",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
    )
    if any(fragment in host for fragment in blocked_host_fragments):
        return None
    return label, absolute


def _links_after_heading(heading: Tag, container: BeautifulSoup | Tag):
    for element in heading.next_elements:
        if container not in element.parents:
            break
        if isinstance(element, Tag) and element is not heading and element.name in {"h2", "h3", "h4"}:
            break
        if isinstance(element, Tag) and element.name == "a" and element.get("href"):
            yield element


def _best_website(soup: BeautifulSoup | Tag, page_url: str) -> str:
    """Prefer a page's explicit Websites section and never treat news links as lab sites."""
    page_host = urlparse(page_url).netloc.lower()
    candidates: list[tuple[int, int, str]] = []

    # The current Samueli template labels personal links with the person's
    # name rather than "Website"; the dedicated container supplies context.
    for position, anchor in enumerate(soup.select(".seas-profile-links a[itemprop='url']")):
        candidate = _website_candidate(anchor, page_url)
        if candidate:
            candidates.append((220, -position, candidate[1]))

    # UCLA Samueli profiles publish personal/lab links under a dedicated Websites heading.
    # The anchor can be icon-only in the raw HTML, so section position is more reliable
    # than anchor text.
    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = _clean(heading.get_text(" ", strip=True)).lower()
        if heading_text not in {"website", "websites", "personal website", "personal websites"}:
            continue
        for position, anchor in enumerate(_links_after_heading(heading, soup)):
            candidate = _website_candidate(anchor, page_url)
            if candidate:
                _label, absolute = candidate
                candidates.append((200, -position, absolute))

    # Conservative fallback for profiles with no dedicated Websites heading. Only
    # explicit website/homepage/lab labels qualify; generic research/news links do not.
    for position, anchor in enumerate(soup.find_all("a", href=True)):
        candidate = _website_candidate(anchor, page_url)
        if not candidate:
            continue
        label, absolute = candidate
        lowered = label.lower()
        parsed = urlparse(absolute)
        score = 0
        if "lab website" in lowered or lowered == "lab" or "laboratory" in lowered:
            score = 140
        elif "personal" in lowered or "homepage" in lowered or "home page" in lowered:
            score = 135
        elif "website" in lowered or "web page" in lowered:
            score = 130
        if score:
            if parsed.netloc.lower() != page_host:
                score += 3
            candidates.append((score, -position, absolute))

    if not candidates:
        return "Not publicly available"
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return candidates[0][2]


def parse_ucla_profile_html(html_text: str, page_url: str, name: str) -> UCLAProfileDetails:
    soup = BeautifulSoup(html_text, "html.parser")
    if not _normalize_person_name(name):
        return UCLAProfileDetails(department="Not publicly available")
    headings = [h for h in soup.find_all("h1")
                if _profile_name_matches(h.get_text(" ", strip=True), name, page_url)]
    if len(headings) != 1:
        # A wrong person's page or ambiguous template must not supply fields.
        return UCLAProfileDetails(department="Not publicly available")
    heading = headings[0]
    content = (heading.find_parent(class_="seas-profile")
               or heading.find_parent("article") or heading.find_parent("main") or soup)
    for noise in content.select("nav, footer, script, style, noscript, [role='navigation']"):
        noise.decompose()
    lines = _lines_after_h1(content, heading.get_text(" ", strip=True))
    identity = heading.find_parent(class_="seas-profile-identity")
    # Modern template puts the department before the person's H1. Read the
    # explicit appointment fields, not biography/navigation occurrences.
    title_lines = lines
    department_lines = lines
    if identity:
        title_lines = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-title")]
        department_lines = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-chip--dept")]
    all_text = _clean(content.get_text(" ", strip=True))
    emails = EMAIL_RE.findall(all_text)
    return UCLAProfileDetails(
        title=_extract_title(title_lines),
        department=("; ".join(dict.fromkeys(_clean(line) for line in department_lines if _clean(line)))
                    if identity and department_lines else _extract_department(department_lines)),
        email=_choose_email(emails, name),
        research_interests=_extract_research_section(content),
        website_url=_best_website(content, page_url),
    )


def parse_generic_academic_page(html_text: str, page_url: str, name: str) -> UCLAProfileDetails:
    """Conservative fallback for UCLA people whose directory link is a personal site."""
    soup = BeautifulSoup(html_text, "html.parser")
    text = _clean(soup.get_text(" ", strip=True))
    details = UCLAProfileDetails(
        email=_choose_email(EMAIL_RE.findall(text), name),
        website_url=page_url,
    )

    title_match = re.search(
        r"\b((?:assistant|associate|distinguished|adjunct|full)?\s*professor(?:\s+of\s+[A-Za-z &-]+)?|"
        r"research scientist|lecturer|postdoctoral researcher)\b",
        text,
        flags=re.IGNORECASE,
    )
    if title_match:
        details.title = _clean(title_match.group(1)).title()

    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if not meta:
        meta = soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
    if meta and meta.get("content"):
        candidate = _clean(str(meta.get("content")))
        if 25 <= len(candidate) <= 700:
            details.research_interests = candidate

    if details.research_interests == "Not publicly available":
        for tag in soup.find_all(["p", "div", "li"]):
            candidate = _clean(tag.get_text(" ", strip=True))
            lowered = candidate.lower()
            if 30 <= len(candidate) <= 700 and any(
                phrase in lowered
                for phrase in ("research interests", "my research", "research focuses", "works on", "working on")
            ):
                details.research_interests = candidate
                break
    return details


def _merge_interests(profile_interests: str, entry: UCLAResearchEntry) -> str:
    pieces: list[str] = []
    if profile_interests != "Not publicly available":
        pieces.append(profile_interests)
    if entry.areas:
        pieces.append("UCLA CS research areas: " + ", ".join(entry.areas))
    if not pieces and entry.area_descriptions:
        pieces.extend(entry.area_descriptions[:1])
    return "; ".join(pieces) if pieces else "Not publicly available"


class UCLAScraper(BaseUniversityScraper):
    university_name = "University of California, Los Angeles"
    directory_url = UCLA_RESEARCH_AREAS_URL

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
        directory_soup = self.get_soup(self.directory_url)
        entries = parse_ucla_research_areas_html(str(directory_soup), self.directory_url)
        if self.max_profiles is not None:
            entries = entries[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking UCLA profile {index} of {total}: {entry.name}")

            details = UCLAProfileDetails()
            page_to_check = (
                entry.profile_url
                if entry.profile_url != self.directory_url
                else entry.website_url
            )
            if page_to_check != "Not publicly available":
                try:
                    profile_soup = self.get_soup(page_to_check)
                    if "samueli.ucla.edu/people/" in page_to_check.lower():
                        details = parse_ucla_profile_html(str(profile_soup), page_to_check, entry.name)
                    else:
                        details = parse_generic_academic_page(str(profile_soup), page_to_check, entry.name)
                except requests.RequestException as exc:
                    LOGGER.warning("Could not inspect UCLA profile for %s: %s", entry.name, exc)

            if not details.email and entry.website_url != "Not publicly available" and entry.website_url != page_to_check:
                try:
                    website_soup = self.get_soup(entry.website_url)
                    fallback = parse_generic_academic_page(str(website_soup), entry.website_url, entry.name)
                    if fallback.email:
                        details.email = fallback.email
                    if details.title == "Not publicly available":
                        details.title = fallback.title
                    if details.research_interests == "Not publicly available":
                        details.research_interests = fallback.research_interests
                except requests.RequestException as exc:
                    LOGGER.warning("Could not inspect UCLA website for %s: %s", entry.name, exc)

            if not details.email:
                continue

            website_url = details.website_url
            if website_url == "Not publicly available":
                website_url = entry.website_url

            records.append(
                ScrapedProfessor(
                    name=entry.name,
                    university=self.university_name,
                    department=details.department,
                    title=details.title,
                    research_interests=_merge_interests(details.research_interests, entry),
                    email=details.email,
                    website_url=website_url,
                    profile_url=entry.profile_url,
                    source_type="Official UCLA CS research areas and UCLA academic profile",
                )
            )
        return records

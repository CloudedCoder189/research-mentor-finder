from __future__ import annotations

import html
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from services.opportunity import assess_outreach_potential

LOGGER = logging.getLogger(__name__)
NOT_AVAILABLE = "Not publicly available"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")

TITLE_PATTERN = re.compile(
    r"\b(?:Distinguished Professor|Chancellor(?:’|')s Professor|University Professor|"
    r"Professor and Chair|Department Chair|Teaching Professor|Research Professor|"
    r"Assistant Teaching Professor|Associate Teaching Professor|Assistant Professor|"
    r"Associate Professor|Professor Emeritus|Professor|Senior Lecturer|Lecturer|"
    r"Research Scientist|Staff Scientist|Principal Scientist|Postdoctoral Researcher|"
    r"Postdoctoral Scholar|Instructor|Director|Chair)\b[^\n|;]{0,180}",
    re.IGNORECASE,
)

PERSON_BLOCKLIST = {
    "faculty", "staff", "faculty and staff", "directory", "contact us", "research",
    "people", "home", "read more", "view profile", "personal website", "lab website",
}

LINK_BLOCKLIST = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "scholar.google.com", "researchgate.net",
    "drive.google.com", "docs.google.com", "accounts.google.com",
    "dropbox.com", "box.com", "onedrive.live.com",
}

WEBSITE_LABEL_SCORES = (
    ("personal website", 120), ("personal homepage", 120), ("academic website", 115),
    ("faculty website", 112), ("home page", 110), ("homepage", 110),
    ("lab website", 108), ("research group", 105), ("research lab", 105),
    ("laboratory", 102), ("research website", 100), ("personal site", 98),
    ("website", 80), ("research center", 65),
)

GENERIC_WEBSITE_PATH_FRAGMENTS = (
    "/research/research-areas-labs",
    "/research/areas/centers",
    "/research/research-centers",
)

RESEARCH_LABELS = (
    "research interests", "research areas", "areas of interest", "research focus",
    "research expertise", "expertise", "interests",
)


@dataclass(frozen=True)
class FacultyDirectoryConfig:
    university_name: str
    directory_url: str
    department: str
    source_type: str
    expected_email_domains: tuple[str, ...]
    city: str
    state: str = "California"
    profile_path_hints: tuple[str, ...] = ()
    directory_name_selectors: tuple[str, ...] = ("h2", "h3", "h4", ".name", ".person-name")
    include_lecturers: bool = True
    follow_profiles: bool = True
    allow_directory_profile_fallback: bool = False


@dataclass(slots=True)
class FacultyCandidate:
    name: str
    title: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    email: str = ""
    profile_url: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE
    source_text: str = ""


def _clean(value: object) -> str:
    text = str(value or "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return " ".join(text.split()).strip()


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.casefold())


def _clean_name(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^(?:Dr\.?|Professor|Prof\.?)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r",?\s+(?:Ph\.?D\.?|M\.?S\.?|B\.?S\.?|M\.?B\.?A\.?)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:image|photo|thumbnail)$", "", text, flags=re.IGNORECASE)
    return text.strip(" |–—-,:;")


def _looks_like_name(value: str) -> bool:
    name = _clean_name(value)
    lowered = name.casefold()
    words = name.split()
    if lowered in PERSON_BLOCKLIST or not 2 <= len(words) <= 8 or len(name) > 100:
        return False
    if any(char.isdigit() for char in name) or "@" in name or PHONE_RE.search(name):
        return False
    if any(term in lowered for term in ("university", "department", "faculty directory", "research areas")):
        return False
    return sum(char.isalpha() for char in name) >= 5


_RANK_WORD_RE = re.compile(
    r"\b(?:professor|lecturer|instructor|scientist|researcher|emeritus|chair|"
    r"director|dean|president|faculty|postdoctoral|scholar|affiliate|adjunct|"
    r"assistant|associate|visiting|clinical|teaching|distinguished|head|"
    r"coordinator|specialist|administrator|engineer)\b",
    re.IGNORECASE,
)


def _extract_title(text: str) -> str:
    match = TITLE_PATTERN.search(_clean(text))
    if not match:
        return NOT_AVAILABLE
    title = _clean(match.group(0)).strip(" |–—-,:;")
    # Avoid swallowing contact or website fields from flattened directory cards.
    email_match = EMAIL_RE.search(title)
    if email_match:
        title = title[: email_match.start()]
    phone_match = PHONE_RE.search(title)
    if phone_match:
        title = title[: phone_match.start()]
    title = re.split(
        r"\s+(?:Email|Office|Phone|Website|Lab Website|Personal Website|Research Interests|Research Areas)\b",
        title,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    # Profile pages render tab labels and breadcrumbs next to the title, and a
    # flattened card can absorb them. Cut at the first one that is not a rank.
    head = title
    for pattern in (
        r"\s+Profile\s+Publications\s+Teaching\b",
        r"\s+Publications\s+Teaching\b",
        r"\s+Teaching\s+Overview\b",
        r"\s+Overview\b",
        r"\s+Affiliation\b",
        r"\s+Faculty\s+Type\b",
        r"\s+Web\s+Site\b",
        r"\s+Home\s+Page\b",
        r"\s+Pronouns\s*:",
    ):
        match = re.search(pattern, head, flags=re.IGNORECASE)
        if match and _RANK_WORD_RE.search(head[: match.start()]):
            head = head[: match.start()]
    return head.strip(" |–—-,:;") or NOT_AVAILABLE


def _extract_labeled_research(text: str) -> str:
    flattened = _clean(text)
    for label in RESEARCH_LABELS:
        match = re.search(
            rf"\b{re.escape(label)}\s*[:\-]?\s*(.+?)(?=\s+(?:Email|Phone|Office|Website|Personal Website|Lab Website|Education|Biography|Bio)\b|$)",
            flattened,
            flags=re.IGNORECASE,
        )
        if match:
            value = _clean(match.group(1)).strip(" |–—-,:;")
            if value and len(value) <= 1200:
                return sanitize_research_text(value)
    return NOT_AVAILABLE


def _concise_bio_research(text: str, max_chars: int = 720) -> str:
    clean = _clean(text)
    if clean == "" or len(clean) < 25:
        return NOT_AVAILABLE
    # Prefer sentences that describe research, then cap the text to prevent full-page imports.
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    selected = [
        sentence for sentence in sentences
        if re.search(r"\b(research|research concerns|research interests lie|work focuses|works on|interests include|develops|studies|investigates|specializes)\b", sentence, re.IGNORECASE)
    ][:4]
    value = " ".join(selected) if selected else clean
    if len(value) > max_chars:
        value = value[:max_chars].rsplit(" ", 1)[0]
    return sanitize_research_text(value.strip(" ,;:"), max_chars=max_chars)




def sanitize_research_text(value: str, *, max_chars: int = 1200) -> str:
    """Remove contact/office spillover from research descriptions.

    Faculty cards sometimes flatten email, phone, office, and website fields into
    the same text node as research interests.  Keep the academic description,
    but never place contact information into semantic-search text.
    """
    text = _clean(value)
    if not text or text == NOT_AVAILABLE:
        return NOT_AVAILABLE
    text = EMAIL_RE.sub(" ", text)
    text = PHONE_RE.sub(" ", text)
    text = re.split(
        r"\s+(?:Campus\s+Email|Email|E-mail|Phone|Telephone|Office|Contact|Website|Personal Website|Lab Website)\s*[:\-]?\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.sub(r"\s+", " ", text).strip(" |–—-,:;")
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].strip(" |–—-,:;")
    return text if len(text) >= 3 else NOT_AVAILABLE


def _decode_cloudflare_email(encoded_value: str) -> str:
    """Decode one explicit Cloudflare ``data-cfemail`` value.

    Cloudflare Email Address Obfuscation replaces an address that is visible to
    human visitors with a hexadecimal XOR payload in the public HTML.  This
    helper decodes only that explicit payload; it never guesses an address from
    a professor's name.
    """
    encoded = re.sub(r"[^0-9a-f]", "", str(encoded_value or "").casefold())
    if len(encoded) < 4 or len(encoded) % 2:
        return ""
    try:
        key = int(encoded[:2], 16)
        decoded = "".join(
            chr(int(encoded[index:index + 2], 16) ^ key)
            for index in range(2, len(encoded), 2)
        )
    except (ValueError, OverflowError):
        return ""
    decoded = decoded.strip(".,;:()[]{}<>\"'").casefold()
    return decoded if EMAIL_RE.fullmatch(decoded) else ""


def _cloudflare_email_candidates(soup: BeautifulSoup) -> set[str]:
    """Extract addresses explicitly published through Cloudflare protection."""
    values: set[str] = set()
    for tag in soup.select("[data-cfemail]"):
        decoded = _decode_cloudflare_email(str(tag.get("data-cfemail", "")))
        if decoded:
            values.add(decoded)
    for anchor in soup.find_all("a", href=True):
        match = re.search(
            r"/cdn-cgi/l/email-protection#([0-9a-f]+)",
            str(anchor.get("href", "")),
            flags=re.IGNORECASE,
        )
        if match:
            decoded = _decode_cloudflare_email(match.group(1))
            if decoded:
                values.add(decoded)
    return values


def _email_candidates(soup: BeautifulSoup) -> set[str]:
    values: set[str] = set()
    for anchor in soup.select('a[href^="mailto:"]'):
        values.update(EMAIL_RE.findall(str(anchor.get("href", ""))))
    values.update(EMAIL_RE.findall(soup.get_text(" ", strip=True)))
    values.update(_cloudflare_email_candidates(soup))
    return {email.casefold().strip(".,;:()[]{}<>\"'") for email in values}


def _obfuscated_email_candidates(value: str) -> set[str]:
    """Extract common public ``name at school dot edu`` email spellings.

    This deliberately handles only explicit email-like text. It does not infer or
    guess an address from a professor's name.
    """
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s*(?:\[|\(|\{)\s*at\s*(?:\]|\)|\})\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+at\s+", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*(?:\[|\(|\{)\s*dot\s*(?:\]|\)|\})\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+dot\s+", ".", text, flags=re.IGNORECASE)
    return {
        candidate.casefold().strip(".,;:()[]{}<>\"'")
        for candidate in EMAIL_RE.findall(text)
    }


def _strict_person_email(
    emails: Iterable[str],
    name: str,
    domains: tuple[str, ...],
) -> str:
    """Choose a public address only when its local part resembles the person.

    Department, assistant, and generic university addresses are rejected even if
    they share the expected academic domain.
    """
    parts = [
        part for part in re.findall(
            r"[a-z]+", unicodedata.normalize("NFKD", name).casefold()
        )
        if len(part) > 1
    ]
    if not parts:
        return ""
    first, last = parts[0], parts[-1]
    middle_initials = "".join(part[0] for part in parts[1:-1])
    candidates: list[tuple[int, str]] = []
    for email_value in emails:
        email_value = str(email_value).casefold().strip(".,;:()[]{}<>\"'")
        if "@" not in email_value:
            continue
        local, domain = email_value.split("@", 1)
        if not any(domain == expected or domain.endswith(f".{expected}") for expected in domains):
            continue
        if any(word in local for word in (
            "admin", "assistant", "office", "support", "contact", "info", "webmaster", "department"
        )):
            continue
        compact = re.sub(r"[^a-z0-9]", "", local)
        score = 0
        if last and last in compact:
            score += 8
        if first and first in compact:
            score += 5
        if first and last and compact.startswith(first[0]) and last[:4] in compact:
            score += 5
        if first and last and compact == f"{first}{last}":
            score += 4
        if middle_initials and middle_initials in compact:
            score += 1
        if score >= 5:
            candidates.append((score, email_value))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1]


def _choose_email(emails: Iterable[str], name: str, domains: tuple[str, ...]) -> str:
    name_parts = re.findall(r"[a-z]+", unicodedata.normalize("NFKD", name).casefold())
    first = name_parts[0] if name_parts else ""
    last = name_parts[-1] if name_parts else ""
    best = ""
    best_score = -100
    for email in emails:
        if "@" not in email:
            continue
        local, domain = email.casefold().split("@", 1)
        compact = re.sub(r"[^a-z0-9]", "", local)
        score = 0
        if any(domain == expected or domain.endswith(f".{expected}") for expected in domains):
            score += 8
        elif domain.endswith(".edu"):
            score += 2
        if last and last in compact:
            score += 6
        if first and first in compact:
            score += 3
        if first and last and compact.startswith(first[0]) and last in compact:
            score += 2
        if any(word in local for word in ("admin", "info", "office", "support", "contact", "webmaster", "department")):
            score -= 15
        if score > best_score and score >= 5:
            best = email
            best_score = score
    return best


def _profile_link_from_block(block: Tag, base_url: str, name: str, hints: tuple[str, ...]) -> str:
    name_key = _normalize(name)
    candidates: list[tuple[int, str]] = []
    for anchor in block.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if href.lower().startswith(("mailto:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        label = _clean(anchor.get_text(" ", strip=True))
        label_key = _normalize(label)
        score = 0
        if name_key and (name_key in label_key or label_key in name_key) and len(label_key) >= 5:
            score += 12
        if any(hint.casefold() in absolute.casefold() for hint in hints):
            score += 7
        if any(word in label.casefold() for word in ("profile", "bio", "view")):
            score += 3
        if parsed.path.lower().endswith((".pdf", ".doc", ".docx", ".jpg", ".png")):
            score -= 20
        if score > 0:
            candidates.append((score, absolute))
    if not candidates:
        return NOT_AVAILABLE
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1]


def _website_from_soup(soup: BeautifulSoup, page_url: str, name: str) -> str:
    page_host = urlparse(page_url).netloc.casefold()
    name_parts = [part for part in re.findall(r"[a-z]+", name.casefold()) if len(part) > 1]
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True)).casefold()
        href = str(anchor.get("href", "")).strip()
        if href.casefold().startswith(("mailto:", "javascript:", "#")):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        host = parsed.netloc.casefold()
        if parsed.scheme not in {"http", "https"} or absolute.rstrip("/") == page_url.rstrip("/"):
            continue
        if any(host == blocked or host.endswith(f".{blocked}") for blocked in LINK_BLOCKLIST):
            continue
        if parsed.path.casefold().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx", ".jpg", ".png")):
            continue
        path = parsed.path.casefold().rstrip("/")
        if any(fragment in path for fragment in GENERIC_WEBSITE_PATH_FRAGMENTS):
            continue
        score = 0
        for phrase, weight in WEBSITE_LABEL_SCORES:
            if phrase in label:
                score = max(score, weight)
        # Faculty pages often label a real personal research site by its proper
        # lab name (for example, "Human-AI Experience Lab") instead of the
        # generic phrase "Lab Website".
        if score == 0 and re.search(r"\blab\b", label):
            score = 100
        if score == 0:
            continue
        if host != page_host:
            score += 4
        compact_url = _normalize(absolute)
        if any(part in compact_url for part in name_parts):
            score += 4
        candidates.append((score, absolute))
    if not candidates:
        return NOT_AVAILABLE
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    return candidates[0][1]


def _container_for(element: Tag) -> Tag:
    for parent_name in ("tr", "article", "li", "section", "div"):
        parent = element.find_parent(parent_name)
        if parent is not None and len(_clean(parent.get_text(" ", strip=True))) <= 3500:
            return parent
    return element


def _table_candidates(soup: BeautifulSoup, config: FacultyDirectoryConfig) -> list[FacultyCandidate]:
    results: list[FacultyCandidate] = []
    for table in soup.find_all("table"):
        headers = [_clean(cell.get_text(" ", strip=True)).casefold() for cell in table.find_all("th")]
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 2:
                continue
            texts = [_clean(cell.get_text(" ", strip=True)) for cell in cells]
            email = _choose_email(EMAIL_RE.findall(" ".join(texts)), texts[0], config.expected_email_domains)
            name = _clean_name(texts[0])
            if not _looks_like_name(name):
                continue
            title = NOT_AVAILABLE
            research = NOT_AVAILABLE
            if headers and len(headers) >= len(texts):
                for header, value in zip(headers, texts):
                    if "title" in header or "position" in header:
                        title = _extract_title(value)
                    if "research" in header or "interest" in header or "expertise" in header:
                        research = value or NOT_AVAILABLE
            if title == NOT_AVAILABLE:
                title = _extract_title(" ".join(texts[1:]))
            if research == NOT_AVAILABLE:
                research = _extract_labeled_research(" ".join(texts[1:]))
                if research == NOT_AVAILABLE and len(texts) >= 5:
                    last = texts[-1]
                    if 10 < len(last) < 1200 and not EMAIL_RE.search(last) and not PHONE_RE.search(last):
                        research = last
            profile_url = _profile_link_from_block(row, config.directory_url, name, config.profile_path_hints)
            website_url = _website_from_soup(BeautifulSoup(str(row), "html.parser"), config.directory_url, name)
            results.append(FacultyCandidate(name, title, research, email, profile_url, website_url, " ".join(texts)))
    return results


def parse_configurable_directory_html(html_text: str, config: FacultyDirectoryConfig) -> list[FacultyCandidate]:
    soup = BeautifulSoup(html_text, "html.parser")
    candidates = _table_candidates(soup, config)

    # Heading/card directories and directories where email appears inside a profile card.
    elements: list[Tag] = []
    for selector in config.directory_name_selectors:
        elements.extend(soup.select(selector))
    elements.extend(soup.select('a[href^="mailto:"]'))

    for element in elements:
        block = _container_for(element)
        block_text = _clean(block.get_text(" ", strip=True))
        if not block_text or len(block_text) > 3500:
            continue

        possible_names: list[str] = []
        if element.name in {"h1", "h2", "h3", "h4", "h5"} or "name" in " ".join(element.get("class", [])):
            possible_names.append(_clean_name(element.get_text(" ", strip=True)))
        for heading in block.find_all(["h2", "h3", "h4", "h5"], limit=3):
            possible_names.append(_clean_name(heading.get_text(" ", strip=True)))
        for anchor in block.find_all("a", href=True, limit=8):
            possible_names.append(_clean_name(anchor.get_text(" ", strip=True)))

        name = next((value for value in possible_names if _looks_like_name(value)), "")
        if not name:
            continue
        title = _extract_title(block_text)
        if not config.include_lecturers and "lecturer" in title.casefold():
            continue
        email = _choose_email(_email_candidates(BeautifulSoup(str(block), "html.parser")), name, config.expected_email_domains)
        profile_url = _profile_link_from_block(block, config.directory_url, name, config.profile_path_hints)
        research = _extract_labeled_research(block_text)
        website = _website_from_soup(BeautifulSoup(str(block), "html.parser"), config.directory_url, name)
        candidates.append(FacultyCandidate(name, title, research, email, profile_url, website, block_text))

    deduped: dict[str, FacultyCandidate] = {}
    for candidate in candidates:
        key = _normalize(candidate.name)
        if not key:
            continue
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = candidate
            continue
        # Merge richer data from duplicate nested containers.
        for attr in ("title", "research_interests", "email", "profile_url", "website_url"):
            current = getattr(existing, attr)
            incoming = getattr(candidate, attr)
            if current in {"", NOT_AVAILABLE} and incoming not in {"", NOT_AVAILABLE}:
                setattr(existing, attr, incoming)
        if len(candidate.source_text) > len(existing.source_text):
            existing.source_text = candidate.source_text
    return list(deduped.values())


def _profile_title(soup: BeautifulSoup, name: str) -> str:
    name_heading = None
    name_key = _normalize(name)
    for heading in soup.find_all(["h1", "h2", "h3"]):
        heading_key = _normalize(_clean(heading.get_text(" ", strip=True)))
        if name_key and (name_key in heading_key or heading_key in name_key):
            name_heading = heading
            break
    if name_heading is not None:
        nearby: list[str] = []
        for element in name_heading.next_elements:
            if isinstance(element, Tag) and element is not name_heading and element.name in {"h1", "h2"}:
                break
            if isinstance(element, Tag):
                value = _clean(element.get_text(" ", strip=True))
                if value and value not in nearby:
                    nearby.append(value)
            if sum(len(value) for value in nearby) > 900:
                break
        title = _extract_title(" ".join(nearby))
        if title != NOT_AVAILABLE:
            return title
    return _extract_title(_clean(soup.get_text(" ", strip=True))[:2500])


def _profile_research(soup: BeautifulSoup) -> str:
    full_text = _clean(soup.get_text(" ", strip=True))
    labeled = _extract_labeled_research(full_text)
    if labeled != NOT_AVAILABLE:
        return labeled

    paragraphs: list[str] = []
    for paragraph in soup.select("main p, article p, .profile p, .person p, .bio p"):
        text = _clean(paragraph.get_text(" ", strip=True))
        if not 30 <= len(text) <= 1200:
            continue
        if re.search(
            r"\b(research|research concerns|research interests lie|work focuses|works on|interests include|develops|studies|investigates|specializes|focuses on)\b",
            text, re.IGNORECASE,
        ):
            paragraphs.append(text)
        if len(paragraphs) >= 4:
            break
    if paragraphs:
        return _concise_bio_research(" ".join(paragraphs))

    for heading in soup.find_all(["h2", "h3", "h4"]):
        label = _clean(heading.get_text(" ", strip=True)).casefold()
        if not any(term in label for term in ("research", "bio", "about")):
            continue
        section: list[str] = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h2", "h3", "h4"}:
                break
            if isinstance(sibling, Tag):
                value = _clean(sibling.get_text(" ", strip=True))
            else:
                value = _clean(sibling)
            if value:
                section.append(value)
            if sum(len(part) for part in section) > 900:
                break
        value = _concise_bio_research(" ".join(section))
        if value != NOT_AVAILABLE:
            return value
    return _concise_bio_research(full_text[:5000])


def enrich_candidate_from_profile(
    candidate: FacultyCandidate,
    html_text: str,
    profile_url: str,
    config: FacultyDirectoryConfig,
) -> FacultyCandidate:
    soup = BeautifulSoup(html_text, "html.parser")
    full_text = _clean(soup.get_text(" ", strip=True))
    email = candidate.email or _choose_email(_email_candidates(soup), candidate.name, config.expected_email_domains)
    profile_title = _profile_title(soup, candidate.name)
    title = profile_title if profile_title != NOT_AVAILABLE else candidate.title
    research = candidate.research_interests
    if research == NOT_AVAILABLE:
        research = _profile_research(soup)
    research = sanitize_research_text(research)
    website = candidate.website_url
    if website == NOT_AVAILABLE:
        website = _website_from_soup(soup, profile_url, candidate.name)
    return FacultyCandidate(
        name=candidate.name,
        title=title,
        research_interests=research,
        email=email,
        profile_url=profile_url,
        website_url=website,
        source_text=full_text[:6000],
    )


class ConfigurableFacultyScraper(BaseUniversityScraper):
    config: FacultyDirectoryConfig

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        config = getattr(cls, "config", None)
        if config is not None:
            cls.university_name = config.university_name
            cls.directory_url = config.directory_url

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
        candidates = parse_configurable_directory_html(str(directory_soup), self.config)
        candidates.sort(key=lambda item: ("lecturer" in item.title.casefold(), item.name.casefold()))
        if self.max_profiles is not None:
            candidates = candidates[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            if self.progress_callback:
                self.progress_callback(f"Checking profile {index} of {total}: {candidate.name}")
            enriched = candidate
            if self.config.follow_profiles and candidate.profile_url != NOT_AVAILABLE:
                try:
                    profile_soup = self.get_soup(candidate.profile_url)
                    enriched = enrich_candidate_from_profile(
                        candidate, str(profile_soup), candidate.profile_url, self.config
                    )
                except requests.RequestException as exc:
                    LOGGER.warning("Could not inspect %s profile for %s: %s", self.university_name, candidate.name, exc)

            if (
                not enriched.email
                and enriched.website_url != NOT_AVAILABLE
                and enriched.website_url != enriched.profile_url
            ):
                try:
                    website_soup = self.get_soup(enriched.website_url)
                    website_email = _choose_email(
                        _email_candidates(website_soup),
                        enriched.name,
                        self.config.expected_email_domains,
                    )
                    if website_email:
                        enriched.email = website_email
                except requests.RequestException as exc:
                    LOGGER.warning(
                        "Could not inspect linked academic site for %s at %s: %s",
                        enriched.name, enriched.website_url, exc
                    )
            if not enriched.email:
                continue
            if enriched.title == NOT_AVAILABLE and not self.config.include_lecturers:
                continue
            if (
                enriched.profile_url == NOT_AVAILABLE
                and self.config.allow_directory_profile_fallback
            ):
                enriched.profile_url = self.config.directory_url
            enriched.research_interests = sanitize_research_text(
                enriched.research_interests
            )
            base_record = {
                "title": enriched.title,
                "research_interests": enriched.research_interests,
                "website_url": enriched.website_url,
                "profile_url": enriched.profile_url,
            }
            assessment = assess_outreach_potential(
                base_record,
                source_text=enriched.source_text,
                source_url=(
                    enriched.website_url if enriched.website_url != NOT_AVAILABLE else enriched.profile_url
                ),
            )
            records.append(
                ScrapedProfessor(
                    name=enriched.name,
                    university=self.university_name,
                    department=self.config.department,
                    title=enriched.title,
                    research_interests=enriched.research_interests,
                    email=enriched.email,
                    website_url=enriched.website_url,
                    profile_url=enriched.profile_url,
                    opportunity_level=assessment.level,
                    opportunity_signals=assessment.signals,
                    opportunity_source_url=assessment.source_url,
                    source_type=self.config.source_type,
                )
            )
        return records

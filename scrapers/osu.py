"""Oregon State University College of Engineering faculty (Phase 3).

V9.7 Phase 3 expands beyond California with the official Oregon State
University College of Engineering rosters for Electrical Engineering and
Computer Science (``/EECS/About/People``) and Mechanical, Industrial, and
Manufacturing Engineering (``/MIME/About/People``).

Both directories are server-rendered Drupal pages whose person entries are
``div.coe-brand-people-card`` cards.  The card pairs a person's name
(``h2.coe-brand-people-card-name``) with that person's email link
(``a[href^=mailto:]``), a title (the first ``p.mb-4-5``) and an optional
``/about/people/<slug>`` profile anchor.

The roster paginates with a view ``block_config_key`` carried on the pager
links (``?block_config_key=...&page=N``) instead of a plain ``?page=N``
parameter, so the scraper reads that key from the first page and replays it on
every later page until a page returns no cards.

Each person's profile page additionally supplies research interests (the
``profile-research-interests`` block) and an optional research website
(``field--name-field-engr-research-website``), which improves the downstream
opportunity assessment.

The combined :class:`OregonStateUniversityScraper` runs both department
scrapers and collapses cross-listed people (someone listed under EECS and MIME
with the same email or name) through
:func:`services.deduplication.deduplicate`.  Like the Phase 2 broadening
wrappers it is deliberately not authoritative, so a refresh never prunes
existing Oregon records.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.configurable import NOT_AVAILABLE, _clean, sanitize_research_text
from services.deduplication import deduplicate

LOGGER = logging.getLogger(__name__)

OSU_BASE_URL = "https://engineering.oregonstate.edu"
OSU_EECS_URL = "https://engineering.oregonstate.edu/EECS/About/People"
OSU_MIME_URL = "https://engineering.oregonstate.edu/MIME/About/People"

OSU_UNIVERSITY_NAME = "Oregon State University"

CARDS_PER_PAGE = 39
MAX_OSU_PAGES = 30

PROFILE_HREF_RE = re.compile(r"/about/people/", re.I)
MAILTO_RE = re.compile(r"^mailto:", re.I)
BLOCK_CONFIG_KEY_RE = re.compile(r"block_config_key=([^&\"'\s]+)")


@dataclass(slots=True)
class OSUCard:
    name: str
    title: str
    email: str
    profile_url: str


@dataclass(slots=True)
class OSUProfileDetails:
    research_interests: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE


def _osu_card_title(card) -> str:
    """Compose the card title, including any "Additional Positions" tie-ins.

    The first ``p.mb-4-5`` holds the primary title (sometimes already several
    titles joined by `` | ``).  A later ``p.mb-4-5`` can carry an
    "Additional Positions ..." label whose value (for example "CoRIS Associate
    Director for Research") is appended as an extra title part.
    """
    title_paras = card.select("p.mb-4-5")
    parts: list[str] = []
    if title_paras:
        parts.append(_clean(title_paras[0].get_text(" ", strip=True)))
    for para in title_paras[1:]:
        text = _clean(para.get_text(" ", strip=True))
        if text.startswith("Additional Positions"):
            value = _clean(text[len("Additional Positions"):].lstrip(":|"))
            if value:
                parts.append(value)
    return " | ".join(part for part in parts if part)


def parse_osu_directory_page(
    html_text: str,
    base_url: str,
) -> list[OSUCard]:
    """Extract person cards from one OSU College of Engineering directory page.

    The email is read from the ``mailto:`` anchor *inside the same card* as the
    name, which is the guarantee that person and email stay paired even when
    the card layout shifts within a page.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    cards: list[OSUCard] = []
    seen: set[tuple[str, str]] = set()
    for card_node in soup.select("div.coe-brand-people-card"):
        name_node = card_node.select_one("h2.coe-brand-people-card-name")
        name = _clean(name_node.get_text(" ", strip=True)) if name_node else ""
        email_node = card_node.find("a", href=MAILTO_RE)
        email = ""
        if email_node is not None:
            email = _clean(email_node.get("href", "")[len("mailto:"):])
        if not name or not email:
            continue
        profile_anchor = card_node.find("a", href=PROFILE_HREF_RE)
        profile_url = NOT_AVAILABLE
        if profile_anchor is not None:
            profile_url = urljoin(base_url, profile_anchor.get("href", ""))
        title = _osu_card_title(card_node)
        key = (name.casefold(), email.casefold())
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            OSUCard(
                name=name,
                title=title,
                email=email,
                profile_url=profile_url,
            )
        )
    return cards


def extract_osu_block_config_key(html_text: str) -> str | None:
    """Read the roster pagination key from a directory page's pager links."""
    match = BLOCK_CONFIG_KEY_RE.search(html_text)
    return match.group(1) if match else None


def parse_osu_profile_details(html_text: str, base_url: str) -> OSUProfileDetails:
    """Read research interests and a research website from an OSU profile page."""
    soup = BeautifulSoup(html_text, "html.parser")
    interests = NOT_AVAILABLE
    interests_node = soup.select_one("div.profile-research-interests")
    if interests_node is not None:
        text = _clean(interests_node.get_text(" ", strip=True))
        if text:
            interests = sanitize_research_text(text)
    website = NOT_AVAILABLE
    website_node = soup.select_one(
        "div.field--name-field-engr-research-website a[href]"
    )
    if website_node is not None:
        website = _clean(website_node.get("href", ""))
        if website and not website.casefold().startswith(("http://", "https://")):
            website = urljoin(base_url, website)
    return OSUProfileDetails(
        research_interests=interests,
        website_url=website if website else NOT_AVAILABLE,
    )


class OSUCollegeScraper(BaseUniversityScraper):
    """Base scraper for one Oregon State College of Engineering department."""

    university_name = OSU_UNIVERSITY_NAME
    department = "Not publicly available"
    # Explicitly non-authoritative: a successful refresh never prunes records.
    authoritative_roster = False

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
        self.pages_read = 0

    def _page_url(self, page: int, block_key: str | None) -> str:
        if page == 0:
            return self.directory_url
        if block_key:
            return f"{self.directory_url}?block_config_key={block_key}&page={page}"
        return f"{self.directory_url}?term_node_tid_depth=166&page={page}"

    def scrape(self) -> list[ScrapedProfessor]:
        page_zero = self.get_soup(self.directory_url)
        self.pages_read = 1
        block_key = extract_osu_block_config_key(str(page_zero))
        cards = parse_osu_directory_page(str(page_zero), self.directory_url)

        page = 1
        seen_cards: set[str] = {card.email.casefold() for card in cards}
        while True:
            if len(cards) == 0:
                break
            if len(cards) < CARDS_PER_PAGE or (block_key is None and page > 1):
                break
            if page >= MAX_OSU_PAGES:
                LOGGER.warning(
                    "OSU %s pagination stopped at page %s without exhausting the roster",
                    self.department,
                    page,
                )
                break
            try:
                soup = self.get_soup(self._page_url(page, block_key))
            except requests.RequestException as exc:
                LOGGER.warning("OSU %s page %s failed: %s", self.department, page, exc)
                break
            self.pages_read += 1
            page_cards = parse_osu_directory_page(str(soup), self.directory_url)
            fresh = [card for card in page_cards if card.email.casefold() not in seen_cards]
            if not fresh:
                break
            for card in fresh:
                seen_cards.add(card.email.casefold())
            cards.extend(fresh)
            page += 1

        cards.sort(key=lambda card: card.name.casefold())
        if self.max_profiles is not None:
            cards = cards[: self.max_profiles]

        records: list[ScrapedProfessor] = []
        total = len(cards)
        for index, card in enumerate(cards, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking Oregon State {self.department} profile "
                    f"{index} of {total}: {card.name}"
                )
            research = NOT_AVAILABLE
            website = NOT_AVAILABLE
            if card.profile_url != NOT_AVAILABLE:
                try:
                    profile_soup = self.get_soup(card.profile_url)
                    details = parse_osu_profile_details(
                        str(profile_soup), card.profile_url
                    )
                    research = details.research_interests
                    website = details.website_url
                except requests.RequestException as exc:
                    LOGGER.warning(
                        "Could not inspect OSU profile for %s: %s",
                        card.name,
                        exc,
                    )
            records.append(
                ScrapedProfessor(
                    name=card.name,
                    university=self.university_name,
                    department=self.department,
                    title=card.title,
                    research_interests=research,
                    email=card.email,
                    website_url=website,
                    profile_url=card.profile_url,
                    source_type=(
                        f"Official Oregon State {self.department} people directory "
                        "and profile pages"
                    ),
                )
            )
        return records


class OSUEECSScraper(OSUCollegeScraper):
    directory_url = OSU_EECS_URL
    department = "Electrical and Computer Engineering"


class OSUMIMEScraper(OSUCollegeScraper):
    directory_url = OSU_MIME_URL
    department = "Mechanical, Industrial, and Manufacturing Engineering"


class OregonStateUniversityScraper(BaseUniversityScraper):
    """Combined Oregon State University scraper (EECS + MIME)."""

    university_name = OSU_UNIVERSITY_NAME
    directory_url = OSU_EECS_URL
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.eecs = OSUEECSScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.mime = OSUMIMEScraper(
            request_delay=request_delay,
            timeout=timeout,
            max_profiles=max_profiles,
            progress_callback=progress_callback,
        )
        self.last_error = ""

    def scrape(self) -> list[ScrapedProfessor]:
        eecs_records = self.eecs.safe_scrape()
        mime_records = self.mime.safe_scrape()
        errors = [
            message
            for message in (self.eecs.last_error, self.mime.last_error)
            if str(message or "").strip()
        ]
        if errors:
            self.last_error = " ".join(errors)
        combined = eecs_records + mime_records
        unique = deduplicate([record.as_record() for record in combined])
        return [ScrapedProfessor(**row) for row in unique]
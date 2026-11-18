"""University of Washington faculty scrapers (V9.7 Phase 4).

Washington is the second state expansion.  Seven approved University of
Washington departments are added, always to the combined (non-authoritative)
:class:`UniversityOfWashingtonScraper`:

* Allen School of Computer Science & Engineering (``cs.washington.edu``) --
  the official faculty-members roster only; adjunct, emeritus, and affiliate
  listings live on separate pages and are intentionally not scraped.  The
  roster page links each person once per slug, and the Elementor profile page
  carries the authoritative name, title, ``Expertise:`` research areas, the
  ``Email:`` field, and optional faculty/research website.
* Electrical & Computer Engineering (``ece.uw.edu``) -- the ``faculty/``
  roster is fully self-contained: each ``stafftemplate--entry`` pairs the
  name, title, research interests, and the person's own email link inline.
* Statistics (``stat.washington.edu``) -- the ``people/faculty`` list links
  profile pages whose contact table publishes the email; the Statistics site
  uses a certificate chain the public client cannot validate, so those
  requests are made with certificate verification disabled *for this host
  only*.
* Chemistry, Physics, Economics, and Biology (Drupal people directories) --
  the list pages pair a person card (``views-field-title``/``directory-item``)
  with the official title and ``mailto:`` email; profile pages add a research
  biography and optional personal website.

Every department scraper is a deliberately *non-authoritative* roster: a
successful refresh never prunes existing records.  The combined wrapper runs
the departments in canonical order (CSE first) and collapses cross-listed
people through :func:`services.deduplication.deduplicate`, keeping the first
source's record.  Each department enforces a floor guard so a silently
degenerate parse (for example a roster that returns a handful of rows) is
surfaced on ``last_error`` instead of quietly shrinking the dataset.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.broadened import combine_broadened
from scrapers.configurable import (
    EMAIL_RE,
    NOT_AVAILABLE,
    PHONE_RE,
    _clean,
    _clean_name,
    _concise_bio_research,
    _website_from_soup,
    sanitize_research_text,
)

LOGGER = logging.getLogger(__name__)

UW_UNIVERSITY_NAME = "University of Washington"
UW_OFFICIAL_DOMAIN = "uw.edu"

CSE_DIRECTORY_URL = "https://www.cs.washington.edu/people/faculty-members/"
ECE_DIRECTORY_URL = "https://www.ece.uw.edu/faculty/"
STATS_DIRECTORY_URL = "https://stat.washington.edu/people/faculty"
CHEM_DIRECTORY_URL = "https://chem.washington.edu/people/faculty"
PHYS_DIRECTORY_URL = "https://phys.washington.edu/people/faculty"
ECON_DIRECTORY_URL = "https://econ.washington.edu/people/faculty"
BIO_DIRECTORY_URL = "https://biology.washington.edu/people/faculty"

# Floor guards: if a department parse returns fewer rows than its floor, the
# roster almost certainly changed layout and the scraper should not silently
# report a healthy refresh.
UW_DEPT_FLOORS: dict[str, int] = {
    "Computer Science and Engineering": 60,
    "Electrical and Computer Engineering": 25,
    "Statistics": 20,
    "Chemistry": 25,
    "Physics": 30,
    "Economics": 25,
    "Biology": 60,
}

MAILTO_RE = re.compile(r"^mailto:", re.I)
CSE_PROFILE_RE = re.compile(r"/people/faculty/([a-z0-9-]+)/", re.I)
# In-page slugs that are not individual people on the Statistics roster.
STATS_SKIP_SLUGS = {
    "faculty",
    "faculty-awards",
    "student-awards",
    "alumni",
    "students",
    "staff",
    "postdoctoral-researchers",
    "research",
    "people",
    "visiting",
    "visitors",
    "emeriti",
    "affiliates",
}

_SECTION_BOUNDARIES = (
    "Biography",
    "Education",
    "Awards",
    "Honors & Awards",
    "Preprints",
    "Publications",
    "Selected Publications",
    "Courses Taught",
    "Teaching",
    "Seminars",
    "Talks",
    "Contact Information",
    "Personal Website",
    "Office",
)

_HEADING_LABELS = (
    "Contact Information",
    "Education",
    "Fields of Interest",
    "Research - Fields of Interest",
    "Biography",
    "Awards",
    "Preprints",
    "Publications",
    "UW Box Number",
    "Office",
)


@dataclass(slots=True)
class UWPerson:
    """One University of Washington faculty roster entry."""

    name: str
    title: str = ""
    email: str = ""
    profile_url: str = NOT_AVAILABLE
    research_interests: str = NOT_AVAILABLE
    website_url: str = NOT_AVAILABLE
    slug: str = ""
    inline_research: str = ""


def _uw_domain_email(urls: list[str]) -> str:
    """Return the first email on an official UW domain, else the first address."""
    chosen = ""
    for value in urls:
        email = str(value or "").strip().casefold()
        if "@" not in email:
            continue
        domain = email.split("@", 1)[1]
        if domain == UW_OFFICIAL_DOMAIN or domain.endswith(f".{UW_OFFICIAL_DOMAIN}"):
            return email
        if not chosen:
            chosen = email
    return chosen


def _uw_profile_research(html_text: str) -> str:
    """Read research-oriented text from a University of Washington profile.

    Chemistry, Physics, Economics, and Biology profiles publish a "Fields of
    Interest" or "Biography" section inside the main ``article``.  Statistics
    profiles publish a ``Bio:`` paragraph inside the content region.  Whichever
    labeled section exists is capped and cleaned so contact data never leaks
    into the semantic-search text.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    root = soup.select_one("article") or soup.select_one("div.region-content") or soup
    full = _clean(root.get_text(" ", strip=True))

    stripped = EMAIL_RE.sub(" ", full)
    stripped = PHONE_RE.sub(" ", stripped)
    lowered = stripped.casefold()

    for label in ("fields of interest", "research interests", "research areas", "research expertise"):
        index = lowered.find(label)
        if index == -1:
            continue
        value = stripped[index + len(label):].strip(" :;,-")
        value = re.split(
            r"\s+(?:" + "|".join(re.escape(boundary) for boundary in _SECTION_BOUNDARIES) + r")\s*:?",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        cleaned = sanitize_research_text(value)
        if cleaned != NOT_AVAILABLE:
            return cleaned

    bio = _section_after(root, "Bio")
    if bio:
        for value in bio:
            cleaned = _concise_bio_research(value)
            if cleaned != NOT_AVAILABLE:
                return cleaned
    biography = _section_after(root, "Biography")
    if biography:
        for value in biography:
            cleaned = _concise_bio_research(value)
            if cleaned != NOT_AVAILABLE:
                return cleaned
    return NOT_AVAILABLE


def _section_after(root, label: str) -> list[str]:
    """Text of the section that follows a labeled heading (e.g. ``Bio``)."""
    node = None
    for element in root.find_all(["h2", "h3", "h4", "strong", "b"]):
        text = _clean(element.get_text(" ", strip=True))
        if text.casefold().strip(": ") != label.casefold():
            continue
        node = element
        break
    if node is None:
        return []
    parts: list[str] = []
    for sibling in node.next_siblings:
        if sibling.name in {"h2", "h3", "h4"}:
            break
        if hasattr(sibling, "get_text"):
            value = _clean(sibling.get_text(" ", strip=True))
        else:
            value = _clean(str(sibling))
        if value and value not in parts:
            parts.append(value)
        if sum(len(part) for part in parts) > 1400:
            break
    return parts


# ---------------- CSE (Allen School) ----------------


def extract_cse_slugs(html_text: str) -> list[str]:
    """Distinct faculty roster identifiers from the CSE faculty-members page.

    Each profile appears once per slug, so the parsed order is preserved and
    duplicates are collapsed before any network work.
    """
    slugs: list[str] = []
    for match in CSE_PROFILE_RE.finditer(html_text):
        slug = match.group(1)
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def parse_cse_profile(html_text: str, profile_url: str) -> UWPerson:
    """Read one Allen School Elementor profile page.

    The profile's visible fields are labeled with bold ``Field:`` runs
    (``Focus Area:``, ``Expertise:``, ``Email:``, ``Biography:``).  The person's
    name is the first ``h2`` after the page's ``h1`` and the title is the
    following ``h3``.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    name = ""
    for heading in soup.find_all(["h1", "h2"]):
        candidate = _clean_name(heading.get_text(" ", strip=True))
        if candidate and candidate != "Faculty" and _looks_person(candidate):
            name = candidate
            break
    title = NOT_AVAILABLE
    for heading in soup.find_all("h3"):
        candidate = _clean(heading.get_text(" ", strip=True))
        if candidate and candidate != "Popular Links":
            title = candidate
            break
    email = ""
    website = NOT_AVAILABLE
    research = NOT_AVAILABLE
    for block in soup.select(".elementor-widget-container"):
        text = _clean(block.get_text(" ", strip=True))
        email_match = re.search(r"^Email:?\s*(.+)$", text, re.IGNORECASE)
        if email_match and not email:
            email = email_match.group(1).strip().casefold()
        research_match = re.search(r"^Expertise:?\s*(.+)$", text, re.IGNORECASE)
        if research_match and research == NOT_AVAILABLE:
            research = sanitize_research_text(research_match.group(1))
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True)).casefold()
        if "webpage" in label or "website" in label:
            href = str(anchor.get("href", "")).strip()
            if href.casefold().startswith(("http://", "https://")):
                website = href
                break
    return UWPerson(
        name=name,
        title=title,
        email=email,
        profile_url=profile_url,
        research_interests=research if research != NOT_AVAILABLE else _uw_profile_research(html_text),
        website_url=website if website != NOT_AVAILABLE else _website_from_soup(soup, profile_url, name),
    )


def _looks_person(value: str) -> bool:
    lowered = value.casefold()
    if lowered in {"university of washington", "computer science & engineering", "allen school"}:
        return False
    return len(value.split()) >= 2 and not any(char.isdigit() for char in value)


# ---------------- Inline rosters (ECE, Chemistry, Physics, Economics, Biology) ----------------


def parse_ece_directory(html_text: str, base_url: str) -> list[UWPerson]:
    """Parse the self-contained ECE faculty roster cards.

    Every ``stafftemplate--entry`` pairs the ``stafftemplate--name``,
    ``stafftemplate--title``, ``stafftemplate--interests``, and the person's
    ``stafftemplate--email`` (:class:`UWPerson`) link so person and address
    are guaranteed to match.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    people: list[UWPerson] = []
    for entry in soup.select("div.stafftemplate--entry"):
        name_node = entry.select_one("span.stafftemplate--name")
        name = _clean_name(name_node.get_text(" ", strip=True)) if name_node else ""
        title_node = entry.select_one("span.stafftemplate--title")
        title = _clean(title_node.get_text(" ", strip=True)) if title_node else ""
        interests_node = entry.select_one("span.stafftemplate--interests")
        interests = (
            _clean(interests_node.get_text(" ", strip=True))
            if interests_node
            else ""
        )
        email_node = entry.select_one('a[href^="mailto:"]')
        email = ""
        if email_node is not None:
            email = _clean(email_node.get("href", "")[len("mailto:"):]).casefold()
        if not name or not email:
            continue
        people.append(
            UWPerson(
                name=name,
                title=title or NOT_AVAILABLE,
                email=email,
                profile_url=NOT_AVAILABLE,
                research_interests=sanitize_research_text(interests)
                if interests
                else NOT_AVAILABLE,
                inline_research=interests,
            )
        )
    return people


def parse_drupal_people_list(html_text: str, base_url: str) -> list[UWPerson]:
    """Parse the Chemistry/Physics/Economics people-directory rows.

    Each row pairs a ``views-field-title`` link with its
    ``views-field-field-job-title`` (title) and ``views-field-field-email``
    ``mailto:`` address.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    people: list[UWPerson] = []
    for title_node in soup.select("div.views-field.views-field-title"):
        row = title_node.find_parent("div", class_=lambda value: value and "views-row" in value)
        base = row if row is not None else title_node.parent
        anchor = title_node.select_one("a[href]")
        if anchor is None:
            continue
        name = _clean_name(anchor.get_text(" ", strip=True))
        if not name:
            continue
        title_value = NOT_AVAILABLE
        title_block = base.select_one(".views-field-field-job-title")
        if title_block is not None:
            title_value = _clean(title_block.get_text(" ", strip=True))
        email = ""
        email_anchor = base.select_one('a[href^="mailto:"]')
        if email_anchor is not None:
            email = _clean(email_anchor.get("href", "")[len("mailto:"):]).casefold()
        if not email:
            continue
        profile_url = NOT_AVAILABLE
        if anchor.get("href", "").casefold().startswith("/people/"):
            profile_url = f"{base_url}{anchor.get('href')}"
        people.append(
            UWPerson(
                name=name,
                title=title_value,
                email=email,
                profile_url=profile_url,
            )
        )
    return people


def parse_bio_directory(html_text: str, base_url: str) -> list[UWPerson]:
    """Parse the Biology ``directory-item`` cards."""
    soup = BeautifulSoup(html_text, "html.parser")
    people: list[UWPerson] = []
    for item in soup.select("div.directory-item"):
        anchor = item.select_one("a[href*='/people/']")
        if anchor is None:
            continue
        name = _clean_name(anchor.get_text(" ", strip=True))
        if not name:
            continue
        title_value = NOT_AVAILABLE
        title_block = item.select_one(".directory-item__title")
        if title_block is not None:
            title_value = _clean(title_block.get_text(" ", strip=True))
        email = ""
        email_anchor = item.select_one('a[href^="mailto:"]')
        if email_anchor is not None:
            email = _clean(email_anchor.get("href", "")[len("mailto:"):]).casefold()
        if not email:
            continue
        profile_url = NOT_AVAILABLE
        if anchor.get("href", "").casefold().startswith("/people/"):
            profile_url = f"{base_url}{anchor.get('href')}"
        people.append(
            UWPerson(
                name=name,
                title=title_value,
                email=email,
                profile_url=profile_url,
            )
        )
    return people


# ---------------- Statistics ----------------


def extract_stats_people(html_text: str, base_url: str) -> list[UWPerson]:
    """Person slugs and names from the Statistics faculty roster.

    The list renders each person twice (a headshot image and a text link);
    the empty-image anchors are ignored and the text anchor's label is kept.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    seen: dict[str, UWPerson] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        match = re.search(r"/people/([a-z0-9-]+)(?:/)?$", href.casefold())
        if not match:
            continue
        slug = match.group(1)
        if slug in STATS_SKIP_SLUGS:
            continue
        name = _clean_name(anchor.get_text(" ", strip=True))
        if name:
            seen[slug] = UWPerson(
                name=name,
                profile_url=f"{base_url}/people/{slug}",
                slug=slug,
            )
        elif slug not in seen:
            seen[slug] = UWPerson(name="", profile_url=f"{base_url}/people/{slug}", slug=slug)
    return list(seen.values())


def parse_stats_profile(html_text: str, person: UWPerson) -> UWPerson:
    """Fill title, email, research, and homepage from a Statistics profile.

    The ``region-content`` block carries the name (``h1``), the job title
    (first ``h3``), the contact table's ``mailto:`` address, a ``Homepage``
    link, and a ``Bio:`` paragraph.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    region = soup.select_one("div.region-content") or soup
    name = person.name
    if not name:
        for heading in region.find_all(["h1", "h2"]):
            candidate = _clean_name(heading.get_text(" ", strip=True))
            if candidate and _looks_person(candidate):
                name = candidate
                break
    title = person.title
    if not title:
        for heading in region.find_all("h3"):
            candidate = _clean(heading.get_text(" ", strip=True))
            if candidate and not candidate.casefold().startswith(("awards", "preprints", "publications")):
                title = candidate
                break
    email = person.email
    if not email:
        email = _uw_domain_email(
            [
                anchor.get("href", "")[len("mailto:"):]
                for anchor in region.find_all("a", href=True)
                if str(anchor.get("href", "")).casefold().startswith("mailto:")
            ]
        )
    research = _uw_profile_research(html_text)
    website = NOT_AVAILABLE
    for anchor in region.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True)).casefold()
        if label in {"homepage", "personal website", "lab website", "faculty website", "website"}:
            href = str(anchor.get("href", "")).strip()
            if href.casefold().startswith(("http://", "https://")):
                website = href
                break
    return UWPerson(
        name=name,
        title=title or NOT_AVAILABLE,
        email=email,
        profile_url=person.profile_url,
        research_interests=research,
        website_url=website if website != NOT_AVAILABLE else _website_from_soup(soup, person.profile_url, name),
        slug=person.slug,
    )


# ---------------- Scrapers ----------------


class UWDeptScraper(BaseUniversityScraper):
    """Shared base for the University of Washington department scrapers."""

    university_name = UW_UNIVERSITY_NAME
    department = NOT_AVAILABLE
    authoritative_roster = False
    verify_tls = True

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 30,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.max_profiles = max_profiles
        self.progress_callback = progress_callback
        self.person_count = 0

    def get_soup(self, url: str) -> BeautifulSoup:
        time.sleep(self.request_delay)
        response = self.session.get(url, timeout=self.timeout, verify=self.verify_tls)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def _floor_message(self, count: int) -> str | None:
        floor = UW_DEPT_FLOORS.get(self.department)
        if floor is not None and count < floor:
            return (
                f"{self.department} returned only {count} faculty records; "
                f"at least {floor} were expected."
            )
        return None

    def _enrich(self, person: UWPerson) -> UWPerson:
        """Fetch a profile page to enrich research/website (best effort)."""
        return person

    def _emit(
        self,
        people: list[UWPerson],
        source_label: str,
    ) -> list[ScrapedProfessor]:
        if self.max_profiles is not None:
            people = people[: self.max_profiles]
        self.person_count = len(people)
        records: list[ScrapedProfessor] = []
        total = len(people)
        for index, person in enumerate(people, start=1):
            if self.progress_callback:
                self.progress_callback(
                    f"Checking University of Washington {self.department} profile "
                    f"{index} of {total}: {person.name or person.slug}"
                )
            if not person.email:
                continue
            records.append(
                ScrapedProfessor(
                    name=person.name,
                    university=self.university_name,
                    department=self.department,
                    title=person.title or NOT_AVAILABLE,
                    research_interests=person.research_interests,
                    email=person.email,
                    website_url=person.website_url or NOT_AVAILABLE,
                    profile_url=person.profile_url,
                    source_type=source_label,
                )
            )
        return records


class UWProfilesScraper(UWDeptScraper):
    """Base for departments that follow each profile page."""

    def _enrich_all(self, people: list[UWPerson]) -> list[UWPerson]:
        for person in people:
            if person.profile_url == NOT_AVAILABLE:
                continue
            try:
                html_text = str(self.get_soup(person.profile_url))
            except Exception as exc:  # noqa: BLE001 - keep the roster row even if a profile fails.
                LOGGER.warning(
                    "Could not inspect UW %s profile for %s: %s",
                    self.department,
                    person.name or person.slug,
                    exc,
                )
                continue
            enriched = self.parse_profile(html_text, person)
            if enriched.name:
                person.name = enriched.name
            if person.title in {"", NOT_AVAILABLE} and enriched.title:
                person.title = enriched.title
            if not person.email and enriched.email:
                person.email = enriched.email
            if person.research_interests == NOT_AVAILABLE:
                person.research_interests = enriched.research_interests
            if person.website_url == NOT_AVAILABLE:
                person.website_url = enriched.website_url
        return people

    def parse_profile(self, html_text: str, person: UWPerson) -> UWPerson:
        raise NotImplementedError


class UWCSEFacultyScraper(UWProfilesScraper):
    directory_url = CSE_DIRECTORY_URL
    department = "Computer Science and Engineering"

    def parse_profile(self, html_text: str, person: UWPerson) -> UWPerson:
        return parse_cse_profile(html_text, person.profile_url)

    def scrape(self) -> list[ScrapedProfessor]:
        slugs = extract_cse_slugs(str(self.get_soup(self.directory_url)))
        people = [UWPerson(name="", profile_url=f"https://www.cs.washington.edu/people/faculty/{slug}/", slug=slug) for slug in slugs]
        people = self._enrich_all(people)
        records = self._emit(
            people,
            source_label=(
                "Official University of Washington Allen School faculty-members "
                "roster and profile pages"
            ),
        )
        message = self._floor_message(self.person_count)
        if message:
            self.last_error = message
        return records


class UWECEfacultyScraper(UWDeptScraper):
    directory_url = ECE_DIRECTORY_URL
    department = "Electrical and Computer Engineering"

    def scrape(self) -> list[ScrapedProfessor]:
        people = parse_ece_directory(str(self.get_soup(self.directory_url)), self.directory_url)
        records = self._emit(
            people,
            source_label=(
                "Official University of Washington Electrical & Computer "
                "Engineering faculty roster"
            ),
        )
        message = self._floor_message(self.person_count)
        if message:
            self.last_error = message
        return records


class UWCStatisticsScraper(UWProfilesScraper):
    directory_url = STATS_DIRECTORY_URL
    department = "Statistics"
    verify_tls = False  # stat.washington.edu publishes a chain the client cannot validate.

    def parse_profile(self, html_text: str, person: UWPerson) -> UWPerson:
        return parse_stats_profile(html_text, person)

    def scrape(self) -> list[ScrapedProfessor]:
        people = extract_stats_people(str(self.get_soup(self.directory_url)), "https://stat.washington.edu")
        people = self._enrich_all(people)
        records = self._emit(
            people,
            source_label=(
                "Official University of Washington Department of Statistics "
                "faculty roster and profile pages"
            ),
        )
        message = self._floor_message(self.person_count)
        if message:
            self.last_error = message
        return records


class RedirectableProfileScraper(UWProfilesScraper):
    """Drupal people-directory department (Chemistry/Physics/Economics/Biology)."""

    directory_base = ""
    source_label_text = ""
    list_parser = staticmethod(parse_drupal_people_list)

    def parse_profile(self, html_text: str, person: UWPerson) -> UWPerson:
        soup = BeautifulSoup(html_text, "html.parser")
        website = _website_from_soup(soup, person.profile_url, person.name)
        research = _uw_profile_research(html_text)
        return UWPerson(
            name=person.name,
            email=person.email,
            profile_url=person.profile_url,
            research_interests=research,
            website_url=website,
        )

    def scrape(self) -> list[ScrapedProfessor]:
        people = self.list_parser(str(self.get_soup(self.directory_url)), self.directory_base)
        people = self._enrich_all(people)
        records = self._emit(
            people,
            source_label=self.source_label_text,
        )
        message = self._floor_message(self.person_count)
        if message:
            self.last_error = message
        return records


class UWCHeChemistryScraper(RedirectableProfileScraper):
    directory_url = CHEM_DIRECTORY_URL
    department = "Chemistry"
    directory_base = "https://chem.washington.edu"
    source_label_text = (
        "Official University of Washington Department of Chemistry faculty "
        "directory and profile pages"
    )


class UWPhysicsScraper(RedirectableProfileScraper):
    directory_url = PHYS_DIRECTORY_URL
    department = "Physics"
    directory_base = "https://phys.washington.edu"
    source_label_text = (
        "Official University of Washington Department of Physics faculty "
        "directory and profile pages"
    )


class UWEconomicsScraper(RedirectableProfileScraper):
    directory_url = ECON_DIRECTORY_URL
    department = "Economics"
    directory_base = "https://econ.washington.edu"
    source_label_text = (
        "Official University of Washington Department of Economics faculty "
        "directory and profile pages"
    )


class UWBiologyScraper(RedirectableProfileScraper):
    directory_url = BIO_DIRECTORY_URL
    department = "Biology"
    directory_base = "https://biology.washington.edu"
    source_label_text = (
        "Official University of Washington Department of Biology faculty "
        "directory and profile pages"
    )
    list_parser = staticmethod(parse_bio_directory)


class UniversityOfWashingtonScraper(BaseUniversityScraper):
    """Combined University of Washington scraper (7 approved departments).

    Runs departments in canonical order (CSE first) so cross-listed people
    keep their first record, then collapses across departments through
    :func:`services.deduplication.deduplicate`.
    """

    university_name = UW_UNIVERSITY_NAME
    directory_url = CSE_DIRECTORY_URL
    authoritative_roster = False

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 30,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.sub_scrapers: list[UWDeptScraper] = [
            UWCSEFacultyScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWECEfacultyScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWCStatisticsScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWCHeChemistryScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWPhysicsScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWEconomicsScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
            UWBiologyScraper(request_delay=request_delay, timeout=timeout, max_profiles=max_profiles, progress_callback=progress_callback),
        ]
        self.last_error = ""

    def scrape(self) -> list[ScrapedProfessor]:
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            message
            for message in (getattr(sub, "last_error", "") for sub in self.sub_scrapers)
            if str(message or "").strip()
        ]
        if errors:
            self.last_error = " ".join(errors)
        elif not combined:
            self.last_error = "No University of Washington faculty records were returned."
        per_department = {sub.department: sub.person_count for sub in self.sub_scrapers}
        LOGGER.info(
            "University of Washington scraped per department: %s",
            per_department,
        )
        return combined
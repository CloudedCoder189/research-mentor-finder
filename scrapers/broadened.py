"""Non-destructive department broadening for registered universities.

V9.7 Phase 1 adds Electrical and Computer Engineering faculty at UC Santa Cruz
and UC Santa Barbara without rewriting the existing working scrapers. Each
broadened scraper runs its university's existing department scraper first,
followed by new department configs created from the shared configurable
framework, then combines the two sources with a light local cleanup:

* generic department mailboxes (``be-...-dept-*``, ``*-chair``, ``*-mgmt``,
  office/admin/staff mailboxes) are dropped so shared addresses never become
  professor records;
* role-card entries whose parsed name is only a heading (Undergraduate
  Director, Department Chair, ...) are dropped in favor of the person's own
  card, which shares the same email;
* cross-listed people collapse to their existing department because the
  existing department runs first and :func:`services.deduplication.deduplicate`
  keeps the first occurrence per email or per name+university.

The wrappers are deliberately *not* authoritative, so a successful refresh
never prunes existing records (stale-deletion rules are unchanged).
"""

from __future__ import annotations

import re

from scrapers.base import BaseUniversityScraper, ScrapedProfessor
from scrapers.berkeley import BerkeleyEEScraper, BerkeleyScraper
from scrapers.berkeley_stats import BerkeleyStatsScraper
from scrapers.configurable import (
    ConfigurableFacultyScraper,
    FacultyDirectoryConfig,
    _normalize,
)
from scrapers.ucsb import UCSBScraper
from scrapers.ucsc import UCSCScraper
from scrapers.ucsd import UCSDScraper
from scrapers.ucsd_ece import UCSDECEScraper
from services.deduplication import deduplicate

GENERIC_MAILBOX_TOKENS = (
    "dept",
    "chair",
    "director",
    "mgmt",
    "office",
    "admin",
    "staff",
    "support",
    "info",
    "contact",
    "helpdesk",
    "postmaster",
    "webmaster",
    "advising",
    "gradadvising",
)

# Normalized (no spaces/punctuation) names that are directory role-card headings
# rather than the person's own card.
ROLE_ONLY_NAMES = {
    "undergraduatedirector",
    "graduatedirector",
    "departmentchair",
    "facultyadvisor",
    "graduateadvisor",
    "undergraduateadvisor",
    "programdirector",
    "assistanttothechair",
    "chair",
    "director",
    "graduateadvising",
    "undergraduateadvising",
    "academicadvising",
}


def _acceptable_person(record: dict[str, str]) -> bool:
    if _normalize(record.get("name", "")) in ROLE_ONLY_NAMES:
        return False
    email = str(record.get("email", "")).strip()
    local = email.split("@", 1)[0].casefold()
    # UC Santa Cruz publishes shared department-managed mailboxes under a
    # ``be-`` prefix (for example ``be-ecechair@ucsc.edu``) that never belong to
    # a single professor.
    if local.startswith("be-"):
        return False
    for token in GENERIC_MAILBOX_TOKENS:
        if re.search(rf"(?:^|[._-]){re.escape(token)}(?:$|[._-])", local):
            return False
    return True


def combine_broadened(
    *sources: list[ScrapedProfessor] | list[dict[str, str]],
) -> list[ScrapedProfessor]:
    """Concatenate, locally clean, and cross-sourced deduplicate records.

    Sources are considered in order, so existing departments passed first keep
    their record when a person is cross-listed under several departments.
    """
    records: list[ScrapedProfessor] = []
    for source in sources:
        for item in source:
            record = item if isinstance(item, ScrapedProfessor) else ScrapedProfessor(**item)
            if _acceptable_person(record.as_record()):
                records.append(record)
    unique = deduplicate([record.as_record() for record in records])
    return [ScrapedProfessor(**row) for row in unique]


UCSC_ECE_CONFIG = FacultyDirectoryConfig(
    university_name="University of California, Santa Cruz",
    directory_url=(
        "https://engineering.ucsc.edu/departments/"
        "electrical-and-computer-engineering/people/"
    ),
    department="Electrical and Computer Engineering",
    source_type=(
        "Official UC Santa Cruz Electrical and Computer Engineering people "
        "directory and profiles"
    ),
    expected_email_domains=("ucsc.edu",),
    city="Santa Cruz",
    profile_path_hints=("/people/", "/faculty/"),
    allow_directory_profile_fallback=True,
)

UCSB_ECE_CONFIG = FacultyDirectoryConfig(
    university_name="University of California, Santa Barbara",
    directory_url="https://www.ece.ucsb.edu/people/faculty",
    department="Electrical and Computer Engineering",
    source_type=(
        "Official UC Santa Barbara Electrical and Computer Engineering faculty "
        "directory and profiles"
    ),
    expected_email_domains=("ucsb.edu",),
    city="Santa Barbara",
    profile_path_hints=("/people/", "/faculty/"),
    allow_directory_profile_fallback=True,
)


class UCSCECEScraper(ConfigurableFacultyScraper):
    config = UCSC_ECE_CONFIG


class UCSBECEScraper(ConfigurableFacultyScraper):
    config = UCSB_ECE_CONFIG


class BroadenedUCSCScraper(BaseUniversityScraper):
    university_name = "University of California, Santa Cruz"
    directory_url = UCSCScraper.directory_url

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.progress_callback = progress_callback
        self.sub_scrapers = [
            UCSCScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
            UCSCECEScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
        ]

    def scrape(self) -> list[ScrapedProfessor]:
        if self.progress_callback:
            self.progress_callback(
                "Reading UC Santa Cruz Computer Science and Electrical and "
                "Computer Engineering faculty sources..."
            )
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            str(getattr(sub_scraper, "last_error", "") or "").strip()
            for sub_scraper in self.sub_scrapers
        ]
        messages = [message for message in errors if message]
        if not combined:
            self.last_error = (
                "; ".join(messages) if messages else "No UC Santa Cruz faculty records were returned."
            )
        elif messages:
            self.last_error = "; ".join(messages)
        return combined


class BroadenedUCSBScraper(BaseUniversityScraper):
    university_name = "University of California, Santa Barbara"
    directory_url = UCSBScraper.directory_url

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.progress_callback = progress_callback
        self.sub_scrapers = [
            UCSBScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
            UCSBECEScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
        ]

    def scrape(self) -> list[ScrapedProfessor]:
        if self.progress_callback:
            self.progress_callback(
                "Reading UC Santa Barbara Computer Science and Electrical and "
                "Computer Engineering faculty sources..."
            )
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            str(getattr(sub_scraper, "last_error", "") or "").strip()
            for sub_scraper in self.sub_scrapers
        ]
        messages = [message for message in errors if message]
        if not combined:
            self.last_error = (
                "; ".join(messages) if messages else "No UC Santa Barbara faculty records were returned."
            )
        elif messages:
            self.last_error = "; ".join(messages)
        return combined


class BroadenedBerkeleyScraper(BaseUniversityScraper):
    """UC Berkeley Electrical Engineering and Computer Sciences + Statistics.

    The official EECS ``CS`` and ``EE`` directory lists use the same page
    generator, so both are parsed by
    :func:`scrapers.berkeley.parse_berkeley_directory_html`.  The Statistics
    department is added from the official Department of Statistics directory.
    The existing CS source runs first so cross-listed faculty (listed under
    several rosters, sometimes with different email addresses) keep their
    existing record; the full wrapper is deliberately non-authoritative.
    """
    university_name = "University of California, Berkeley"
    directory_url = BerkeleyScraper.directory_url

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.progress_callback = progress_callback
        self.sub_scrapers = [
            BerkeleyScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
            BerkeleyEEScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
            BerkeleyStatsScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
        ]

    def scrape(self) -> list[ScrapedProfessor]:
        if self.progress_callback:
            self.progress_callback(
                "Reading UC Berkeley Electrical Engineering and Computer Sciences "
                "and Department of Statistics faculty sources..."
            )
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            str(getattr(sub_scraper, "last_error", "") or "").strip()
            for sub_scraper in self.sub_scrapers
        ]
        messages = [message for message in errors if message]
        if not combined:
            self.last_error = (
                "; ".join(messages)
                if messages
                else "No UC Berkeley faculty records were returned."
            )
        elif messages:
            self.last_error = "; ".join(messages)
        return combined


class BroadenedUCSDScraper(BaseUniversityScraper):
    """UC San Diego Computer Science and Engineering, then Electrical + Computer Engineering.

    The existing CSE scraper runs first so cross-listed faculty (a handful
    appear on both the CSE and ECE rosters) keep their existing record.
    """
    university_name = "University of California, San Diego"
    directory_url = UCSDScraper.directory_url

    def __init__(
        self,
        request_delay: float = 0.45,
        timeout: int = 20,
        max_profiles: int | None = None,
        progress_callback=None,
    ) -> None:
        super().__init__(request_delay=request_delay, timeout=timeout)
        self.progress_callback = progress_callback
        self.sub_scrapers = [
            UCSDScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
            UCSDECEScraper(
                request_delay=request_delay,
                timeout=timeout,
                max_profiles=max_profiles,
                progress_callback=progress_callback,
            ),
        ]

    def scrape(self) -> list[ScrapedProfessor]:
        if self.progress_callback:
            self.progress_callback(
                "Reading UC San Diego Computer Science and Engineering and "
                "Electrical and Computer Engineering faculty sources..."
            )
        results = [sub_scraper.safe_scrape() for sub_scraper in self.sub_scrapers]
        combined = combine_broadened(*results)
        errors = [
            str(getattr(sub_scraper, "last_error", "") or "").strip()
            for sub_scraper in self.sub_scrapers
        ]
        messages = [message for message in errors if message]
        if not combined:
            self.last_error = (
                "; ".join(messages)
                if messages
                else "No UC San Diego faculty records were returned."
            )
        elif messages:
            self.last_error = "; ".join(messages)
        return combined
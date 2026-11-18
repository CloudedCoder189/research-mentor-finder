from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import parse_qs, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

NOT_AVAILABLE = "Not publicly available"

ProgressCallback = Callable[[str], None]

OFFICIAL_DOMAINS: dict[str, tuple[str, ...]] = {
    "Stanford University": ("stanford.edu",),
    "University of California, Berkeley": ("berkeley.edu",),
    "University of California, Los Angeles": ("ucla.edu",),
    "University of California, San Diego": ("ucsd.edu",),
    "San Jose State University": ("sjsu.edu",),
    "University of Southern California": ("usc.edu", "isi.edu"),
    "University of California, Davis": ("ucdavis.edu",),
    "University of California, Irvine": ("uci.edu", "ics.uci.edu"),
    "University of California, Santa Barbara": ("ucsb.edu",),
    "University of California, Santa Cruz": ("ucsc.edu",),
    "California Institute of Technology": ("caltech.edu",),
    "Santa Clara University": ("scu.edu",),
    "California Polytechnic State University, San Luis Obispo": ("calpoly.edu",),
    "San Diego State University": ("sdsu.edu",),
    "Oregon State University": (
        "oregonstate.edu",
        "orst.edu",
        "osucascades.edu",
    ),
    "University of Oregon": ("uoregon.edu",),
    "Portland State University": ("pdx.edu",),
    "University of Washington": (
        "uw.edu",
        "washington.edu",
        "u.washington.edu",
    ),
    "Washington State University": ("wsu.edu",),
    "Western Washington University": ("wwu.edu",),
}

BLOCKED_WEBSITE_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "scholar.google.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "www.youtube.com",
    "wikipedia.org",
    "www.wikipedia.org",
    "marktechpost.com",
    "www.marktechpost.com",
    "medium.com",
    "www.medium.com",
}

UCI_UNIVERSITY = "University of California, Irvine"
UCI_FACULTY_URL = "https://cs.ics.uci.edu/faculty/"

PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


@dataclass(slots=True)
class VerificationResult:
    professor_id: int
    name: str
    university: str
    status: str
    issues: str
    profile_status: str
    website_status: str
    email_status: str
    verified_at: str

    def as_record(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(slots=True)
class PageResult:
    url: str
    status_code: int | None
    final_url: str
    text: str
    html: str
    error: str = ""


def _session() -> requests.Session:
    session = requests.Session()
    contact_email = os.getenv("SCRAPER_CONTACT_EMAIL", "").strip()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    if "@" in contact_email:
        headers["From"] = contact_email
    session.headers.update(headers)
    retry = Retry(
        total=2,
        connect=2,
        read=1,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _name_tokens(name: str) -> list[str]:
    normalized = _normalize_text(name)
    blocked = {"dr", "prof", "professor", "phd", "md"}
    return [token for token in normalized.split() if token not in blocked and len(token) > 1]


def _first_name_equivalent(left: str, right: str) -> bool:
    """Return True for conservative short/full first-name variants.

    Faculty directories often use a formal first name while personal sites use
    a common short form (for example, Christopher/Chris or Daniel/Dan). We only
    apply this after an exact last-name match, which keeps the identity check
    conservative.
    """
    if left == right:
        return True
    if min(len(left), len(right)) < 3:
        return False
    return left.startswith(right) or right.startswith(left)


def _name_appears(name: str, text: str) -> bool:
    tokens = _name_tokens(name)
    normalized_text = _normalize_text(text)
    haystack_tokens = normalized_text.split()
    haystack = f" {normalized_text} "
    if len(tokens) < 2:
        return bool(tokens and f" {tokens[0]} " in haystack)

    first = tokens[0]
    last = tokens[-1]
    if last in haystack_tokens and any(
        _first_name_equivalent(first, token) for token in haystack_tokens
    ):
        return True

    compact_name = "".join(tokens)
    compact_haystack = re.sub(r"[^a-z0-9]", "", haystack)
    return compact_name in compact_haystack




def _decode_cloudflare_email(encoded_value: str) -> str:
    encoded = re.sub(r"[^0-9a-f]", "", str(encoded_value or "").casefold())
    if len(encoded) < 4 or len(encoded) % 2:
        return ""
    try:
        key = int(encoded[:2], 16)
        value = "".join(
            chr(int(encoded[index:index + 2], 16) ^ key)
            for index in range(2, len(encoded), 2)
        )
    except (ValueError, OverflowError):
        return ""
    value = value.casefold().strip(".,;:()[]{}<>\"'")
    return value if EMAIL_RE.fullmatch(value) else ""


def _email_appears(email: str, page: PageResult | None) -> bool:
    """Return True for normal, obfuscated, or Cloudflare-protected email text."""
    if not email or page is None or page.error:
        return False
    combined = f"{page.html} {page.text}".lower()
    if email.lower() in combined:
        return True
    soup = BeautifulSoup(page.html, "html.parser")
    protected: set[str] = set()
    for tag in soup.select("[data-cfemail]"):
        decoded = _decode_cloudflare_email(str(tag.get("data-cfemail", "")))
        if decoded:
            protected.add(decoded)
    for anchor in soup.find_all("a", href=True):
        match = re.search(
            r"/cdn-cgi/l/email-protection#([0-9a-f]+)",
            str(anchor.get("href", "")),
            flags=re.IGNORECASE,
        )
        if match:
            decoded = _decode_cloudflare_email(match.group(1))
            if decoded:
                protected.add(decoded)
    if email.casefold() in protected:
        return True
    local, _, domain = email.lower().partition("@")
    if not local or not domain:
        return False
    normalized = _normalize_text(combined)
    domain_tokens = domain.split(".")
    obfuscated = " ".join(
        [local, "at", *sum(([part, "dot"] for part in domain_tokens[:-1]), []), domain_tokens[-1]]
    )
    return obfuscated in normalized

def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except ValueError:
        return ""


def _domain_matches(host: str, accepted: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in accepted)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/") or "/"
    # Treat HTTP and HTTPS variants as the same link relationship. University
    # directories frequently publish an older http:// homepage while browsers
    # and scrapers store the upgraded https:// form.
    scheme = "https" if parsed.scheme.lower() in {"http", "https"} else parsed.scheme.lower()
    return urlunparse((scheme, parsed.netloc.lower(), clean_path, "", "", ""))


def _linked_urls(html_text: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    found: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = requests.compat.urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme in {"http", "https"}:
            found.add(_normalize_url(absolute))
    return found


def _browser_fetch_ucdavis(url: str, *, timeout: int) -> PageResult:
    if curl_requests is None:
        return PageResult(
            url=url,
            status_code=403,
            final_url=url,
            text="",
            html="",
            error="HTTP 403; curl_cffi is not installed for the UC Davis browser fallback",
        )
    try:
        headers = {"Accept-Language": "en-US,en;q=0.9", "Referer": "https://cs.ucdavis.edu/"}
        contact_email = os.getenv("SCRAPER_CONTACT_EMAIL", "").strip()
        if "@" in contact_email:
            headers["From"] = contact_email
        response = curl_requests.get(
            url,
            impersonate="chrome",
            timeout=timeout,
            allow_redirects=True,
            headers=headers,
        )
        status = int(response.status_code)
        if status >= 400:
            return PageResult(url, status, str(response.url), "", "", f"HTTP {status}")
        html_text = str(response.text)[:2_000_000]
        soup = BeautifulSoup(html_text, "html.parser")
        visible = soup.get_text(" ", strip=True)
        attributes = " ".join(
            str(tag.get(attr, ""))
            for tag in soup.find_all(True)
            for attr in ("alt", "title", "aria-label")
            if tag.get(attr)
        )
        return PageResult(
            url=url,
            status_code=status,
            final_url=str(response.url),
            text=" ".join(f"{visible} {attributes}".split()),
            html=html_text,
        )
    except Exception as exc:
        return PageResult(url, None, url, "", "", f"Browser-compatible request failed: {exc}")


def _fetch_page(
    session: requests.Session,
    url: str,
    *,
    timeout: int = 18,
    delay: float = 0.15,
) -> PageResult:
    time.sleep(delay)
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        status = int(response.status_code)
        if status == 403 and _host(url).endswith("cs.ucdavis.edu"):
            return _browser_fetch_ucdavis(url, timeout=timeout)
        if status >= 400:
            return PageResult(
                url=url,
                status_code=status,
                final_url=response.url,
                text="",
                html="",
                error=f"HTTP {status}",
            )
        html_text = response.text[:2_000_000]
        soup = BeautifulSoup(html_text, "html.parser")
        visible = soup.get_text(" ", strip=True)
        attributes = " ".join(
            str(tag.get(attr, ""))
            for tag in soup.find_all(True)
            for attr in ("alt", "title", "aria-label")
            if tag.get(attr)
        )
        text = " ".join(f"{visible} {attributes}".split())
        return PageResult(
            url=url,
            status_code=status,
            final_url=response.url,
            text=text,
            html=html_text,
        )
    except requests.RequestException as exc:
        return PageResult(
            url=url,
            status_code=None,
            final_url=url,
            text="",
            html="",
            error=str(exc),
        )

def _validate_title(record: dict[str, str]) -> list[str]:
    title = str(record.get("title", "")).strip()
    name = str(record.get("name", "")).strip()
    issues: list[str] = []
    if not title or title == NOT_AVAILABLE:
        issues.append("Title is missing")
        return issues
    # Legitimate interdisciplinary faculty titles can be very long. Treat a
    # title as a flattened directory row only when it is exceptionally long;
    # email/phone/name checks below still catch actual row contamination.
    if len(title) > 280:
        issues.append("Title appears to contain an entire directory row")
    if EMAIL_RE.search(title):
        issues.append("Title contains an email address")
    if PHONE_RE.search(title):
        issues.append("Title contains a phone number")
    if name and _normalize_text(name) in _normalize_text(title):
        issues.append("Title repeats the professor name")
    return issues


def _validate_research(record: dict[str, str]) -> list[str]:
    interests = str(record.get("research_interests", "")).strip()
    issues: list[str] = []
    if not interests or interests == NOT_AVAILABLE:
        issues.append("Research interests are missing")
    elif EMAIL_RE.search(interests) or PHONE_RE.search(interests):
        issues.append("Research interests contain contact information")
    elif len(interests) > 2500:
        issues.append("Research interests look unusually long")
    return issues


def _canonical_uci_profile_url(url: str) -> str:
    """Convert UCI query-string people URLs to their stable canonical route."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = parsed.netloc.casefold()
    if not (host == "ics.uci.edu" or host.endswith(".ics.uci.edu")):
        return url
    people_value = parse_qs(parsed.query).get("people", [""])[0].strip()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", people_value, re.IGNORECASE):
        return f"https://ics.uci.edu/people/{people_value.casefold()}/"
    return url


def _uci_profile_linked_from_roster(profile_url: str, roster_page: PageResult | None) -> bool:
    """Return True when the official UCI roster links to this faculty profile.

    UCI currently publishes query-string links such as ``?people=brian-demsky``
    while the database stores the equivalent canonical ``/people/brian-demsky/``
    route. Normal URL normalization drops the query string, so UCI needs a small
    purpose-built comparison here.
    """
    if not profile_url or roster_page is None or roster_page.error or not roster_page.html:
        return False
    expected = _canonical_uci_profile_url(profile_url)
    soup = BeautifulSoup(roster_page.html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        absolute = requests.compat.urljoin(roster_page.final_url or roster_page.url, str(anchor["href"]))
        if _canonical_uci_profile_url(absolute) == expected:
            return True
    return False


def _uci_roster_confirms(
    name: str,
    email: str,
    profile_url: str,
    roster_page: PageResult | None,
) -> bool:
    """Verify a UCI professor against the single official CS faculty roster.

    Repeated requests to individual UCI profiles can begin returning the generic
    ICS homepage with HTTP 200. The department roster is authoritative and
    contains the professor name, public email, and profile link in one page, so
    it is a safer identity source for batch audits.
    """
    return bool(
        roster_page
        and not roster_page.error
        and _name_appears(name, roster_page.text)
        and _email_appears(email, roster_page)
        and _uci_profile_linked_from_roster(profile_url, roster_page)
    )


def _fetch_uci_roster(session: requests.Session) -> PageResult:
    page = _fetch_page(session, UCI_FACULTY_URL, delay=0.0)
    expected_text = _normalize_text(page.text)
    if not page.error and "cs faculty" in expected_text and "computer science" in expected_text:
        return page
    if curl_requests is None:
        return page
    try:
        response = curl_requests.get(
            UCI_FACULTY_URL,
            impersonate="chrome",
            timeout=20,
            allow_redirects=True,
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://ics.uci.edu/",
            },
        )
        status = int(response.status_code)
        if status >= 400:
            return page
        html_text = str(response.text)[:2_000_000]
        soup = BeautifulSoup(html_text, "html.parser")
        visible = soup.get_text(" ", strip=True)
        attributes = " ".join(
            str(tag.get(attr, ""))
            for tag in soup.find_all(True)
            for attr in ("alt", "title", "aria-label")
            if tag.get(attr)
        )
        browser_page = PageResult(
            url=UCI_FACULTY_URL,
            status_code=status,
            final_url=str(response.url),
            text=" ".join(f"{visible} {attributes}".split()),
            html=html_text,
        )
        normalized = _normalize_text(browser_page.text)
        if "cs faculty" in normalized and "computer science" in normalized:
            return browser_page
    except Exception:
        pass
    return page


def verify_record(
    record: dict[str, str | int],
    *,
    session: requests.Session | None = None,
    uci_roster_page: PageResult | None = None,
) -> VerificationResult:
    session = session or _session()
    professor_id = int(record.get("id", 0))
    name = str(record.get("name", "")).strip()
    university = str(record.get("university", "")).strip()
    email = str(record.get("email", "")).strip().lower()
    profile_url = _canonical_uci_profile_url(
        str(record.get("profile_url", NOT_AVAILABLE)).strip()
    )
    website_url = str(record.get("website_url", NOT_AVAILABLE)).strip()

    fatal: list[str] = []
    warnings: list[str] = []

    title_issues = _validate_title({k: str(v) for k, v in record.items()})
    for issue in title_issues:
        if issue == "Title is missing":
            warnings.append(issue)
        else:
            fatal.append(issue)
    warnings.extend(_validate_research({k: str(v) for k, v in record.items()}))

    accepted_domains = OFFICIAL_DOMAINS.get(university, ())
    email_host = email.rsplit("@", 1)[-1] if "@" in email else ""
    if not email or not EMAIL_RE.fullmatch(email):
        fatal.append("Email format is invalid")
        email_status = "Invalid"
    elif accepted_domains and not _domain_matches(email_host, accepted_domains):
        warnings.append("Email domain does not match the university")
        email_status = "Review"
    else:
        email_status = "Verified domain"

    profile_page: PageResult | None = None
    profile_status = "Missing"
    if not profile_url or profile_url == NOT_AVAILABLE:
        fatal.append("Official profile URL is missing")
    else:
        profile_host = _host(profile_url)
        if accepted_domains and not _domain_matches(profile_host, accepted_domains):
            fatal.append("Faculty profile is not on an official university domain")
        roster_verified = (
            university == UCI_UNIVERSITY
            and _uci_roster_confirms(name, email, profile_url, uci_roster_page)
        )
        if roster_verified:
            profile_status = "Verified from official faculty roster"
            email_status = "Verified on official faculty roster"

        # When the authoritative UCI roster already confirms the person, email,
        # and exact profile link, avoid dozens of individual requests. UCI starts
        # serving a generic homepage during larger batches even though it returns
        # HTTP 200. We only need the individual page when a personal website must
        # be checked for an official link relationship.
        should_fetch_profile = not roster_verified or (
            website_url and website_url != NOT_AVAILABLE and website_url != profile_url
        )
        if should_fetch_profile:
            profile_page = _fetch_page(session, profile_url)
            if profile_page.error:
                if roster_verified:
                    profile_page = uci_roster_page
                elif profile_page.status_code in {401, 403, 429}:
                    warnings.append(
                        f"Official profile could not be automatically checked ({profile_page.error})"
                    )
                    profile_status = f"Blocked ({profile_page.error})"
                else:
                    fatal.append(f"Official profile could not be opened ({profile_page.error})")
                    profile_status = f"Failed ({profile_page.error})"
            elif not _name_appears(name, profile_page.text):
                if roster_verified:
                    profile_page = uci_roster_page
                else:
                    fatal.append("Professor name was not found on the official profile page")
                    profile_status = "Wrong or changed page"
            else:
                profile_status = "Verified"
                email_visible = _email_appears(email, profile_page)
                email_status = "Verified on profile" if email_visible else email_status
        elif roster_verified:
            profile_page = uci_roster_page

    website_status = "Not provided"
    email_visible_on_website = False
    if website_url and website_url != NOT_AVAILABLE and website_url != profile_url:
        site_host = _host(website_url)
        linked_from_profile = False
        if profile_page and profile_page.html:
            linked_from_profile = _normalize_url(website_url) in _linked_urls(
                profile_page.html, profile_page.final_url
            )
        if site_host in BLOCKED_WEBSITE_DOMAINS or any(
            site_host.endswith(f".{blocked}") for blocked in BLOCKED_WEBSITE_DOMAINS
        ):
            if linked_from_profile:
                warnings.append(
                    "Website is a scholar or social platform profile that the "
                    "official faculty page itself links to"
                )
                website_status = "Officially linked platform profile"
            else:
                fatal.append("Website points to a news, social, or publication platform")
                website_status = "Rejected domain"
        else:
            website_page = _fetch_page(session, website_url)
            if website_page.error:
                if linked_from_profile:
                    warnings.append(
                        f"Website is linked from the official profile but could not be opened ({website_page.error})"
                    )
                    website_status = "Officially linked; currently unavailable"
                elif website_page.status_code in {401, 403, 429}:
                    warnings.append(
                        f"Website could not be automatically checked ({website_page.error})"
                    )
                    website_status = f"Blocked ({website_page.error})"
                else:
                    fatal.append(f"Website could not be opened ({website_page.error})")
                    website_status = f"Failed ({website_page.error})"
            else:
                email_visible_on_website = _email_appears(email, website_page)
            if not website_page.error:
                if linked_from_profile:
                    website_status = "Verified from official profile"
                elif _name_appears(name, website_page.text):
                    website_status = "Verified by page identity"
                    warnings.append("Website was not linked from the checked official profile")
                else:
                    fatal.append("Website appears unrelated to the professor")
                    website_status = "Identity mismatch"

    if (
        profile_page
        and not profile_page.error
        and email
        and email_status == "Verified domain"
        and not email_visible_on_website
    ):
        # The scraper may have obtained the address from the official directory
        # rather than the individual profile. Keep this as a review warning only
        # when the address is not visible on either checked page.
        warnings.append("Email was not visible on the checked profile page")
        email_status = "Official domain; not visible on checked pages"
    elif email_visible_on_website:
        email_status = "Verified on website"

    if fatal:
        status = "Failed"
        issues = fatal + warnings
    elif warnings:
        status = "Review"
        issues = warnings
    else:
        status = "Verified"
        issues = []

    return VerificationResult(
        professor_id=professor_id,
        name=name,
        university=university,
        status=status,
        issues="; ".join(dict.fromkeys(issues)) or "No issues found",
        profile_status=profile_status,
        website_status=website_status,
        email_status=email_status,
        verified_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def audit_records(
    records: list[dict[str, str | int]],
    *,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, str | int]]:
    session = _session()
    uci_roster_page: PageResult | None = None
    if any(str(record.get("university", "")) == UCI_UNIVERSITY for record in records):
        uci_roster_page = _fetch_uci_roster(session)
    results: list[dict[str, str | int]] = []
    total = len(records)
    for index, record in enumerate(records, start=1):
        if progress_callback:
            progress_callback(
                f"Checking {index}/{total}: {record.get('name', 'Unknown')} — "
                f"{record.get('university', 'Unknown')}"
            )
        results.append(
            verify_record(
                record,
                session=session,
                uci_roster_page=uci_roster_page,
            ).as_record()
        )
    return results

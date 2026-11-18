from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from services.verification import _fetch_page

NOT_AVAILABLE = "Not publicly available"
LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str], None]


NON_WEBSITE_HOSTS = {
    "drive.google.com", "docs.google.com", "accounts.google.com",
    "dropbox.com", "box.com", "onedrive.live.com",
}
AUTH_HOSTS = {"accounts.google.com", "login.microsoftonline.com", "login.live.com"}
DOCUMENT_PATH_RE = re.compile(
    r"(?:\.(?:pdf|docx?|pptx?|xlsx?|zip)(?:$|[?#])|/file/d/|/document/d/|/spreadsheets/d/)",
    re.IGNORECASE,
)


def _host_matches(host: str, blocked_hosts: set[str]) -> bool:
    host = host.casefold().split(":", 1)[0]
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in blocked_hosts)


def _is_document_or_auth_url(url: str) -> bool:
    parsed = urlparse(url)
    return _host_matches(parsed.netloc, NON_WEBSITE_HOSTS) or bool(DOCUMENT_PATH_RE.search(url))

LINK_AUDIT_SCOPES = (
    "Unchecked website links",
    "Broken or review website links",
    "One university",
    "Selected professors",
    "All website links",
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", ascii_text.casefold())


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
        total=1,
        connect=1,
        read=1,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def select_link_records(
    records: Iterable[Mapping[str, object]],
    *,
    scope: str,
    university: str | None = None,
    selected_ids: set[int] | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    selected_ids = selected_ids or set()
    output: list[dict[str, object]] = []
    for raw in records:
        record = dict(raw)
        website = str(record.get("website_url", NOT_AVAILABLE)).strip()
        status = str(record.get("website_status", "Not checked")).strip()
        if website in {"", NOT_AVAILABLE}:
            continue
        if scope == "Unchecked website links" and status != "Not checked":
            continue
        if scope == "Broken or review website links" and status not in {"Broken", "Review"}:
            continue
        if scope == "One university" and str(record.get("university")) != str(university):
            continue
        if scope == "Selected professors" and int(record.get("id", 0)) not in selected_ids:
            continue
        output.append(record)
    output.sort(key=lambda item: (str(item.get("university", "")), str(item.get("name", ""))))
    return output[:limit] if limit else output


def _official_profile_links_to(profile_html: str, profile_url: str, website_url: str) -> bool:
    soup = BeautifulSoup(profile_html, "html.parser")
    target = website_url.rstrip("/").casefold()
    target_host = urlparse(website_url).netloc.casefold()
    target_path = urlparse(website_url).path.rstrip("/").casefold()
    for anchor in soup.find_all("a", href=True):
        absolute = requests.compat.urljoin(profile_url, str(anchor.get("href", ""))).rstrip("/")
        if absolute.casefold() == target:
            return True
        parsed = urlparse(absolute)
        if parsed.netloc.casefold() == target_host and parsed.path.rstrip("/").casefold() == target_path:
            return True
    return False


def _identity_found(html_text: str, name: str) -> bool:
    text = _normalize(BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True))
    parts = [part for part in re.findall(r"[a-z]+", unicodedata.normalize("NFKD", name).casefold()) if len(part) > 1]
    if not parts:
        return False
    last = _normalize(parts[-1])
    first = _normalize(parts[0])
    return bool(last and last in text and (first in text or (first and first[0] + last in text)))


def verify_website_link(
    record: Mapping[str, object],
    *,
    session: requests.Session | None = None,
    timeout: int = 14,
) -> dict[str, object]:
    website_url = str(record.get("website_url", NOT_AVAILABLE)).strip()
    profile_url = str(record.get("profile_url", NOT_AVAILABLE)).strip()
    professor_id = int(record.get("id", 0))
    name = str(record.get("name", "")).strip()
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if website_url in {"", NOT_AVAILABLE}:
        return {
            "professor_id": professor_id,
            "name": name,
            "university": str(record.get("university", "")),
            "website_url": website_url,
            "status": "Not available",
            "issue": "No separate personal or lab website is published",
            "checked_at": checked_at,
            "final_url": NOT_AVAILABLE,
        }

    parsed = urlparse(website_url)
    if _is_document_or_auth_url(website_url):
        return {
            "professor_id": professor_id,
            "name": name,
            "university": str(record.get("university", "")),
            "website_url": website_url,
            "status": "Broken",
            "issue": "Link is a document, file-sharing page, or sign-in page rather than a public personal/lab website",
            "checked_at": checked_at,
            "final_url": NOT_AVAILABLE,
        }
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "professor_id": professor_id,
            "name": name,
            "university": str(record.get("university", "")),
            "website_url": website_url,
            "status": "Broken",
            "issue": "Invalid website URL",
            "checked_at": checked_at,
            "final_url": NOT_AVAILABLE,
        }

    client = session or _session()
    response: requests.Response | None = None
    website_error = ""
    try:
        response = client.get(website_url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.SSLError as exc:
        website_error = f"SSL certificate prevented automated verification: {exc}"
    except requests.exceptions.Timeout:
        website_error = "Website timed out during verification"
    except requests.exceptions.ConnectionError as exc:
        website_error = f"Website connection failed: {exc}"
    except requests.RequestException as exc:
        website_error = f"Website request failed: {exc}"

    profile_links = False
    if profile_url not in {"", NOT_AVAILABLE}:
        profile_page = _fetch_page(client, profile_url, timeout=timeout, delay=0)
        if not profile_page.error:
            profile_links = _official_profile_links_to(
                profile_page.html, profile_page.final_url, website_url
            )

    if response is None:
        status = "Verified" if profile_links else "Review"
        issue = (
            "Official faculty profile links to this site, but the site blocked automated verification"
            if profile_links
            else website_error
        )
        return {
            "professor_id": professor_id,
            "name": name,
            "university": str(record.get("university", "")),
            "website_url": website_url,
            "status": status,
            "issue": issue,
            "checked_at": checked_at,
            "final_url": website_url,
        }

    final_url = response.url or website_url
    final_parsed = urlparse(final_url)
    if _host_matches(final_parsed.netloc, AUTH_HOSTS):
        status = "Review"
        issue = "Website redirected to a sign-in page and is not publicly accessible"
    elif response.status_code in {404, 410}:
        status = "Broken"
        issue = f"Website returned HTTP {response.status_code}"
    elif response.status_code in {401, 403, 429}:
        status = "Verified" if profile_links else "Review"
        issue = (
            f"Official faculty profile links to this site; site returned HTTP {response.status_code} to automated checks"
            if profile_links
            else f"Website blocked automated checks with HTTP {response.status_code}"
        )
    elif response.status_code >= 400:
        status = "Review"
        issue = f"Website returned HTTP {response.status_code}"
    elif _identity_found(response.text[:500_000], name):
        status = "Verified"
        issue = "Website loaded and matched the professor's name"
    elif profile_links:
        status = "Verified"
        issue = "Official faculty profile links to this website"
    else:
        status = "Review"
        issue = "Website loaded, but the professor's identity was not confirmed automatically"

    return {
        "professor_id": professor_id,
        "name": name,
        "university": str(record.get("university", "")),
        "website_url": website_url,
        "status": status,
        "issue": issue,
        "checked_at": checked_at,
        "final_url": final_url,
    }


def audit_website_links(
    records: Iterable[Mapping[str, object]],
    *,
    progress_callback: ProgressCallback | None = None,
    request_delay: float = 0.15,
) -> list[dict[str, object]]:
    rows = list(records)
    client = _session()
    results: list[dict[str, object]] = []
    total = len(rows)
    for index, record in enumerate(rows, start=1):
        if progress_callback:
            progress_callback(
                f"Checking website {index} of {total}: {record.get('name', 'Unknown professor')}"
            )
        results.append(verify_website_link(record, session=client))
        if request_delay:
            time.sleep(request_delay)
    return results


def website_is_publicly_usable(record: Mapping[str, object], *, owner_mode: bool = False) -> bool:
    website = str(record.get("website_url", NOT_AVAILABLE)).strip()
    if website in {"", NOT_AVAILABLE}:
        return False
    status = str(record.get("website_status", "Not checked")).strip()
    if owner_mode:
        return status != "Broken"
    return status in {"Verified", "Not checked"}

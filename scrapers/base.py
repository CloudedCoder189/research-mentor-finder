from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ScrapedProfessor:
    name: str
    university: str
    department: str = "Not publicly available"
    title: str = "Not publicly available"
    research_interests: str = "Not publicly available"
    email: str = ""
    website_url: str = "Not publicly available"
    profile_url: str = "Not publicly available"
    categories: str = ""
    opportunity_level: str = "Basic"
    opportunity_signals: str = "No explicit opportunity information found"
    opportunity_source_url: str = "Not publicly available"
    source_type: str = "University website"

    def as_record(self) -> dict[str, str]:
        return asdict(self)


class BaseUniversityScraper(ABC):
    university_name: str
    directory_url: str

    def __init__(self, request_delay: float = 1.0, timeout: int = 20) -> None:
        self.request_delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.last_error = ""

        # Most university directories are ordinary public web pages. A browser-compatible
        # request profile avoids false 403 responses from CDNs that reject the default
        # Python/requests fingerprint. The optional From header still lets the owner
        # identify the crawler without sending an invalid placeholder address.
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
        self.session.headers.update(headers)

        retry_policy = Retry(
            total=3,
            connect=3,
            read=2,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_soup(self, url: str) -> BeautifulSoup:
        time.sleep(self.request_delay)
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    @staticmethod
    def absolute_url(base_url: str, value: str | None) -> str:
        if not value:
            return "Not publicly available"
        return urljoin(base_url, value)

    @staticmethod
    def clean_text(value: Any) -> str:
        if value is None:
            return "Not publicly available"
        text = " ".join(str(value).split()).strip()
        return text or "Not publicly available"

    def safe_scrape(self) -> list[ScrapedProfessor]:
        try:
            return self.scrape()
        except requests.RequestException as exc:
            self.last_error = str(exc)
            LOGGER.error("Network error scraping %s: %s", self.university_name, exc)
        except Exception as exc:  # Keeps one layout failure from stopping all universities.
            self.last_error = str(exc)
            LOGGER.exception("Unexpected scraper error for %s: %s", self.university_name, exc)
        return []

    @abstractmethod
    def scrape(self) -> list[ScrapedProfessor]:
        raise NotImplementedError

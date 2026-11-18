from __future__ import annotations

from dataclasses import dataclass

from scrapers.base import BaseUniversityScraper, ScrapedProfessor


@dataclass(frozen=True)
class DirectorySelectors:
    card: str
    name: str
    profile_link: str
    title: str | None = None
    department: str | None = None
    interests: str | None = None
    email: str | None = None
    website: str | None = None


class GenericDirectoryScraper(BaseUniversityScraper):
    """Reusable scraper for faculty directories with repeated profile cards."""

    selectors: DirectorySelectors
    default_department = "Computer Science"

    def scrape(self) -> list[ScrapedProfessor]:
        soup = self.get_soup(self.directory_url)
        records: list[ScrapedProfessor] = []

        for card in soup.select(self.selectors.card):
            name_element = card.select_one(self.selectors.name)
            link_element = card.select_one(self.selectors.profile_link)
            if not name_element or not link_element:
                continue

            email = ""
            if self.selectors.email:
                email_element = card.select_one(self.selectors.email)
                if email_element:
                    email = (email_element.get("href") or email_element.get_text()).replace(
                        "mailto:", ""
                    ).strip()

            # Version one includes only people with a public email.
            if not email:
                continue

            profile_url = self.absolute_url(self.directory_url, link_element.get("href"))
            records.append(
                ScrapedProfessor(
                    name=self.clean_text(name_element.get_text()),
                    university=self.university_name,
                    department=self._text(card, self.selectors.department, self.default_department),
                    title=self._text(card, self.selectors.title),
                    research_interests=self._text(card, self.selectors.interests),
                    email=email,
                    website_url=self._url(card, self.selectors.website),
                    profile_url=profile_url,
                )
            )

        return records

    def _text(self, card, selector: str | None, default: str = "Not publicly available") -> str:
        if not selector:
            return default
        element = card.select_one(selector)
        return self.clean_text(element.get_text()) if element else default

    def _url(self, card, selector: str | None) -> str:
        if not selector:
            return "Not publicly available"
        element = card.select_one(selector)
        return self.absolute_url(self.directory_url, element.get("href") if element else None)

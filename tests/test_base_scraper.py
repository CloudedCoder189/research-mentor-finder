from scrapers.base import BaseUniversityScraper


class ExampleScraper(BaseUniversityScraper):
    university_name = "Example"
    directory_url = "https://example.edu"

    def scrape(self):
        return []


def test_base_scraper_omits_invalid_from_header(monkeypatch):
    monkeypatch.setenv("SCRAPER_CONTACT_EMAIL", "contact-not-configured")
    scraper = ExampleScraper(request_delay=0)
    assert "From" not in scraper.session.headers
    assert "Mozilla" in scraper.session.headers["User-Agent"]


def test_base_scraper_uses_valid_contact_header(monkeypatch):
    monkeypatch.setenv("SCRAPER_CONTACT_EMAIL", "owner@example.com")
    scraper = ExampleScraper(request_delay=0)
    assert scraper.session.headers["From"] == "owner@example.com"

import requests

from services.link_verification import (
    select_link_records,
    verify_website_link,
    website_is_publicly_usable,
)


class FakeResponse:
    def __init__(self, status_code=200, text="", url="https://lab.example.edu"):
        self.status_code = status_code
        self.text = text
        self.url = url


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, *args, **kwargs):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def record(**overrides):
    data = {
        "id": 1,
        "name": "Ada Lovelace",
        "university": "Example University",
        "website_url": "https://lab.example.edu",
        "profile_url": "https://example.edu/people/ada",
        "website_status": "Not checked",
    }
    data.update(overrides)
    return data


def test_verified_when_site_contains_professor_name():
    result = verify_website_link(
        record(), session=FakeSession([
            FakeResponse(text="<h1>Ada Lovelace</h1>"),
            FakeResponse(text="<a href='https://lab.example.edu'>Lab</a>", url="https://example.edu/people/ada"),
        ])
    )
    assert result["status"] == "Verified"


def test_broken_for_404():
    result = verify_website_link(
        record(), session=FakeSession([
            FakeResponse(status_code=404),
            FakeResponse(text="", url="https://example.edu/people/ada"),
        ])
    )
    assert result["status"] == "Broken"


def test_blocked_site_is_verified_when_official_profile_links_to_it():
    result = verify_website_link(
        record(), session=FakeSession([
            requests.exceptions.SSLError("certificate"),
            FakeResponse(text="<a href='https://lab.example.edu'>Lab Website</a>", url="https://example.edu/people/ada"),
        ])
    )
    assert result["status"] == "Verified"


def test_public_button_requires_verified_status():
    assert website_is_publicly_usable(record(website_status="Verified"))
    assert not website_is_publicly_usable(record(website_status="Broken"))
    assert website_is_publicly_usable(record(website_status="Not checked"))
    assert website_is_publicly_usable(record(website_status="Review"), owner_mode=True)


def test_targeted_link_scope():
    rows = [
        record(id=1, website_status="Not checked"),
        record(id=2, website_status="Broken"),
        record(id=3, website_status="Verified"),
    ]
    assert [r["id"] for r in select_link_records(rows, scope="Unchecked website links")] == [1]
    assert [r["id"] for r in select_link_records(rows, scope="Broken or review website links")] == [2]


def test_google_drive_document_is_not_accepted_as_professor_website():
    result = verify_website_link(record(website_url="https://drive.google.com/file/d/abc/view"))
    assert result["status"] == "Broken"
    assert "document" in result["issue"].casefold()


def test_google_site_redirect_to_login_is_review_not_verified():
    result = verify_website_link(
        record(website_url="https://sites.google.com/example/lab"),
        session=FakeSession([
            FakeResponse(
                text="Sign in",
                url="https://accounts.google.com/v3/signin/identifier",
            ),
            FakeResponse(
                text="<a href='https://sites.google.com/example/lab'>Lab</a>",
                url="https://example.edu/people/ada",
            ),
        ]),
    )
    assert result["status"] == "Review"


def test_link_session_uses_browser_headers_without_fake_from(monkeypatch):
    from services import link_verification

    monkeypatch.delenv("SCRAPER_CONTACT_EMAIL", raising=False)
    session = link_verification._session()
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")
    assert "From" not in session.headers

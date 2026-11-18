from services import verification


BASE_RECORD = {
    "id": 1,
    "name": "Ada Lovelace",
    "university": "Stanford University",
    "department": "Computer Science",
    "title": "Professor",
    "research_interests": "Artificial intelligence and machine learning",
    "email": "ada@stanford.edu",
    "profile_url": "https://cs.stanford.edu/people/ada",
    "website_url": "https://adalab.example.org",
}


def test_verifies_official_profile_and_linked_website(monkeypatch):
    profile_html = (
        '<html><body>Ada Lovelace <a href="mailto:ada@stanford.edu">Email</a>'
        '<a href="https://adalab.example.org">Lab website</a></body></html>'
    )

    def fake_fetch(_session, url, **_kwargs):
        if "stanford.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Ada Lovelace Professor ada@stanford.edu",
                html=profile_html,
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Ada Lovelace Research Lab",
            html="<html>Ada Lovelace Research Lab</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(BASE_RECORD, session=object())

    assert result.status == "Verified"
    assert result.profile_status == "Verified"
    assert result.website_status == "Verified from official profile"
    assert result.email_status == "Verified on profile"


def test_rejects_unrelated_website(monkeypatch):
    record = dict(BASE_RECORD)
    record["website_url"] = "https://random.example.org/news"

    def fake_fetch(_session, url, **_kwargs):
        if "stanford.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Ada Lovelace ada@stanford.edu",
                html="<html>Ada Lovelace ada@stanford.edu</html>",
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Completely unrelated news article",
            html="<html>Completely unrelated news article</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())

    assert result.status == "Failed"
    assert "unrelated" in result.issues.lower()


def test_officially_linked_platform_profile_is_review_not_failed(monkeypatch):
    record = dict(BASE_RECORD)
    record["website_url"] = (
        "https://scholar.google.com/citations?user=abc123&hl=en&oi=ao"
    )
    profile_html = (
        '<html><body>Ada Lovelace <a href="mailto:ada@stanford.edu">Email</a>'
        '<a href="https://scholar.google.com/citations?user=abc123">Scholar</a></body></html>'
    )

    def fake_fetch(_session, url, **_kwargs):
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Ada Lovelace ada@stanford.edu",
            html=profile_html if "stanford.edu" in url else "",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())

    assert result.status == "Review"
    assert "platform profile" in result.issues.lower()
    assert "unrelated" not in result.issues.lower()


def test_rejects_flattened_title(monkeypatch):
    record = dict(BASE_RECORD)
    record["title"] = (
        "Ada Lovelace Professor (408) 555-1212 ada@stanford.edu Artificial Intelligence"
    )

    def fake_fetch(_session, url, **_kwargs):
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Ada Lovelace ada@stanford.edu",
            html="<html>Ada Lovelace ada@stanford.edu</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())

    assert result.status == "Failed"
    assert "title" in result.issues.lower()


def test_marks_blocked_official_profile_for_review(monkeypatch):
    record = dict(BASE_RECORD)
    record["website_url"] = "Not publicly available"

    def fake_fetch(_session, url, **_kwargs):
        return verification.PageResult(
            url=url,
            status_code=403,
            final_url=url,
            text="",
            html="",
            error="HTTP 403",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())

    assert result.status == "Review"
    assert "403" in result.issues


def test_allows_legitimate_long_interdisciplinary_title(monkeypatch):
    record = dict(BASE_RECORD)
    record["title"] = (
        "Niki and Max Nikias Chair in Engineering and University Professor of "
        "Electrical and Computer Engineering, Computer Science, Linguistics, "
        "Psychology, Pediatrics, and Otolaryngology"
    )
    record["website_url"] = "Not publicly available"

    def fake_fetch(_session, url, **_kwargs):
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Ada Lovelace ada@stanford.edu",
            html="<html>Ada Lovelace ada@stanford.edu</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"


def test_profile_alt_text_can_verify_directory_person(monkeypatch):
    record = dict(BASE_RECORD)
    record["name"] = "Benjamin Poon"
    record["university"] = "San Jose State University"
    record["email"] = "ben.poon@sjsu.edu"
    record["profile_url"] = "https://www.sjsu.edu/cs/faculty/lecturers.php"
    record["website_url"] = "Not publicly available"

    def fake_fetch(_session, url, **_kwargs):
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Lecturers Benjamin Poon Artificial Intelligence ben.poon@sjsu.edu",
            html='<html><img alt="Benjamin Poon image">ben.poon@sjsu.edu</html>',
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"


def test_email_visible_on_personal_website_satisfies_audit(monkeypatch):
    record = dict(BASE_RECORD)

    def fake_fetch(_session, url, **_kwargs):
        if "stanford.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Ada Lovelace Professor",
                html='<html>Ada Lovelace <a href="https://adalab.example.org">Lab website</a></html>',
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Ada Lovelace ada@stanford.edu Research Lab",
            html="<html>Ada Lovelace ada@stanford.edu Research Lab</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"
    assert result.email_status == "Verified on website"


def test_name_matching_accepts_common_short_and_formal_variants():
    assert verification._name_appears(
        "Chris Piech", "Christopher Piech Associate Professor"
    )
    assert verification._name_appears(
        "Dan Yamins", "Daniel Yamins Associate Professor"
    )
    assert not verification._name_appears(
        "Dan Yamins", "Daniel Robertson Associate Professor"
    )


def test_verifies_profile_with_formal_name_and_personal_site_with_short_name(monkeypatch):
    record = dict(BASE_RECORD)
    record.update(
        {
            "name": "Dan Yamins",
            "email": "yamins@stanford.edu",
            "profile_url": "https://profiles.stanford.edu/daniel-yamins",
            "website_url": "https://stanford.edu/~yamins/",
        }
    )

    def fake_fetch(_session, url, **_kwargs):
        if "profiles.stanford.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Daniel Yamins Associate Professor yamins@stanford.edu",
                html=(
                    '<html>Daniel Yamins yamins@stanford.edu '
                    '<a href="https://stanford.edu/~yamins/">Website</a></html>'
                ),
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Dan Yamins Stanford computer scientist",
            html="<html>Dan Yamins Stanford computer scientist</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"
    assert result.profile_status == "Verified"
    assert result.website_status == "Verified from official profile"


def test_verifies_obfuscated_email_on_personal_website(monkeypatch):
    record = dict(BASE_RECORD)
    record.update(
        {
            "name": "Chris Piech",
            "email": "piech@cs.stanford.edu",
            "profile_url": "https://profiles.stanford.edu/christopher-piech",
            "website_url": "https://stanford.edu/~cpiech/bio/index.html",
        }
    )

    def fake_fetch(_session, url, **_kwargs):
        if "profiles.stanford.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Christopher Piech Associate Professor",
                html=(
                    '<html>Christopher Piech '
                    '<a href="https://stanford.edu/~cpiech/bio/index.html">Website</a></html>'
                ),
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Chris Piech Email piech at cs dot stanford dot edu",
            html="<html>Chris Piech Email piech at cs dot stanford dot edu</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"
    assert result.website_status == "Verified from official profile"
    assert result.email_status == "Verified on website"


def test_ucdavis_blocked_profile_uses_browser_fallback(monkeypatch):
    class FakeResponse:
        status_code = 403
        url = "https://cs.ucdavis.edu/directory/test-person"
        text = ""

    class FakeSession:
        def get(self, *_args, **_kwargs):
            return FakeResponse()

    expected = verification.PageResult(
        url=FakeResponse.url,
        status_code=200,
        final_url=FakeResponse.url,
        text="Test Person test@ucdavis.edu",
        html="<html>Test Person test@ucdavis.edu</html>",
    )
    monkeypatch.setattr(verification, "_browser_fetch_ucdavis", lambda *_args, **_kwargs: expected)
    result = verification._fetch_page(FakeSession(), FakeResponse.url, delay=0)
    assert result.status_code == 200
    assert "Test Person" in result.text


def test_ucdavis_officially_linked_lab_is_not_false_identity_failure(monkeypatch):
    record = dict(BASE_RECORD)
    record.update(
        {
            "name": "Matthew Farrens",
            "university": "University of California, Davis",
            "email": "farrens@ucdavis.edu",
            "profile_url": "https://cs.ucdavis.edu/directory/matthew-farrens",
            "website_url": "https://example.org/farrens-lab",
        }
    )

    def fake_fetch(_session, url, **_kwargs):
        if "ucdavis.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Matthew Farrens Professor farrens@ucdavis.edu",
                html=(
                    '<html>Matthew Farrens farrens@ucdavis.edu '
                    '<a href="https://example.org/farrens-lab">Research Lab</a></html>'
                ),
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Computer Architecture Research Group",
            html="<html>Computer Architecture Research Group</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"
    assert result.website_status == "Verified from official profile"


def test_uci_query_profile_is_checked_via_canonical_people_path(monkeypatch):
    record = dict(BASE_RECORD)
    record.update({
        "name": "Brian Demsky",
        "university": "University of California, Irvine",
        "email": "bdemsky@uci.edu",
        "profile_url": "https://ics.uci.edu/?people=brian-demsky",
        "website_url": "Not publicly available",
    })
    seen = []

    def fake_fetch(_session, url, **_kwargs):
        seen.append(url)
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Brian Demsky Professor bdemsky@uci.edu",
            html="<html>Brian Demsky bdemsky@uci.edu</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert seen[0] == "https://ics.uci.edu/people/brian-demsky/"
    assert result.status == "Verified"


def test_uci_roster_verifies_record_when_individual_profile_turns_into_homepage(monkeypatch):
    record = dict(BASE_RECORD)
    record.update({
        "name": "Brian Demsky",
        "university": "University of California, Irvine",
        "email": "bdemsky@uci.edu",
        "profile_url": "https://ics.uci.edu/people/brian-demsky/",
        "website_url": "Not publicly available",
    })
    roster_html = (
        '<html><h1>CS Faculty</h1><a href="https://ics.uci.edu/?people=brian-demsky">'
        'View Brian Demsky</a><h3>Brian Demsky</h3>'
        '<p>Professor Computer Science bdemsky@uci.edu</p></html>'
    )
    roster = verification.PageResult(
        url=verification.UCI_FACULTY_URL,
        status_code=200,
        final_url=verification.UCI_FACULTY_URL,
        text="CS Faculty Brian Demsky Professor Computer Science bdemsky@uci.edu",
        html=roster_html,
    )

    def fail_if_profile_fetched(*_args, **_kwargs):
        raise AssertionError("individual UCI profile should not be fetched when roster is authoritative")

    monkeypatch.setattr(verification, "_fetch_page", fail_if_profile_fetched)
    result = verification.verify_record(
        record,
        session=object(),
        uci_roster_page=roster,
    )

    assert result.status == "Verified"
    assert result.profile_status == "Verified from official faculty roster"
    assert result.email_status == "Verified on official faculty roster"


def test_uci_roster_fallback_ignores_generic_homepage_for_profile(monkeypatch):
    record = dict(BASE_RECORD)
    record.update({
        "name": "Brian Demsky",
        "university": "University of California, Irvine",
        "email": "bdemsky@uci.edu",
        "profile_url": "https://ics.uci.edu/people/brian-demsky/",
        "website_url": "https://plrg.ics.uci.edu/",
    })
    roster_html = (
        '<html><h1>CS Faculty</h1><a href="/?people=brian-demsky">View Brian Demsky</a>'
        '<h3>Brian Demsky</h3><p>Professor Computer Science bdemsky@uci.edu</p></html>'
    )
    roster = verification.PageResult(
        url=verification.UCI_FACULTY_URL,
        status_code=200,
        final_url=verification.UCI_FACULTY_URL,
        text="CS Faculty Brian Demsky Professor Computer Science bdemsky@uci.edu",
        html=roster_html,
    )

    def fake_fetch(_session, url, **_kwargs):
        if "people/brian-demsky" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url="https://ics.uci.edu/",
                text="UC Irvine Donald Bren School of Information and Computer Sciences",
                html="<html>Generic ICS homepage</html>",
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Brian Demsky bdemsky@uci.edu Programming Languages Research Group",
            html="<html>Brian Demsky bdemsky@uci.edu</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(
        record,
        session=object(),
        uci_roster_page=roster,
    )

    assert result.status == "Review"
    assert "Professor name was not found" not in result.issues
    assert result.profile_status == "Verified from official faculty roster"
    assert result.email_status == "Verified on website"


def test_uci_audit_fetches_roster_once_and_skips_individual_profiles(monkeypatch):
    records = []
    for professor_id, name, email, slug in (
        (1, "Brian Demsky", "bdemsky@uci.edu", "brian-demsky"),
        (2, "Alex Berg", "bergac@uci.edu", "alex-berg"),
    ):
        record = dict(BASE_RECORD)
        record.update({
            "id": professor_id,
            "name": name,
            "university": "University of California, Irvine",
            "email": email,
            "profile_url": f"https://ics.uci.edu/people/{slug}/",
            "website_url": "Not publicly available",
        })
        records.append(record)

    roster_html = (
        '<html><h1>CS Faculty</h1>'
        '<a href="/?people=brian-demsky">View Brian Demsky</a>'
        '<p>Brian Demsky Professor Computer Science bdemsky@uci.edu</p>'
        '<a href="/?people=alex-berg">View Alex Berg</a>'
        '<p>Alex Berg Associate Professor Computer Science bergac@uci.edu</p>'
        '</html>'
    )
    roster = verification.PageResult(
        url=verification.UCI_FACULTY_URL,
        status_code=200,
        final_url=verification.UCI_FACULTY_URL,
        text=(
            "CS Faculty Brian Demsky Professor Computer Science bdemsky@uci.edu "
            "Alex Berg Associate Professor Computer Science bergac@uci.edu"
        ),
        html=roster_html,
    )
    calls = []

    def fake_roster(_session):
        calls.append("roster")
        return roster

    def fail_individual(*_args, **_kwargs):
        raise AssertionError("individual UCI profiles should not be fetched")

    monkeypatch.setattr(verification, "_fetch_uci_roster", fake_roster)
    monkeypatch.setattr(verification, "_fetch_page", fail_individual)
    results = verification.audit_records(records)

    assert calls == ["roster"]
    assert [row["status"] for row in results] == ["Verified", "Verified"]


def test_official_profile_http_link_matches_saved_https_website(monkeypatch):
    record = dict(BASE_RECORD)
    record.update(
        {
            "name": "Patrick Tantalo",
            "university": "University of California, Santa Cruz",
            "email": "ptantalo@ucsc.edu",
            "profile_url": "https://campusdirectory.ucsc.edu/cd_detail?uid=ptantalo",
            "website_url": "https://people.ucsc.edu/~ptantalo/",
        }
    )

    def fake_fetch(_session, url, **_kwargs):
        if "campusdirectory.ucsc.edu" in url:
            return verification.PageResult(
                url=url,
                status_code=200,
                final_url=url,
                text="Patrick Tantalo Lecturer ptantalo@ucsc.edu",
                html=(
                    "<html>Patrick Tantalo ptantalo@ucsc.edu "
                    '<a href="http://people.ucsc.edu/~ptantalo/">Home Page</a></html>'
                ),
            )
        return verification.PageResult(
            url=url,
            status_code=200,
            final_url=url,
            text="Course materials",
            html="<html>Course materials</html>",
        )

    monkeypatch.setattr(verification, "_fetch_page", fake_fetch)
    result = verification.verify_record(record, session=object())
    assert result.status == "Verified"
    assert result.website_status == "Verified from official profile"

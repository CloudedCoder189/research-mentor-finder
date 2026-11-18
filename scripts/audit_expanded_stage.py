"""Recheck the 51 repaired records; reuse captured profiles, fetch public websites.

Writes only their verification fields in the expanded private staging database.
No app login, private profile reads, AI calls, or original database writes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import sqlite3
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from scripts.review_ucla_sources import CAPTURES, EVIDENCE
from scripts.stage_expanded_ucla_repairs import STAGE
from services import verification


def main():
    with sqlite3.connect(STAGE) as connection:
        connection.row_factory = sqlite3.Row
        records = [dict(row) for row in connection.execute("SELECT * FROM professors WHERE embedding_json = '' ORDER BY id")]
    assert len(records) == 51
    pages = {}
    for record in records:
        metadata = json.loads((CAPTURES / f"{record['id']}.json").read_text(encoding="utf-8"))
        raw = (CAPTURES / f"{record['id']}.html").read_bytes()
        assert metadata["status"] == 200 and hashlib.sha256(raw).hexdigest() == metadata["sha256"]
        html = raw.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        attributes = " ".join(str(tag.get(attr, "")) for tag in soup.find_all(True)
                              for attr in ("alt", "title", "aria-label") if tag.get(attr))
        page = verification.PageResult(record["profile_url"], 200, metadata["response_url"],
                                       soup.get_text(" ", strip=True) + " " + attributes, html)
        pages[verification._normalize_url(record["profile_url"])] = page
    actual_fetch = verification._fetch_page
    website_urls = sorted(set(str(record["website_url"]) for record in records if record["website_url"] != "Not publicly available"))
    website_captures = []

    def fetch_website(url):
        parsed = urlparse(url)
        assert parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
        assert parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        secure_url = urlunparse(parsed._replace(scheme="https"))
        with verification._session() as session:
            result = actual_fetch(session, secure_url, timeout=12, delay=0)
        # The source relationship still uses the originally published URL.
        result.url = url
        return url, result

    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, (url, page) in enumerate(pool.map(fetch_website, website_urls), start=1):
            key = verification._normalize_url(url)
            pages[key] = page
            digest = hashlib.sha256(page.html.encode()).hexdigest()
            capture_path = CAPTURES / f"website-{hashlib.sha256(url.encode()).hexdigest()[:16]}.html"
            capture_path.write_text(page.html, encoding="utf-8")
            website_captures.append({"requested_url": url, "checked_url": urlunparse(urlparse(url)._replace(scheme="https")),
                                     "final_url": page.final_url, "status_code": page.status_code,
                                     "error": page.error, "html_sha256": digest})
            print(json.dumps({"websites_checked": index, "of": len(website_urls), "http_status": page.status_code}), flush=True)

    def cached_fetch(session, url, **kwargs):
        key = verification._normalize_url(url)
        if key not in pages:
            raise RuntimeError("Audit attempted to leave the captured public-page scope")
        return pages[key]

    verification._fetch_page = cached_fetch
    results = []
    try:
        for record in records:
            result = verification.verify_record(record)
            if record["id"] == 141:
                if result.status == "Verified":
                    result.status = "Review"
                caution = "Official title specifies a future start date (November 1, 2027); current appointment/availability needs confirmation"
                result.issues = caution if result.issues == "No issues found" else result.issues + "; " + caution
            results.append(asdict(result))
    finally:
        verification._fetch_page = actual_fetch
    with sqlite3.connect(STAGE) as connection:
        before_other = connection.execute("SELECT id, verification_status, verification_issues, verified_at FROM professors WHERE id NOT IN (" + ",".join("?" for _ in records) + ") ORDER BY id", tuple(r["id"] for r in records)).fetchall()
        connection.executemany("UPDATE professors SET verification_status=?, verification_issues=?, verified_at=? WHERE id=?",
                               [(r["status"], r["issues"], r["verified_at"], r["professor_id"]) for r in results])
        after_other = connection.execute("SELECT id, verification_status, verification_issues, verified_at FROM professors WHERE id NOT IN (" + ",".join("?" for _ in records) + ") ORDER BY id", tuple(r["id"] for r in records)).fetchall()
        assert before_other == after_other
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    counts = {status: sum(r["status"] == status for r in results) for status in ("Verified", "Review", "Failed")}
    (EVIDENCE / "targeted-verification.json").write_text(json.dumps({
        "scope": "51 repaired records only; existing deterministic identity/contact/link verifier plus reviewed title/department manifest",
        "profile_sources": "Previously captured live public university pages, hash checked",
        "website_checks": "Fresh anonymous HTTPS GETs; old HTTP source links treated as the equivalent relationship",
        "counts": counts, "results": results, "website_captures": website_captures,
        "limitations": "Automated verification does not establish recruitment availability or complete research-field accuracy; source conflicts/future starts remain flagged",
        "paid_calls": 0}, indent=2), encoding="utf-8")
    print(json.dumps({"targeted_records": len(records), "statuses": counts}))


if __name__ == "__main__":
    main()

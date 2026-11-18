"""Capture public university sources for the UCLA repair; never write a database."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

from scripts.real_acceptance_snapshot import ROOT, DEST
from scrapers.ucla import parse_ucla_profile_html, _normalize_person_name

CAPTURES = ROOT / "test-runtime/ucla-expanded-source-20261005"
EVIDENCE = ROOT / "evidence/ucla-expanded-repair-2026-10-05"
RANK = re.compile(r"\b(?:(?:assistant|associate|distinguished|adjunct)\s+)?professor(?:\s+emerit(?:us|a))?\b", re.I)
SOURCE_HOSTS = {"samueli.ucla.edu", "www2.eecs.berkeley.edu", "web.cs.ucla.edu"}


def target_records() -> list[dict]:
    with sqlite3.connect(DEST.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute("""SELECT id, name, title, department, profile_url
            FROM professors WHERE title = 'Expert Directory' OR id = 30 ORDER BY id""")]


def capture(record: dict) -> dict:
    url = record["profile_url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS:
        raise ValueError("Source outside the explicit public university allowlist")
    metadata = {"id": record["id"], "name": record["name"], "requested_url": url,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        redirects = []
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS:
                raise ValueError("Redirect outside the explicit public university allowlist")
            response = requests.get(url, timeout=(10, 25), allow_redirects=False)
            if response.status_code not in {301, 302, 303, 307, 308} or not response.headers.get("Location"):
                break
            destination = urljoin(url, response.headers["Location"])
            redirects.append({"from": url, "status": response.status_code, "to": destination})
            url = destination
        metadata["redirects"] = redirects
        metadata.update(status=response.status_code, response_url=response.url)
        if response.status_code == 200:
            raw = response.content
            (CAPTURES / f"{record['id']}.html").write_bytes(raw)
            metadata.update(raw_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        else:
            metadata["error"] = "Non-200 response; no fields accepted"
    except requests.RequestException as exc:
        metadata["error"] = type(exc).__name__
    (CAPTURES / f"{record['id']}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def review(record: dict) -> dict:
    metadata = json.loads((CAPTURES / f"{record['id']}.json").read_text(encoding="utf-8"))
    result = metadata | {"stored_title": record["title"], "stored_department": record["department"]}
    if metadata.get("status") != 200:
        return result
    raw = (CAPTURES / f"{record['id']}.html").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == metadata["sha256"]
    soup = BeautifulSoup(raw, "html.parser")
    identity = soup.select_one(".seas-profile-identity")
    if not identity:
        result["review_needed"] = "No modern UCLA identity container (Berkeley has its own template)"
        return result
    heading = identity.find("h1")
    result["source_name"] = heading.get_text(" ", strip=True) if heading else ""
    result["identity_name_matches"] = _normalize_person_name(result["source_name"]) == _normalize_person_name(record["name"])
    result["explicit_titles"] = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-title")]
    result["explicit_departments"] = [node.get_text(" ", strip=True) for node in identity.select(".seas-profile-chip--dept")]
    profile = soup.select_one(".seas-profile")
    # Rank mentions outside the explicit appointment header are observations,
    # not an automatic determination that the person holds those ranks.
    if profile:
        identity.extract()
        result["other_rank_mentions"] = sorted(set(match.group(0) for match in RANK.finditer(profile.get_text(" ", strip=True))))
    details = parse_ucla_profile_html(raw.decode("utf-8", errors="replace"), record["profile_url"], record["name"])
    result["parsed_fields"] = {field: getattr(details, field) for field in ("title", "department", "research_interests", "website_url")}
    result["review_status"] = "pending_human_or_agent_source_review"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="Public GET requests only; no app/provider calls")
    args = parser.parse_args()
    CAPTURES.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    records = target_records()
    if args.fetch:
        with ThreadPoolExecutor(max_workers=2) as pool:
            for index, result in enumerate(pool.map(capture, records), start=1):
                print(json.dumps({"completed": index, "of": len(records), "id": result["id"], "status": result.get("status"), "error": result.get("error")}), flush=True)
    reviews = [review(record) for record in records]
    (EVIDENCE / "source-review.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    print(json.dumps({"reviewed_captures": len(reviews), "http_200": sum(r.get("status") == 200 for r in reviews)}))


if __name__ == "__main__":
    main()

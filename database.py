from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable, Mapping, Sequence
from threading import RLock

from runtime_config import PROJECT_ROOT

from services.taxonomy import infer_taxonomy
from services.university_registry import infer_department_category, metadata_for

BASE_DIR = PROJECT_ROOT
_configured_db = Path(os.getenv("PROFESSOR_DB_PATH", BASE_DIR / "data" / "professors.db")).expanduser()
DB_PATH = (_configured_db if _configured_db.is_absolute() else BASE_DIR / _configured_db).resolve()

NOT_AVAILABLE = "Not publicly available"

DEFAULT_USER_ID = "local-owner"

OUTREACH_STATUSES = (
    "Not contacted",
    "Email drafted",
    "Email sent",
    "Follow-up needed",
    "Replied",
    "Meeting scheduled",
    "Rejected",
)


BLOCKED_NON_PERSON_NAMES = {
    "terms of use",
    "privacy policy",
    "accessibility",
    "contact us",
    "faculty directory",
    "research areas",
}

BLOCKED_WEBSITE_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "marktechpost.com",
    "www.marktechpost.com",
    "drive.google.com",
    "docs.google.com",
    "accounts.google.com",
    "dropbox.com",
    "box.com",
    "onedrive.live.com",
}

GENERIC_WEBSITE_PATH_FRAGMENTS = (
    "/research/research-areas-labs",
    "/research/areas/centers",
    "/research/research-centers",
)

KNOWN_RECORD_FIXES: dict[tuple[str, str], dict[str, str]] = {
    ("Stanford University", "Chris Piech"): {
        "profile_url": "https://profiles.stanford.edu/christopher-piech",
        "website_url": "https://stanford.edu/~cpiech/bio/index.html",
        "title": "Associate Professor (Teaching) of Computer Science and, by courtesy, in the Graduate School of Education",
    },
    ("Stanford University", "Dan Yamins"): {
        "profile_url": "https://profiles.stanford.edu/daniel-yamins",
        "website_url": "https://stanford.edu/~yamins/",
        "email": "yamins@stanford.edu",
        "title": "Associate Professor of Psychology and of Computer Science",
    },
    ("Stanford University", "Emma Brunskill"): {
        "profile_url": "https://profiles.stanford.edu/emma-brunskill",
        "website_url": "https://cs.stanford.edu/people/ebrun/",
        "email": "ebrun@cs.stanford.edu",
        "title": "Associate Professor of Computer Science",
    },
    ("Stanford University", "Ehsan Adeli"): {
        "profile_url": "https://profiles.stanford.edu/ehsan-adeli",
        "website_url": "https://stanford.edu/~eadeli/",
        "title": "Assistant Professor (Research) of Psychiatry and Behavioral Sciences and, by courtesy, of Computer Science and of Biomedical Data Science",
    },
    ("Stanford University", "James Zou"): {
        "profile_url": "https://profiles.stanford.edu/james-zou",
        "website_url": "https://www.james-zou.com/",
        "title": "Associate Professor of Biomedical Data Science and, by courtesy, of Computer Science and of Electrical Engineering",
    },
    ("University of California, Santa Barbara", "James A. Preiss"): {
        "profile_url": "https://www.cs.ucsb.edu/people/faculty/james-preiss",
        "website_url": "https://www.jamespreiss.com/",
        "email": "preiss@ucsb.edu",
        "title": "Assistant Professor",
    },
    ("University of California, Santa Barbara", "Misha Sra"): {
        "profile_url": "https://www.cs.ucsb.edu/people/faculty/misha-sra",
        "website_url": "https://sites.cs.ucsb.edu/~sra/",
        "email": "sra@cs.ucsb.edu",
        "title": "Associate Professor",
    },
    ("University of California, Santa Cruz", "Patrick Tantalo"): {
        "email": "ptantalo@ucsc.edu",
        "title": "Lecturer",
    },
    ("University of Southern California", "Wensheng Wu"): {
        "profile_url": "https://viterbi.usc.edu/directory/faculty/Wu/Wensheng",
        "website_url": "Not publicly available",
        "email": "wenshenw@usc.edu",
        "title": "Associate Professor of Computer Science Practice",
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS professors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    university TEXT NOT NULL,
    university_slug TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT 'Not publicly available',
    state TEXT NOT NULL DEFAULT 'Not publicly available',
    department TEXT NOT NULL DEFAULT 'Not publicly available',
    department_category TEXT NOT NULL DEFAULT 'Other Research Area',
    title TEXT NOT NULL DEFAULT 'Not publicly available',
    research_interests TEXT NOT NULL DEFAULT 'Not publicly available',
    email TEXT NOT NULL,
    website_url TEXT NOT NULL DEFAULT 'Not publicly available',
    website_status TEXT NOT NULL DEFAULT 'Not checked',
    website_issue TEXT NOT NULL DEFAULT 'Not checked',
    website_checked_at TEXT NOT NULL DEFAULT 'Not publicly available',
    website_final_url TEXT NOT NULL DEFAULT 'Not publicly available',
    profile_url TEXT NOT NULL DEFAULT 'Not publicly available',
    data_source_url TEXT NOT NULL DEFAULT 'Not publicly available',
    categories TEXT NOT NULL DEFAULT '',
    ai_categories TEXT NOT NULL DEFAULT '',
    ai_summary TEXT NOT NULL DEFAULT '',
    embedding_json TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_source_hash TEXT NOT NULL DEFAULT '',
    ai_enriched_at TEXT NOT NULL DEFAULT 'Not publicly available',
    opportunity_level TEXT NOT NULL DEFAULT 'Basic',
    opportunity_signals TEXT NOT NULL DEFAULT 'No explicit opportunity information found',
    opportunity_source_url TEXT NOT NULL DEFAULT 'Not publicly available',
    source_type TEXT NOT NULL DEFAULT 'University website',
    verification_status TEXT NOT NULL DEFAULT 'Not checked',
    verification_issues TEXT NOT NULL DEFAULT 'Not checked',
    verified_at TEXT NOT NULL DEFAULT 'Not publicly available',
    last_checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(email COLLATE NOCASE)
);

CREATE INDEX IF NOT EXISTS idx_professors_university
ON professors(university);

CREATE INDEX IF NOT EXISTS idx_professors_name_university
ON professors(name, university);

CREATE UNIQUE INDEX IF NOT EXISTS uq_professors_name_university_nocase
ON professors(name COLLATE NOCASE, university COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS query_embedding_cache (
    query_hash TEXT PRIMARY KEY,
    normalized_query TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_query_embedding_cache_model
ON query_embedding_cache(model);

CREATE TABLE IF NOT EXISTS usage_counters (
    usage_date TEXT NOT NULL,
    usage_name TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usage_date, usage_name)
);

CREATE TABLE IF NOT EXISTS app_migrations (
    migration_key TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS professor_outreach (
    professor_id INTEGER PRIMARY KEY,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    outreach_status TEXT NOT NULL DEFAULT 'Not contacted',
    email_sent_at TEXT NOT NULL DEFAULT '',
    follow_up_date TEXT NOT NULL DEFAULT '',
    email_to TEXT NOT NULL DEFAULT '',
    email_subject TEXT NOT NULL DEFAULT '',
    email_body TEXT NOT NULL DEFAULT '',
    gmail_draft_id TEXT NOT NULL DEFAULT '',
    gmail_thread_id TEXT NOT NULL DEFAULT '',
    gmail_account_email TEXT NOT NULL DEFAULT '',
    gmail_draft_created_at TEXT NOT NULL DEFAULT '',
    gmail_sent_at TEXT NOT NULL DEFAULT '',
    gmail_replied_at TEXT NOT NULL DEFAULT '',
    gmail_reply_count INTEGER NOT NULL DEFAULT 0,
    gmail_last_checked_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    csrf_token TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user
ON sessions(user_id);

CREATE TABLE IF NOT EXISTS student_profiles (
    user_id TEXT PRIMARY KEY,
    interests_json TEXT NOT NULL DEFAULT '[]',
    interest_text TEXT NOT NULL DEFAULT '',
    skills_json TEXT NOT NULL DEFAULT '[]',
    experience_json TEXT NOT NULL DEFAULT '[]',
    coursework_json TEXT NOT NULL DEFAULT '[]',
    education_level TEXT NOT NULL DEFAULT 'unspecified',
    preferences_json TEXT NOT NULL DEFAULT '{}',
    profile_completed INTEGER NOT NULL DEFAULT 0 CHECK (profile_completed IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
"""

V8_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_professors_location
ON professors(state, city);

CREATE INDEX IF NOT EXISTS idx_professors_department_category
ON professors(department_category);

CREATE INDEX IF NOT EXISTS idx_professors_verification
ON professors(verification_status);

CREATE INDEX IF NOT EXISTS idx_professors_website_status
ON professors(website_status);
"""



TITLE_PATTERNS = (
    "Distinguished Professor",
    "Professor and Chair",
    "Assistant Teaching Professor",
    "Associate Teaching Professor",
    "Teaching Professor",
    "Assistant Professor",
    "Associate Professor",
    "Research Professor",
    "Adjunct Professor",
    "Professor Emeritus",
    "Professor",
    "Senior Lecturer",
    "Lecturer",
    "Research Scientist",
    "Staff Scientist",
    "Postdoctoral Researcher",
    "Postdoctoral Scholar",
    "Director",
)


RANK_WORD_RE = re.compile(
    r"\b(?:professor|lecturer|instructor|scientist|researcher|emeritus|chair|"
    r"director|dean|president|faculty|postdoctoral|scholar|affiliate|adjunct|"
    r"assistant|associate|visiting|clinical|teaching|distinguished|head|"
    r"coordinator|specialist|administrator|engineer)\b",
    re.IGNORECASE,
)

# Directory pages often flatten the whole faculty card into one string, so the
# stored title can end with breadcrumbs, tab labels, credentials, or prose.
TITLE_NAV_LABEL_RE = re.compile(
    r"\s+(?:"
    r"Profile\s+Publications\s+Teaching"
    r"|Publications\s+Teaching"
    r"|Teaching\s+Overview"
    r"|Overview"
    r"|Affiliation\b"
    r"|Faculty\s+Type\b"
    r"|Web\s+Site\b"
    r"|Home\s+Page\b"
    r"|E-?Mail\b"
    r"|More\s+options\b"
    r"|More\b"
    r"|External\b"
    r"|Primary\b"
    r"|Pronouns\s*:"
    r")",
    re.IGNORECASE,
)

TITLE_CREDENTIAL_RE = re.compile(
    r"[,:;]?\s+(?:"
    r"B\.\s?S\.?|B\.\s?A\.?|M\.\s?S\.?|M\.\s?S\.?c|M\.\s?A\.?|M\.\s?B\.\s?A\.?|"
    r"Ph\.\s?D\.?|MBA|J\.\s?D\.|"
    r"B\.\s?Tech\.?"
    r")\s*(?:,|\.|\s)",
    re.IGNORECASE,
)

TITLE_BREADCRUMB_RE = re.compile(
    r"\b(?:College of|Department of|School of|Faculty of|San Diego|SDSU|"
    r"Pronouns\s*:)\b",
    re.IGNORECASE,
)

TITLE_REPEATED_BLOCK_RE = re.compile(
    r"^(?P<block>\S.{9,}?)\s+\1(?:\s+(?P<tail>\S.*))?$", re.DOTALL
)

TITLE_TRAILING_PRONOUNS_RE = re.compile(r"\s+Pronouns\s*:\s*[a-z/ ]+$", re.IGNORECASE)

TITLE_TRAILING_DIGITS_RE = re.compile(r"\s+\d{5,}\s*$")

# Guards for the connector-separated repetition rule below. The block must be a
# substantial multi-word phrase (not a bare rank) and the gap must stay short.
TITLE_REPEATED_BLOCK_MIN_CHARS = 30
TITLE_CONNECTOR_GAP_MAX_CHARS = 60
TITLE_CONNECTOR_GAP_MAX_WORDS = 12


def _dedupe_repeated_title_block(title: str) -> str:
    """Drop a title block that a directory page repeated verbatim."""
    match = TITLE_REPEATED_BLOCK_RE.match(title)
    if not match:
        return title
    block = match.group("block").strip()
    if not RANK_WORD_RE.search(block):
        return title
    tail = (match.group("tail") or "").strip()
    return f"{block} {tail}".strip() if tail else block


def _collapse_repeated_title_block_with_connector(title: str) -> str:
    """Collapse a repeated leading title block separated by a short connector.

    Some faculty directories print the endowed-chair form of a name before and
    after the real title, for example:

        "Distinguished Professor <Chair A> Professor <Chair B> Professor of ECE
         Dean of the College of Engineering & Distinguished Professor <Chair A>
         Professor <Chair B> Professor"

    The two copies are not adjacent, so the verbatim repetition rule cannot see
    them, and deleting either copy leaves a dangling connector. Keep the leading
    copy plus the connector gap and drop the trailing duplicate.

    Deliberately narrow: the repeated block must start the title, be at least
    ``TITLE_REPEATED_BLOCK_MIN_CHARS`` long, contain a rank word, and be
    separated by a short gap that carries no digits or sentence punctuation.
    """

    words = title.split()
    for size in range(len(words) - 1, 3, -1):
        block = " ".join(words[:size])
        if len(block) < TITLE_REPEATED_BLOCK_MIN_CHARS:
            continue
        if not RANK_WORD_RE.search(block):
            continue
        rest = words[size:]
        if len(rest) <= size or " ".join(rest[-size:]) != block:
            continue
        gap = " ".join(rest[:-size])
        if not gap or len(gap) > TITLE_CONNECTOR_GAP_MAX_CHARS:
            continue
        if re.search(r"[.\d]", gap) or len(gap.split()) > TITLE_CONNECTOR_GAP_MAX_WORDS:
            continue
        return f"{block} {gap}".strip(" &–—-,:;")
    return title


def _clean_title(value: str) -> str:
    title = " ".join(str(value).split()).strip()
    if not title:
        return NOT_AVAILABLE

    # Berkeley uses visual page labels such as "Below The Line" to separate
    # faculty groups. They are layout text, not part of an academic title.
    title = re.sub(
        r"^\s*(?:above|below)\s+the\s+line\s*[,;:|–—-]*\s*",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    if not title:
        return NOT_AVAILABLE

    title = _dedupe_repeated_title_block(title)
    title = _collapse_repeated_title_block_with_connector(title)
    title = TITLE_TRAILING_DIGITS_RE.sub("", title).strip()
    title = PRONOUN_SUFFIX_RE.sub("", title).strip()
    title = TITLE_TRAILING_PRONOUNS_RE.sub("", title).strip()

    nav_label = TITLE_NAV_LABEL_RE.search(title)
    if nav_label and RANK_WORD_RE.search(title[: nav_label.start()]):
        title = title[: nav_label.start()].strip(" |–—-,:;")

    credential = TITLE_CREDENTIAL_RE.search(title)
    if credential and RANK_WORD_RE.search(title[: credential.start()]):
        title = title[: credential.start()].strip(" |–—-,:;")

    breadcrumb = TITLE_BREADCRUMB_RE.search(title)
    if (
        breadcrumb
        and len(TITLE_BREADCRUMB_RE.findall(title)) >= 2
        and RANK_WORD_RE.search(title[: breadcrumb.start()])
    ):
        title = title[: breadcrumb.start()].strip(" |–—-,:;")

    title = " ".join(title.split()).strip(" |–—-,:;")
    if not title:
        return NOT_AVAILABLE

    if "@" not in title and not re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", title):
        return title
    for canonical in TITLE_PATTERNS:
        if re.search(rf"\b{re.escape(canonical)}\b", title, re.IGNORECASE):
            return canonical
    return NOT_AVAILABLE


def _clean_email(value: str) -> str:
    email = str(value).strip().lower().strip(".,;:()[]{}<>\"'")
    # Repair a known class of scraper punctuation artifacts such as .edua.
    email = re.sub(r"\.edua$", ".edu", email)
    return email


PRONOUN_SUFFIX_RE = re.compile(
    r"(?:\s+(?:he/him(?:/his)?|she/her(?:/hers)?|they/them(?:/theirs)?"
    r"|ze/zir(?:/hir)?|xe/xem|ey/em|ve/ver|zee/hir))\s*$",
    re.IGNORECASE,
)

NAV_CHROME_MARKERS = (
    "campus directory",
    "myucsc",
    "a-z index",
    "find people",
    "search campus directory",
    "quick start guides",
    "prospective students",
    "calendars",
    "skip to main content",
    "parents & family community",
    "students faculty & staff alumni",
    "admissions academics research campus life",
)


def _title_signature(value: str) -> str:
    """Comparison key for titles that ignores personal-pronoun suffixes."""
    text = PRONOUN_SUFFIX_RE.sub("", str(value or "")).strip()
    return " ".join(text.split()).casefold()


def _research_nav_only(value: str) -> int:
    """1 when a research-interests value is mostly website navigation chrome.

    University profile pages sometimes flatten campus navigation ("Campus
    Directory ...", "MyUCSC ... A-Z Index ...") into the research text. Two
    nav-only scrapes can differ solely because the site banner changed; that is
    not a material change and must not invalidate an existing embedding.
    """
    text = " ".join(str(value or "").split()).casefold()
    count = sum(marker in text for marker in NAV_CHROME_MARKERS)
    return 1 if count >= 3 else 0


def _clean_research_interests(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text or text == NOT_AVAILABLE:
        return NOT_AVAILABLE
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", " ", text)
    text = re.split(
        r"\s+(?:Campus\s+Email|Email|E-mail|Phone|Telephone|Office|Contact|Website|Personal Website|Lab Website)\s*[:\-]?\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.sub(r"\s+", " ", text).strip(" |–—-,:;")
    if len(text) > 1200:
        text = text[:1200].rsplit(" ", 1)[0].strip(" |–—-,:;")
    return text if len(text) >= 3 else NOT_AVAILABLE


def _clean_name(value: str) -> str:
    name = " ".join(str(value).split()).strip()
    # Some SJSU cards expose image-alt labels as part of the anchor text.
    # Remove only clear image-description suffixes, never ordinary surnames.
    name = re.sub(
        r"(?:['’]s\s+)?(?:image|photo|thumbnail)$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip(" |–—-,:;")
    if name.casefold() in BLOCKED_NON_PERSON_NAMES:
        return ""
    return name


def _clean_website_url(value: str) -> str:
    url = str(value).strip()
    if not url or url == NOT_AVAILABLE:
        return NOT_AVAILABLE
    try:
        parsed = urlparse(url)
    except ValueError:
        return NOT_AVAILABLE
    if parsed.scheme not in {"http", "https"}:
        return NOT_AVAILABLE
    host = parsed.netloc.lower().split(":")[0]
    if host in BLOCKED_WEBSITE_DOMAINS or any(
        host.endswith(f".{blocked}") for blocked in BLOCKED_WEBSITE_DOMAINS
    ):
        return NOT_AVAILABLE
    path = parsed.path.lower().rstrip("/")
    if any(fragment in path for fragment in GENERIC_WEBSITE_PATH_FRAGMENTS):
        return NOT_AVAILABLE
    return url


def _clean_profile_url(value: str, university: str) -> str:
    url = str(value).strip()
    if not url or url == NOT_AVAILABLE:
        return NOT_AVAILABLE
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if university == "San Jose State University" and parsed.netloc.lower().endswith("sjsu.edu"):
        path = re.sub(r"/index\.html?$", "/", parsed.path, flags=re.IGNORECASE)
        if path.lower().startswith("/people/") and not path.endswith("/"):
            path += "/"
        return parsed._replace(path=path, params="", query="", fragment="").geturl()
    return url


def _clean_legacy_malformed_titles(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, title FROM professors WHERE title LIKE '%@%' OR title GLOB '*([0-9][0-9][0-9])*'"
    ).fetchall()
    updates = [(_clean_title(str(row["title"])), int(row["id"])) for row in rows]
    if updates:
        connection.executemany("UPDATE professors SET title = ? WHERE id = ?", updates)


def _clean_existing_data_quality_issues(connection: sqlite3.Connection) -> None:
    """Apply conservative fixes to records saved by older scraper versions.

    Contact and URL-only repairs preserve the already-paid AI summary and
    embedding. Only a title correction changes the semantic search document and
    therefore invalidates AI fields.
    """

    placeholders = tuple(BLOCKED_NON_PERSON_NAMES)
    connection.executemany(
        "DELETE FROM professors WHERE lower(trim(name)) = ?",
        [(name,) for name in placeholders],
    )

    rows = connection.execute(
        "SELECT id, name, university, title, website_url, profile_url, email FROM professors"
    ).fetchall()
    updates: list[tuple[str, str, str, str, str, int]] = []
    semantic_ids: list[tuple[int]] = []
    for row in rows:
        professor_id = int(row["id"])
        university = str(row["university"])
        original_title = str(row["title"])
        clean_name = _clean_name(str(row["name"]))
        clean_title = _clean_title(original_title)
        clean_website = _clean_website_url(str(row["website_url"]))
        clean_profile = _clean_profile_url(str(row["profile_url"]), university)
        clean_email = _clean_email(str(row["email"]))

        fix = KNOWN_RECORD_FIXES.get((university, clean_name), {})
        clean_title = fix.get("title", clean_title)
        clean_website = fix.get("website_url", clean_website)
        clean_profile = fix.get("profile_url", clean_profile)
        clean_email = fix.get("email", clean_email)

        if (
            clean_name != str(row["name"])
            or clean_title != original_title
            or clean_website != str(row["website_url"])
            or clean_profile != str(row["profile_url"])
            or clean_email != str(row["email"])
        ):
            updates.append(
                (
                    clean_name,
                    clean_title,
                    clean_website,
                    clean_profile,
                    clean_email,
                    professor_id,
                )
            )
            # Only a material title change alters the semantic search document.
            # Pronoun-suffix or whitespace-only corrections (e.g. KNOWN_RECORD_FIXES
            # collapsing "Associate Professor She/Her/Hers" to "Associate Professor")
            # must not invalidate an existing embedding.
            if _title_signature(clean_title) != _title_signature(original_title):
                semantic_ids.append((professor_id,))

    if updates:
        connection.executemany(
            """
            UPDATE professors
            SET name = ?, title = ?, website_url = ?, profile_url = ?, email = ?,
                verification_status = 'Not checked',
                verification_issues = 'Record repaired; re-run verification audit',
                verified_at = 'Not publicly available',
                website_status = CASE WHEN website_url <> ? THEN 'Not checked' ELSE website_status END,
                website_issue = CASE WHEN website_url <> ?
                    THEN 'Website repaired; run targeted link check' ELSE website_issue END,
                website_checked_at = CASE WHEN website_url <> ?
                    THEN 'Not publicly available' ELSE website_checked_at END,
                website_final_url = CASE WHEN website_url <> ?
                    THEN 'Not publicly available' ELSE website_final_url END
            WHERE id = ?
            """,
            [
                (name, title, website, profile, email, website, website, website, website, professor_id)
                for name, title, website, profile, email, professor_id in updates
            ],
        )
    if semantic_ids:
        connection.executemany(
            """
            UPDATE professors
            SET ai_categories = '', ai_summary = '', embedding_json = '',
                embedding_model = '', embedding_source_hash = '',
                ai_enriched_at = 'Not publicly available'
            WHERE id = ?
            """,
            semantic_ids,
        )


MIGRATION_COLUMNS: dict[str, str] = {
    "university_slug": "TEXT NOT NULL DEFAULT ''",
    "city": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "state": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "department_category": "TEXT NOT NULL DEFAULT 'Other Research Area'",
    "data_source_url": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "last_checked_at": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "opportunity_level": "TEXT NOT NULL DEFAULT 'Basic'",
    "opportunity_signals": (
        "TEXT NOT NULL DEFAULT 'No explicit opportunity information found'"
    ),
    "opportunity_source_url": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "website_status": "TEXT NOT NULL DEFAULT 'Not checked'",
    "website_issue": "TEXT NOT NULL DEFAULT 'Not checked'",
    "website_checked_at": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "website_final_url": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "verification_status": "TEXT NOT NULL DEFAULT 'Not checked'",
    "verification_issues": "TEXT NOT NULL DEFAULT 'Not checked'",
    "verified_at": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "ai_categories": "TEXT NOT NULL DEFAULT ''",
    "ai_summary": "TEXT NOT NULL DEFAULT ''",
    "embedding_json": "TEXT NOT NULL DEFAULT ''",
    "embedding_model": "TEXT NOT NULL DEFAULT ''",
    "embedding_source_hash": "TEXT NOT NULL DEFAULT ''",
    "ai_enriched_at": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "school_or_college": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "discipline": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "field": "TEXT NOT NULL DEFAULT 'Not publicly available'",
    "subfield": "TEXT NOT NULL DEFAULT 'Not publicly available'",
}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.create_function("title_signature", 1, _title_signature)
    connection.create_function("research_nav_only", 1, _research_nav_only)
    return connection


def _ensure_migration_columns(connection: sqlite3.Connection) -> list[str]:
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(professors)").fetchall()
    }
    added: list[str] = []
    for column, declaration in MIGRATION_COLUMNS.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE professors ADD COLUMN {column} {declaration}")
            added.append(column)
    return added


def _backfill_expansion_metadata(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, university, department, research_interests, profile_url, "
        "university_slug, city, state, department_category, data_source_url, last_checked_at "
        "FROM professors"
    ).fetchall()
    updates = []
    for row in rows:
        metadata = metadata_for(str(row["university"]))
        department_category = infer_department_category(
            str(row["department"]), str(row["research_interests"])
        )
        data_source_url = str(row["data_source_url"] or "").strip()
        if not data_source_url or data_source_url == NOT_AVAILABLE:
            data_source_url = str(row["profile_url"] or NOT_AVAILABLE)
        last_checked_at = str(row["last_checked_at"] or "").strip()
        if not last_checked_at or last_checked_at == NOT_AVAILABLE:
            last_checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        desired = (
            metadata.slug,
            metadata.city,
            metadata.state,
            department_category,
            data_source_url,
            last_checked_at,
            int(row["id"]),
        )
        current = (
            str(row["university_slug"]),
            str(row["city"]),
            str(row["state"]),
            str(row["department_category"]),
            str(row["data_source_url"]),
            str(row["last_checked_at"]),
            int(row["id"]),
        )
        if desired != current:
            updates.append(desired)
    if updates:
        connection.executemany(
            """
            UPDATE professors
            SET university_slug = ?, city = ?, state = ?, department_category = ?,
                data_source_url = ?, last_checked_at = ?
            WHERE id = ?
            """,
            updates,
        )


def _backfill_taxonomy_metadata(connection: sqlite3.Connection) -> None:
    """Fill school/discipline/field/subfield once from existing public data.

    Only ever writes these four columns — never embedding, verification, or
    audit fields — so it is safe to run against migrated databases. New rows
    written by later refreshes are covered the next time maintenance runs.
    """
    rows = connection.execute(
        "SELECT id, university, department, categories, ai_categories, "
        "school_or_college, discipline, field, subfield FROM professors"
    ).fetchall()
    updates = []
    for row in rows:
        desired = infer_taxonomy(
            university=str(row["university"]),
            department=str(row["department"]),
            categories=str(row["categories"]),
            ai_categories=str(row["ai_categories"]),
        )
        current = (
            str(row["school_or_college"]),
            str(row["discipline"]),
            str(row["field"]),
            str(row["subfield"]),
        )
        if desired != current:
            updates.append((*desired, int(row["id"])))
    if updates:
        connection.executemany(
            """
            UPDATE professors
            SET school_or_college = ?, discipline = ?, field = ?, subfield = ?
            WHERE id = ?
            """,
            updates,
        )


DATA_REVISION_KEY = "professors_data_revision"
DATA_MAINTENANCE_KEY = "professors_data_maintenance"


def _data_revision(connection: sqlite3.Connection) -> int:
    """Current professor-data write revision (0 when no writes are recorded)."""
    try:
        row = connection.execute(
            "SELECT details FROM app_migrations WHERE migration_key = ?",
            (DATA_REVISION_KEY,),
        ).fetchone()
        return int(row["details"]) if row else 0
    except (TypeError, ValueError):
        return 0


def _bump_data_revision(connection: sqlite3.Connection) -> None:
    """Invalidate derived caches and mark explicit maintenance as pending."""
    connection.execute(
        """
        INSERT INTO app_migrations (migration_key, applied_at, details)
        VALUES (?, CURRENT_TIMESTAMP, '1')
        ON CONFLICT(migration_key) DO UPDATE SET
            applied_at = CURRENT_TIMESTAMP,
            details = CAST(CAST(details AS INTEGER) + 1 AS TEXT)
        """,
        (DATA_REVISION_KEY,),
    )


def _processed_maintenance_revision(connection: sqlite3.Connection) -> int:
    """Revision that the full maintenance passes already ran against (-1 = none)."""
    try:
        row = connection.execute(
            "SELECT details FROM app_migrations WHERE migration_key = ?",
            (DATA_MAINTENANCE_KEY,),
        ).fetchone()
        return int(row["details"]) if row else -1
    except (TypeError, ValueError):
        return -1


def _run_data_maintenance(connection: sqlite3.Connection) -> None:
    """Run legacy cleanup/backfill only when professors data actually changed.

    These maintenance passes used to run on every database read (~140ms full
    table scan). Rows are already cleaned and backfilled at write time by
    ``upsert_professors``, so the full passes only need to re-run after a real
    professors-table write (bumped by ``_bump_data_revision``) or a fresh
    migration. Outreach/favorite writes and plain reads never trigger it.
    """
    current = _data_revision(connection)
    processed = _processed_maintenance_revision(connection)
    if current <= processed:
        return
    _clean_legacy_malformed_titles(connection)
    _clean_existing_data_quality_issues(connection)
    _backfill_expansion_metadata(connection)
    _backfill_taxonomy_metadata(connection)
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, ?) "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
        (DATA_MAINTENANCE_KEY, str(current)),
    )


OUTREACH_USER_MIGRATION_KEY = "v9.6-outreach-user-scoping"

OUTREACH_DRAFT_MIGRATION_KEY = "v9.7-outreach-draft-columns"

OUTREACH_DRAFT_COLUMNS = (
    ("email_to", "TEXT NOT NULL DEFAULT ''"),
    ("email_subject", "TEXT NOT NULL DEFAULT ''"),
    ("email_body", "TEXT NOT NULL DEFAULT ''"),
)

GMAIL_MIGRATION_KEY = "v9.8-gmail-draft-metadata"

GMAIL_COLUMNS = (
    ("gmail_draft_id", "TEXT NOT NULL DEFAULT ''"),
    ("gmail_thread_id", "TEXT NOT NULL DEFAULT ''"),
    ("gmail_account_email", "TEXT NOT NULL DEFAULT ''"),
    ("gmail_draft_created_at", "TEXT NOT NULL DEFAULT ''"),
)

THREAD_METADATA_MIGRATION_KEY = "v9.10-gmail-thread-metadata"

THREAD_METADATA_COLUMNS = (
    ("gmail_sent_at", "TEXT NOT NULL DEFAULT ''"),
    ("gmail_replied_at", "TEXT NOT NULL DEFAULT ''"),
    ("gmail_reply_count", "INTEGER NOT NULL DEFAULT 0"),
    ("gmail_last_checked_at", "TEXT NOT NULL DEFAULT ''"),
)

PHASE6_AUTH_MIGRATION_KEY = "v9.9-auth-users-sessions-profiles"

LOCAL_OWNER_IMPORT_MIGRATION_KEY = "v9.9-local-owner-import"

LOCAL_OWNER_IMPORTED_KEY = "v9.9-local-owner-imported"

TITLE_CLEANING_MIGRATION_KEY = "v9.11-title-directory-noise"
TITLE_CONNECTOR_MIGRATION_KEY = "v9.12-title-connector-repeats"


def _ensure_title_cleaning_pass(connection: sqlite3.Connection) -> None:
    """Schedule one repair pass so stored titles are cleaned with current rules.

    ``_run_data_maintenance`` is gated on the professors data revision, which only
    advances when rows are written. Tightening ``_clean_title`` therefore would
    never reach already-stored rows, so bump the revision once to replay it.
    """
    row = connection.execute(
        "SELECT 1 FROM app_migrations WHERE migration_key = ?",
        (TITLE_CLEANING_MIGRATION_KEY,),
    ).fetchone()
    if row:
        return
    _bump_data_revision(connection)
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, 'applied')",
        (TITLE_CLEANING_MIGRATION_KEY,),
    )


def _ensure_title_connector_pass(connection: sqlite3.Connection) -> None:
    """Replay stored-title maintenance for connector-separated repeats.

    Same one-shot revision bump as ``_ensure_title_cleaning_pass``. It exists so
    the tightened ``_clean_title`` reaches the rows already in the database
    rather than only freshly scraped ones.
    """
    row = connection.execute(
        "SELECT 1 FROM app_migrations WHERE migration_key = ?",
        (TITLE_CONNECTOR_MIGRATION_KEY,),
    ).fetchone()
    if row:
        return
    _bump_data_revision(connection)
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, 'applied')",
        (TITLE_CONNECTOR_MIGRATION_KEY,),
    )


def _ensure_outreach_user_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_professor_outreach_user_favorite "
        "ON professor_outreach(user_id, is_favorite)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_professor_outreach_user_status "
        "ON professor_outreach(user_id, outreach_status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_professor_outreach_user_follow_up "
        "ON professor_outreach(user_id, follow_up_date)"
    )


def _migrate_outreach_user_scoping(connection: sqlite3.Connection) -> None:
    """Scope outreach/shortlist rows to a user (default: ``DEFAULT_USER_ID``).

    Rebuilds the table with a composite ``(user_id, professor_id)`` primary key,
    copying every existing row verbatim under the local-owner user so current
    local behavior is preserved. Fresh and legacy databases both end up with the
    new shape plus user-scoped indexes; re-runs are no-ops.
    """
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
    }
    if "user_id" in columns:
        _ensure_outreach_user_indexes(connection)
        return
    marker = connection.execute(
        "SELECT 1 FROM app_migrations WHERE migration_key = ?",
        (OUTREACH_USER_MIGRATION_KEY,),
    ).fetchone()
    connection.execute(
        "CREATE TABLE professor_outreach_v9_6 ("
        " user_id TEXT NOT NULL,"
        " professor_id INTEGER NOT NULL,"
        " is_favorite INTEGER NOT NULL DEFAULT 0 CHECK (is_favorite IN (0, 1)),"
        " notes TEXT NOT NULL DEFAULT '',"
        " outreach_status TEXT NOT NULL DEFAULT 'Not contacted',"
        " email_sent_at TEXT NOT NULL DEFAULT '',"
        " follow_up_date TEXT NOT NULL DEFAULT '',"
        " email_to TEXT NOT NULL DEFAULT '',"
        " email_subject TEXT NOT NULL DEFAULT '',"
        " email_body TEXT NOT NULL DEFAULT '',"
        " gmail_draft_id TEXT NOT NULL DEFAULT '',"
        " gmail_thread_id TEXT NOT NULL DEFAULT '',"
        " gmail_account_email TEXT NOT NULL DEFAULT '',"
        " gmail_draft_created_at TEXT NOT NULL DEFAULT '',"
        " gmail_sent_at TEXT NOT NULL DEFAULT '',"
        " gmail_replied_at TEXT NOT NULL DEFAULT '',"
        " gmail_reply_count INTEGER NOT NULL DEFAULT 0,"
        " gmail_last_checked_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (user_id, professor_id),"
        " FOREIGN KEY (professor_id) REFERENCES professors(id) ON DELETE CASCADE"
        ")"
    )
    connection.execute(
        "INSERT INTO professor_outreach_v9_6 ("
        " user_id, professor_id, is_favorite, notes, outreach_status,"
        " email_sent_at, follow_up_date, updated_at"
        ") SELECT ?, professor_id, is_favorite, notes, outreach_status,"
        " email_sent_at, follow_up_date, updated_at FROM professor_outreach",
        (DEFAULT_USER_ID,),
    )
    connection.execute("DROP TABLE professor_outreach")
    connection.execute("ALTER TABLE professor_outreach_v9_6 RENAME TO professor_outreach")
    _ensure_outreach_user_indexes(connection)
    if marker is None:
        connection.execute(
            "INSERT INTO app_migrations (migration_key, applied_at, details) "
            "VALUES (?, CURRENT_TIMESTAMP, 'outreach rows scoped to user_id')",
            (OUTREACH_USER_MIGRATION_KEY,),
        )


def _ensure_outreach_draft_columns(connection: sqlite3.Connection) -> list[str]:
    """Add the email draft columns to ``professor_outreach`` (additive, safe).

    Fresh and v9.6 databases already carry the columns via their table DDL, so
    this is a no-op for them. Older single-owner databases get the columns added
    with a backup of the database file first, a baseline row count, and a
    professors-table integrity assertion so existing outreach history is always
    preserved.
    """
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
    }
    missing = [column for column, _ in OUTREACH_DRAFT_COLUMNS if column not in existing]
    if not missing:
        return []
    if DB_PATH.is_file() and not os.getenv("PROFESSOR_DB_SKIP_BACKUP"):
        backup_name = (
            f"{DB_PATH.stem}-pre-{OUTREACH_DRAFT_MIGRATION_KEY}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.bak"
        )
        shutil.copy2(DB_PATH, DB_PATH.parent / backup_name)
    baseline_rows = int(
        connection.execute("SELECT COUNT(*) FROM professor_outreach").fetchone()[0]
    )
    baseline_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    for column, declaration in OUTREACH_DRAFT_COLUMNS:
        if column not in existing:
            connection.execute(
                f"ALTER TABLE professor_outreach ADD COLUMN {column} {declaration}"
            )
    final_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    if final_professors != baseline_professors:
        raise RuntimeError(
            "Outreach draft migration altered the professors table; refusing to continue."
        )
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, ?) "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
        (
            OUTREACH_DRAFT_MIGRATION_KEY,
            f"outreach draft columns added; baseline rows={baseline_rows}",
        ),
    )
    return missing


def _ensure_gmail_columns(connection: sqlite3.Connection) -> list[str]:
    """Add the Gmail draft-metadata columns (additive, safe, backups first).

    Only ``professor_outreach`` is touched. Fresh and v9.7 databases already
    carry the columns via their table DDL, so this is a no-op for them. Older
    databases get a timestamped backup, a baseline outreach row count, and a
    professors-table integrity assertion so existing outreach history survives
    and professor data is never altered by a Gmail feature migration.
    """
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
    }
    missing = [column for column, _ in GMAIL_COLUMNS if column not in existing]
    if not missing:
        return []
    if DB_PATH.is_file() and not os.getenv("PROFESSOR_DB_SKIP_BACKUP"):
        backup_name = (
            f"{DB_PATH.stem}-pre-{GMAIL_MIGRATION_KEY}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.bak"
        )
        shutil.copy2(DB_PATH, DB_PATH.parent / backup_name)
    baseline_rows = int(
        connection.execute("SELECT COUNT(*) FROM professor_outreach").fetchone()[0]
    )
    baseline_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    for column, declaration in GMAIL_COLUMNS:
        if column not in existing:
            connection.execute(
                f"ALTER TABLE professor_outreach ADD COLUMN {column} {declaration}"
            )
    final_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    if final_professors != baseline_professors:
        raise RuntimeError(
            "Gmail metadata migration altered the professors table; refusing to continue."
        )
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, ?) "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
        (
            GMAIL_MIGRATION_KEY,
            f"gmail draft-metadata columns added; baseline rows={baseline_rows}",
        ),
    )
    return missing


def _ensure_thread_metadata_columns(connection: sqlite3.Connection) -> list[str]:
    """Add the Gmail thread-metadata columns (additive, safe, backups first).

    Only ``professor_outreach`` is touched. Fresh and rebuilt tables already carry
    the columns via their DDL, so this is a no-op for them. Older databases get a
    timestamped backup, a baseline outreach row count, and a professors-table
    integrity assertion so existing outreach history survives and professor data is
    never altered by a reply-detection migration.
    """
    existing = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(professor_outreach)").fetchall()
    }
    missing = [
        column for column, _ in THREAD_METADATA_COLUMNS if column not in existing
    ]
    if not missing:
        return []
    if DB_PATH.is_file() and not os.getenv("PROFESSOR_DB_SKIP_BACKUP"):
        backup_name = (
            f"{DB_PATH.stem}-pre-{THREAD_METADATA_MIGRATION_KEY}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.bak"
        )
        shutil.copy2(DB_PATH, DB_PATH.parent / backup_name)
    baseline_rows = int(
        connection.execute("SELECT COUNT(*) FROM professor_outreach").fetchone()[0]
    )
    baseline_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    for column, declaration in THREAD_METADATA_COLUMNS:
        if column not in existing:
            connection.execute(
                f"ALTER TABLE professor_outreach ADD COLUMN {column} {declaration}"
            )
    final_professors = int(
        connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
    )
    if final_professors != baseline_professors:
        raise RuntimeError(
            "Thread metadata migration altered the professors table; refusing to continue."
        )
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, ?) "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
        (
            THREAD_METADATA_MIGRATION_KEY,
            f"gmail thread-metadata columns added; baseline rows={baseline_rows}",
        ),
    )
    return missing


def _record_phase6_migration(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO app_migrations (migration_key, applied_at, details) "
        "VALUES (?, CURRENT_TIMESTAMP, 'users, sessions, and student_profiles tables ensured') "
        "ON CONFLICT(migration_key) DO UPDATE SET "
        "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
        (PHASE6_AUTH_MIGRATION_KEY,),
    )


_INITIALIZATION_LOCK = RLock()
_INITIALIZED_FILES: set[tuple[str, int, int]] = set()


def _database_identity() -> tuple[str, int, int]:
    info = DB_PATH.stat()
    return (str(DB_PATH.resolve()), info.st_dev, info.st_ino)


def ensure_database_initialized() -> None:
    """Ensure schema once per database file, without repairing researcher data."""
    with _INITIALIZATION_LOCK:
        if DB_PATH.is_file() and _database_identity() in _INITIALIZED_FILES:
            return
        initialize_database(run_maintenance=False)


def initialize_database(*, run_maintenance: bool = True) -> None:
    """Explicit setup/maintenance boundary; ordinary reads only ensure schema.

    Data repairs may invalidate verification and embeddings. They run only when
    this function is explicitly invoked with maintenance enabled, never from a
    read helper. Schema migrations still run when opening an uninitialized DB.
    """
    with connect() as connection:
        connection.executescript(SCHEMA)
        added_columns = _ensure_migration_columns(connection)
        _migrate_outreach_user_scoping(connection)
        draft_columns = _ensure_outreach_draft_columns(connection)
        gmail_columns = _ensure_gmail_columns(connection)
        thread_columns = _ensure_thread_metadata_columns(connection)
        if added_columns or draft_columns or gmail_columns or thread_columns:
            _bump_data_revision(connection)
        if run_maintenance:
            _ensure_title_cleaning_pass(connection)
            _ensure_title_connector_pass(connection)
        connection.executescript(V8_INDEXES)
        _record_phase6_migration(connection)
        if run_maintenance:
            _run_data_maintenance(connection)
    _INITIALIZED_FILES.add(_database_identity())


_STATS_REVISION_CACHE: dict[tuple[str, int, str], object] = {}


def _revision_memoized(name: str, compute) -> object:
    """Compute a professors-derived statistic once per (DB file, revision).

    Values only depend on professors-table contents, so they stay valid across
    favorite/outreach writes. Any professors-table writer bumps the revision via
    ``_bump_data_revision``, which invalidates the cache and triggers a recompute.
    Mutable cached values are shallow-copied before being handed out so callers
    can never corrupt the shared cache.
    """
    ensure_database_initialized()
    with connect() as connection:
        cache_key = (str(DB_PATH), _data_revision(connection), name)
        cached = _STATS_REVISION_CACHE.get(cache_key)
        if cached is not None:
            if isinstance(cached, dict):
                return dict(cached)
            return list(cached) if isinstance(cached, list) else cached
        result = compute(connection)
    _STATS_REVISION_CACHE[cache_key] = result
    if isinstance(result, dict):
        return dict(result)
    return list(result) if isinstance(result, list) else result


def professor_count() -> int:
    def compute(connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COUNT(*) AS total FROM professors").fetchone()
        return int(row["total"])

    return int(_revision_memoized("professor_count", compute))


def upsert_professors(records: Iterable[Mapping[str, str]]) -> int:
    """Insert or update scraped records while retaining valid AI and audit data.

    Semantic data is invalidated only when research-ranking fields change.
    Contact or website-only changes still reset verification, but preserve the
    professor's AI summary and embedding. Rechecking an unchanged page updates
    ``last_checked_at`` without forcing another audit or indexing run.
    """

    ensure_database_initialized()
    semantic_change_condition = """
        professors.department <> excluded.department
        OR title_signature(professors.title) <> title_signature(excluded.title)
        OR (professors.research_interests <> excluded.research_interests
            AND NOT (research_nav_only(professors.research_interests) = 1
                     AND research_nav_only(excluded.research_interests) = 1))
        OR (professors.categories <> excluded.categories
            AND NOT (research_nav_only(professors.research_interests) = 1
                     AND research_nav_only(excluded.research_interests) = 1))
    """
    verification_change_condition = """
        professors.name <> excluded.name
        OR professors.department <> excluded.department
        OR professors.title <> excluded.title
        OR professors.research_interests <> excluded.research_interests
        OR professors.email <> excluded.email
        OR professors.website_url <> excluded.website_url
        OR professors.profile_url <> excluded.profile_url
        OR professors.categories <> excluded.categories
        OR professors.opportunity_level <> excluded.opportunity_level
        OR professors.opportunity_signals <> excluded.opportunity_signals
        OR professors.opportunity_source_url <> excluded.opportunity_source_url
    """
    sql = f"""
    INSERT INTO professors (
        name, university, university_slug, city, state,
        department, department_category, title, research_interests,
        email, website_url, website_status, website_issue, website_checked_at, website_final_url,
        profile_url, data_source_url, categories,
        opportunity_level, opportunity_signals, opportunity_source_url,
        source_type, last_checked_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT DO UPDATE SET
        ai_categories = CASE WHEN {semantic_change_condition} THEN '' ELSE professors.ai_categories END,
        ai_summary = CASE WHEN {semantic_change_condition} THEN '' ELSE professors.ai_summary END,
        embedding_json = CASE WHEN {semantic_change_condition} THEN '' ELSE professors.embedding_json END,
        embedding_model = CASE WHEN {semantic_change_condition} THEN '' ELSE professors.embedding_model END,
        embedding_source_hash = CASE WHEN {semantic_change_condition} THEN '' ELSE professors.embedding_source_hash END,
        ai_enriched_at = CASE WHEN {semantic_change_condition}
            THEN 'Not publicly available' ELSE professors.ai_enriched_at END,
        name = excluded.name,
        university = excluded.university,
        university_slug = excluded.university_slug,
        city = excluded.city,
        state = excluded.state,
        department = excluded.department,
        department_category = excluded.department_category,
        title = excluded.title,
        research_interests = excluded.research_interests,
        email = excluded.email,
        website_url = excluded.website_url,
        website_status = CASE WHEN professors.website_url <> excluded.website_url
            THEN 'Not checked' ELSE professors.website_status END,
        website_issue = CASE WHEN professors.website_url <> excluded.website_url
            THEN 'Website changed; run targeted link check' ELSE professors.website_issue END,
        website_checked_at = CASE WHEN professors.website_url <> excluded.website_url
            THEN 'Not publicly available' ELSE professors.website_checked_at END,
        website_final_url = CASE WHEN professors.website_url <> excluded.website_url
            THEN 'Not publicly available' ELSE professors.website_final_url END,
        profile_url = excluded.profile_url,
        data_source_url = excluded.data_source_url,
        categories = excluded.categories,
        opportunity_level = excluded.opportunity_level,
        opportunity_signals = excluded.opportunity_signals,
        opportunity_source_url = excluded.opportunity_source_url,
        source_type = excluded.source_type,
        verification_status = CASE WHEN {verification_change_condition}
            THEN 'Not checked' ELSE professors.verification_status END,
        verification_issues = CASE WHEN {verification_change_condition}
            THEN 'Record changed; re-run verification audit' ELSE professors.verification_issues END,
        verified_at = CASE WHEN {verification_change_condition}
            THEN 'Not publicly available' ELSE professors.verified_at END,
        last_checked_at = CURRENT_TIMESTAMP,
        updated_at = CASE WHEN {verification_change_condition} THEN CURRENT_TIMESTAMP ELSE professors.updated_at END
    """

    normalized = []
    for record in records:
        email = _clean_email(str(record.get("email", "")))
        name = _clean_name(str(record.get("name", NOT_AVAILABLE)))
        university = str(record.get("university", NOT_AVAILABLE)).strip()
        if not email or not name:
            continue
        metadata = metadata_for(university)
        department = str(record.get("department", NOT_AVAILABLE)).strip()
        research_interests = _clean_research_interests(
            str(record.get("research_interests", NOT_AVAILABLE))
        )
        profile_url = _clean_profile_url(
            str(record.get("profile_url", NOT_AVAILABLE)).strip(), university
        )
        normalized.append(
            (
                name,
                university,
                str(record.get("university_slug", metadata.slug)).strip() or metadata.slug,
                str(record.get("city", metadata.city)).strip() or metadata.city,
                str(record.get("state", metadata.state)).strip() or metadata.state,
                department,
                str(
                    record.get(
                        "department_category",
                        infer_department_category(department, research_interests),
                    )
                ).strip(),
                _clean_title(str(record.get("title", NOT_AVAILABLE))),
                research_interests,
                email,
                _clean_website_url(str(record.get("website_url", NOT_AVAILABLE))),
                str(record.get("website_status", "Not checked")).strip() or "Not checked",
                str(record.get("website_issue", "Not checked")).strip() or "Not checked",
                str(record.get("website_checked_at", NOT_AVAILABLE)).strip() or NOT_AVAILABLE,
                str(record.get("website_final_url", NOT_AVAILABLE)).strip() or NOT_AVAILABLE,
                profile_url,
                str(record.get("data_source_url", profile_url)).strip() or profile_url,
                str(record.get("categories", "")).strip(),
                str(record.get("opportunity_level", "Basic")).strip() or "Basic",
                str(
                    record.get(
                        "opportunity_signals",
                        "No explicit opportunity information found",
                    )
                ).strip(),
                str(record.get("opportunity_source_url", NOT_AVAILABLE)).strip(),
                str(record.get("source_type", "University website")).strip(),
            )
        )

    if not normalized:
        return 0

    with connect() as connection:
        connection.executemany(sql, normalized)
        _bump_data_revision(connection)
        _backfill_expansion_metadata(connection)
        _backfill_taxonomy_metadata(connection)
    return len(normalized)



def prune_university_records(university: str, keep_emails: Iterable[str]) -> int:
    """Delete stale rows only after a complete authoritative roster succeeds."""
    ensure_database_initialized()
    normalized = sorted({_clean_email(value) for value in keep_emails if _clean_email(value)})
    if not normalized:
        return 0
    placeholders = ",".join("?" for _ in normalized)
    with connect() as connection:
        before = int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM professors WHERE university = ?",
                (university,),
            ).fetchone()["total"]
        )
        connection.execute(
            f"DELETE FROM professors WHERE university = ? AND lower(email) NOT IN ({placeholders})",
            (university, *normalized),
        )
        _bump_data_revision(connection)
        after = int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM professors WHERE university = ?",
                (university,),
            ).fetchone()["total"]
        )
    return max(0, before - after)


def migration_applied(migration_key: str) -> bool:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute(
            "SELECT 1 FROM app_migrations WHERE migration_key = ?",
            (migration_key,),
        ).fetchone()
    return row is not None


def mark_migration_applied(migration_key: str, details: str = "") -> None:
    ensure_database_initialized()
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_migrations (migration_key, applied_at, details) "
            "VALUES (?, CURRENT_TIMESTAMP, ?)",
            (migration_key, details),
        )


def clear_query_embedding_cache() -> int:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM query_embedding_cache").fetchone()
        connection.execute("DELETE FROM query_embedding_cache")
    return int(row["total"])


def update_website_link_results(results: Iterable[Mapping[str, str | int]]) -> int:
    """Persist targeted personal/lab website checks without invalidating AI data."""
    ensure_database_initialized()
    rows = []
    for result in results:
        professor_id = int(result.get("professor_id", 0))
        if professor_id <= 0:
            continue
        rows.append((
            str(result.get("status", "Not checked")),
            str(result.get("issue", "Not checked")),
            str(result.get("checked_at", NOT_AVAILABLE)),
            str(result.get("final_url", NOT_AVAILABLE)),
            professor_id,
        ))
    if not rows:
        return 0
    with connect() as connection:
        connection.executemany(
            """
            UPDATE professors
            SET website_status = ?, website_issue = ?, website_checked_at = ?,
                website_final_url = ?
            WHERE id = ?
            """,
            rows,
        )
        _bump_data_revision(connection)
    return len(rows)


def website_link_counts() -> dict[str, int]:
    ensure_database_initialized()
    with connect() as connection:
        rows = connection.execute(
            "SELECT website_status, COUNT(*) AS total FROM professors "
            "WHERE website_url <> ? GROUP BY website_status",
            (NOT_AVAILABLE,),
        ).fetchall()
    return {str(row["website_status"]): int(row["total"]) for row in rows}



def update_ai_enrichment(records: Iterable[Mapping[str, str | int]]) -> int:
    """Persist AI labels, summaries, and embeddings by professor ID."""

    ensure_database_initialized()
    rows = []
    for record in records:
        professor_id = int(record.get("id", 0))
        if professor_id <= 0:
            continue
        rows.append(
            (
                str(record.get("ai_categories", "")).strip(),
                str(record.get("ai_summary", "")).strip(),
                str(record.get("embedding_json", "")).strip(),
                str(record.get("embedding_model", "")).strip(),
                str(record.get("embedding_source_hash", "")).strip(),
                str(record.get("ai_enriched_at", NOT_AVAILABLE)).strip(),
                professor_id,
            )
        )
    if not rows:
        return 0

    with connect() as connection:
        connection.executemany(
            """
            UPDATE professors
            SET ai_categories = ?,
                ai_summary = ?,
                embedding_json = ?,
                embedding_model = ?,
                embedding_source_hash = ?,
                ai_enriched_at = ?
            WHERE id = ?
            """,
            rows,
        )
        _bump_data_revision(connection)
    return len(rows)


def ai_index_counts() -> dict[str, int]:
    def compute(connection: sqlite3.Connection) -> dict[str, int]:
        # embedding_model is always cleared/set together with embedding_json, so it
        # is an exact proxy that avoids scanning the large embedding blobs.
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN embedding_model <> '' THEN 1 ELSE 0 END) AS indexed,
                SUM(CASE WHEN embedding_model = '' THEN 1 ELSE 0 END) AS missing,
                SUM(CASE WHEN ai_summary <> '' THEN 1 ELSE 0 END) AS summarized
            FROM professors
            WHERE source_type <> 'Demo record'
            """
        ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "indexed": int(row["indexed"] or 0),
            "missing": int(row["missing"] or 0),
            "summarized": int(row["summarized"] or 0),
        }

    return dict(_revision_memoized("ai_index_counts", compute))


def delete_demo_records() -> int:
    """Remove fictional starter records after a live import succeeds."""
    ensure_database_initialized()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM professors WHERE source_type = ?",
            ("Demo record",),
        )
        _bump_data_revision(connection)
    return int(cursor.rowcount)


def source_counts() -> dict[str, int]:
    def compute(connection: sqlite3.Connection) -> dict[str, int]:
        rows = connection.execute(
            "SELECT source_type, COUNT(*) AS total FROM professors GROUP BY source_type"
        ).fetchall()
        return {str(row["source_type"]): int(row["total"]) for row in rows}

    return dict(_revision_memoized("source_counts", compute))


def fetch_professors(
    university: str | None = None, *, omit_embeddings: bool = False
) -> list[dict[str, str]]:
    ensure_database_initialized()
    with connect() as connection:
        columns = "*"
        if omit_embeddings:
            columns = ", ".join(
                f'"{str(raw["name"])}"'
                for raw in connection.execute("PRAGMA table_info(professors)").fetchall()
                if str(raw["name"]) != "embedding_json"
            )
        query = f"SELECT {columns} FROM professors"
        params: tuple[str, ...] = ()
        if university and university != "All supported universities":
            query += " WHERE university = ?"
            params = (university,)
        query += " ORDER BY university, name"
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _normalize_optional_date(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD.") from exc
    return normalized


def get_professor_outreach(
    professor_ids: Iterable[int] | None = None,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> dict[int, dict[str, str | int]]:
    """Return persistent shortlist and outreach metadata keyed by professor ID."""
    ensure_database_initialized()
    ids: list[int] = []
    if professor_ids is not None:
        for value in professor_ids:
            try:
                professor_id = int(value)
            except (TypeError, ValueError):
                continue
            if professor_id > 0:
                ids.append(professor_id)
        ids = sorted(set(ids))
    query = "SELECT * FROM professor_outreach WHERE user_id = ?"
    params: list[str | int] = [str(user_id)]
    if professor_ids is not None:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        query += f" AND professor_id IN ({placeholders})"
        params.extend(ids)
    with connect() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return {int(row["professor_id"]): dict(row) for row in rows}


def favorite_professor_ids(*, user_id: str = DEFAULT_USER_ID) -> set[int]:
    ensure_database_initialized()
    with connect() as connection:
        rows = connection.execute(
            "SELECT professor_id FROM professor_outreach "
            "WHERE user_id = ? AND is_favorite = 1",
            (str(user_id),),
        ).fetchall()
    return {int(row["professor_id"]) for row in rows}


def set_professor_favorite(
    professor_id: int, is_favorite: bool, *, user_id: str = DEFAULT_USER_ID
) -> None:
    ensure_database_initialized()
    professor_id = int(professor_id)
    if professor_id <= 0:
        raise ValueError("A valid professor ID is required.")
    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM professors WHERE id = ?", (professor_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("Professor record was not found.")
        connection.execute(
            """
            INSERT INTO professor_outreach (user_id, professor_id, is_favorite, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, professor_id) DO UPDATE SET
                is_favorite = excluded.is_favorite,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(user_id), professor_id, 1 if is_favorite else 0),
        )


def save_professor_outreach(
    professor_id: int,
    *,
    is_favorite: bool,
    outreach_status: str,
    notes: str = "",
    email_sent_at: str = "",
    follow_up_date: str = "",
    email_to: str = "",
    email_subject: str = "",
    email_body: str = "",
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """Save a professor's private local shortlist and outreach workflow state."""
    ensure_database_initialized()
    professor_id = int(professor_id)
    if professor_id <= 0:
        raise ValueError("A valid professor ID is required.")
    status = str(outreach_status).strip()
    if status not in OUTREACH_STATUSES:
        raise ValueError("Choose a valid outreach status.")
    cleaned_notes = str(notes or "").strip()[:10000]
    sent_date = _normalize_optional_date(email_sent_at, "Email sent date")
    follow_up = _normalize_optional_date(follow_up_date, "Follow-up date")
    recipient = str(email_to or "").strip()[:500]
    subject = str(email_subject or "").strip()[:200]
    body = str(email_body or "").strip()[:10000]

    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM professors WHERE id = ?", (professor_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("Professor record was not found.")
        connection.execute(
            """
            INSERT INTO professor_outreach (
                user_id, professor_id, is_favorite, notes, outreach_status,
                email_sent_at, follow_up_date, email_to, email_subject,
                email_body, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, professor_id) DO UPDATE SET
                is_favorite = excluded.is_favorite,
                notes = excluded.notes,
                outreach_status = excluded.outreach_status,
                email_sent_at = excluded.email_sent_at,
                follow_up_date = excluded.follow_up_date,
                email_to = excluded.email_to,
                email_subject = excluded.email_subject,
                email_body = excluded.email_body,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(user_id),
                professor_id,
                1 if is_favorite else 0,
                cleaned_notes,
                status,
                sent_date,
                follow_up,
                recipient,
                subject,
                body,
            ),
        )


def update_professor_outreach(
    professor_id: int,
    *,
    user_id: str = DEFAULT_USER_ID,
    outreach_status: str | None = None,
    notes: str | None = None,
    email_sent_at: str | None = None,
    follow_up_date: str | None = None,
    email_to: str | None = None,
    email_subject: str | None = None,
    email_body: str | None = None,
    gmail_draft_id: str | None = None,
    gmail_thread_id: str | None = None,
    gmail_account_email: str | None = None,
    gmail_draft_created_at: str | None = None,
    gmail_sent_at: str | None = None,
    gmail_replied_at: str | None = None,
    gmail_reply_count: int | None = None,
    gmail_last_checked_at: str | None = None,
) -> dict[str, str | int]:
    """Update selected outreach fields without touching favorites or other fields.

    Only the explicitly provided fields are written, so saving a draft, updating
    a status, or editing notes can never clobber ``is_favorite`` or any other
    state. A row is created with defaults when the professor has not been tracked
    yet. Returns the resulting outreach row for the user.
    """
    ensure_database_initialized()
    professor_id = int(professor_id)
    if professor_id <= 0:
        raise ValueError("A valid professor ID is required.")
    if outreach_status is not None:
        status = str(outreach_status).strip()
        if status not in OUTREACH_STATUSES:
            raise ValueError("Choose a valid outreach status.")
    else:
        status = None
    fields: dict[str, str] = {}
    if status is not None:
        fields["outreach_status"] = status
    if notes is not None:
        fields["notes"] = str(notes or "").strip()[:10000]
    if email_sent_at is not None:
        fields["email_sent_at"] = _normalize_optional_date(
            email_sent_at, "Email sent date"
        )
    if follow_up_date is not None:
        fields["follow_up_date"] = _normalize_optional_date(
            follow_up_date, "Follow-up date"
        )
    if email_to is not None:
        fields["email_to"] = str(email_to or "").strip()[:500]
    if email_subject is not None:
        fields["email_subject"] = str(email_subject or "").strip()[:200]
    if email_body is not None:
        fields["email_body"] = str(email_body or "").strip()[:10000]
    if gmail_draft_id is not None:
        fields["gmail_draft_id"] = str(gmail_draft_id or "").strip()[:120]
    if gmail_thread_id is not None:
        fields["gmail_thread_id"] = str(gmail_thread_id or "").strip()[:120]
    if gmail_account_email is not None:
        fields["gmail_account_email"] = str(gmail_account_email or "").strip()[:254]
    if gmail_draft_created_at is not None:
        fields["gmail_draft_created_at"] = str(gmail_draft_created_at or "").strip()[:32]
    if gmail_sent_at is not None:
        fields["gmail_sent_at"] = str(gmail_sent_at or "").strip()[:32]
    if gmail_replied_at is not None:
        fields["gmail_replied_at"] = str(gmail_replied_at or "").strip()[:32]
    if gmail_reply_count is not None:
        try:
            count = max(0, int(gmail_reply_count))
        except (TypeError, ValueError):
            count = 0
        fields["gmail_reply_count"] = count
    if gmail_last_checked_at is not None:
        fields["gmail_last_checked_at"] = str(gmail_last_checked_at or "").strip()[:32]

    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM professors WHERE id = ?", (professor_id,)
        ).fetchone()
        if exists is None:
            raise ValueError("Professor record was not found.")
        row = connection.execute(
            "SELECT * FROM professor_outreach WHERE user_id = ? AND professor_id = ?",
            (str(user_id), professor_id),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO professor_outreach (user_id, professor_id) "
                "VALUES (?, ?)",
                (str(user_id), professor_id),
            )
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            connection.execute(
                f"UPDATE professor_outreach SET {assignments}, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE user_id = ? AND professor_id = ?",
                (*fields.values(), str(user_id), professor_id),
            )
        result = connection.execute(
            "SELECT * FROM professor_outreach WHERE user_id = ? AND professor_id = ?",
            (str(user_id), professor_id),
        ).fetchone()
    return dict(result)


def fetch_outreach_professors(
    *,
    favorites_only: bool = False,
    status: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, str | int]]:
    """Return professors with saved shortlist, notes, dates, or outreach status."""
    ensure_database_initialized()
    conditions = [
        "o.user_id = ?",
        "(o.is_favorite = 1 OR o.notes <> '' OR o.outreach_status <> 'Not contacted' "
        "OR o.email_sent_at <> '' OR o.follow_up_date <> '')",
    ]
    params: list[str | int] = [str(user_id)]
    if favorites_only:
        conditions.append("o.is_favorite = 1")
    if status and status != "All statuses":
        if status not in OUTREACH_STATUSES:
            raise ValueError("Choose a valid outreach status.")
        conditions.append("o.outreach_status = ?")
        params.append(status)
    where_clause = " AND ".join(conditions)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT p.*,
                   o.is_favorite, o.notes, o.outreach_status,
                   o.email_sent_at, o.follow_up_date,
                   o.email_to, o.email_subject, o.email_body,
                   o.gmail_draft_id, o.gmail_thread_id,
                   o.gmail_account_email, o.gmail_draft_created_at,
                   o.gmail_sent_at, o.gmail_replied_at,
                   o.gmail_reply_count, o.gmail_last_checked_at,
                   o.updated_at AS outreach_updated_at
            FROM professor_outreach AS o
            JOIN professors AS p ON p.id = o.professor_id
            WHERE {where_clause}
            ORDER BY
                CASE WHEN o.follow_up_date <> '' THEN 0 ELSE 1 END,
                o.follow_up_date, p.university, p.name
            """,
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def outreach_counts(*, user_id: str = DEFAULT_USER_ID) -> dict[str, int]:
    ensure_database_initialized()
    today = date.today().isoformat()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN is_favorite = 1 THEN 1 ELSE 0 END), 0) AS shortlisted,
                COALESCE(SUM(CASE WHEN outreach_status IN (
                    'Email sent', 'Follow-up needed', 'Replied',
                    'Meeting scheduled', 'Rejected'
                ) THEN 1 ELSE 0 END), 0) AS contacted,
                COALESCE(SUM(CASE WHEN outreach_status IN (
                    'Replied', 'Meeting scheduled'
                ) THEN 1 ELSE 0 END), 0) AS positive_responses,
                COALESCE(SUM(CASE WHEN follow_up_date <> ''
                    AND follow_up_date <= ?
                    AND outreach_status NOT IN ('Replied', 'Meeting scheduled', 'Rejected')
                    THEN 1 ELSE 0 END), 0) AS follow_ups_due,
                COALESCE(SUM(CASE WHEN is_favorite = 1 OR notes <> ''
                    OR outreach_status <> 'Not contacted' OR email_sent_at <> ''
                    OR follow_up_date <> '' THEN 1 ELSE 0 END), 0) AS tracked
            FROM professor_outreach
            WHERE user_id = ?
            """,
            (today, str(user_id)),
        ).fetchone()
    return {key: int(row[key]) for key in row.keys()}


def _require_user(connection: sqlite3.Connection, user_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM users WHERE user_id = ?", (str(user_id),)
    ).fetchone()
    if row is not None:
        return True
    connection.execute(
        "INSERT INTO users (user_id, email) VALUES (?, ?)",
        (str(user_id), ""),
    )
    return False


def upsert_user(
    *,
    user_id: str,
    email: str = "",
    display_name: str = "",
    avatar_url: str = "",
) -> dict[str, str]:
    """Create or update an authenticated account from a provider identity."""
    ensure_database_initialized()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, email, display_name, avatar_url, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email = COALESCE(NULLIF(excluded.email, ''), users.email),
                display_name = COALESCE(NULLIF(excluded.display_name, ''), users.display_name),
                avatar_url = COALESCE(NULLIF(excluded.avatar_url, ''), users.avatar_url),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(user_id),
                str(email or "").strip(),
                str(display_name or "").strip(),
                str(avatar_url or "").strip(),
                datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            ),
        )
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return dict(row)


def get_user(user_id: str) -> dict[str, str] | None:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    return dict(row) if row is not None else None


def create_session(
    *,
    user_id: str,
    token_hash: str,
    csrf_token: str,
    expires_at: datetime,
) -> None:
    """Persist a server-side session keyed by the hash of its bearer token."""
    ensure_database_initialized()
    with connect() as connection:
        _require_user(connection, user_id)
        connection.execute(
            "DELETE FROM sessions WHERE user_id = ?",
            (str(user_id),),
        )
        connection.execute(
            """
            INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(token_hash),
                str(user_id),
                str(csrf_token or ""),
                expires_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
            ),
        )


def get_session(token_hash: str) -> dict[str, str] | None:
    """Return the session row and user when the token hash is still valid."""
    ensure_database_initialized()
    now = datetime.now(timezone.utc)
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE token_hash = ?", (str(token_hash),)
        ).fetchone()
        if row is None:
            return None
        try:
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
        except ValueError:
            return None
        if expires_at.replace(tzinfo=expires_at.tzinfo or timezone.utc) < now:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (str(token_hash),)
            )
            return None
    return dict(row)


def touch_session(token_hash: str) -> None:
    ensure_database_initialized()
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE token_hash = ?",
            (str(token_hash),),
        )


def delete_session(token_hash: str) -> None:
    ensure_database_initialized()
    with connect() as connection:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (str(token_hash),)
        )


def delete_user_sessions(user_id: str) -> int:
    ensure_database_initialized()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM sessions WHERE user_id = ?", (str(user_id),)
        )
    return int(cursor.rowcount)


def _parse_json_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(value) for value in raw]
    try:
        parsed = json.loads(str(raw or "[]"))
        return [str(value) for value in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def get_student_profile(user_id: str) -> dict[str, object] | None:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM student_profiles WHERE user_id = ?", (str(user_id),)
        ).fetchone()
    if row is None:
        return None
    try:
        preferences = json.loads(str(row["preferences_json"]) or "{}") or {}
    except (TypeError, ValueError, json.JSONDecodeError):
        preferences = {}
    if not isinstance(preferences, dict):
        preferences = {}
    return {
        "user_id": str(row["user_id"]),
        "interests": _parse_json_list(str(row["interests_json"])),
        "interest_text": str(row["interest_text"] or ""),
        "skills": _parse_json_list(str(row["skills_json"])),
        "experience": _parse_json_list(str(row["experience_json"])),
        "coursework": _parse_json_list(str(row["coursework_json"])),
        "education_level": str(row["education_level"] or "unspecified"),
        "preferences": {
            "locations": _parse_json_list(preferences.get("locations") or ""),
            "university_types": _parse_json_list(preferences.get("university_types") or ""),
            "support_level": str(preferences.get("support_level", "") or ""),
            "remote_ok": bool(preferences.get("remote_ok", False)),
        },
        "completed": bool(int(row["profile_completed"] or 0)),
        "updated_at": str(row["updated_at"] or ""),
    }


def save_student_profile(
    user_id: str,
    *,
    interests: Iterable[str],
    interest_text: str,
    skills: Iterable[str],
    experience: Iterable[str],
    coursework: Iterable[str],
    education_level: str,
    preferences: Mapping[str, object],
    completed: bool,
) -> dict[str, object]:
    """Persist a student's research profile; returns the stored profile row."""
    ensure_database_initialized()
    clean = lambda values: [str(value).strip()[:200] for value in values if str(value).strip()]
    prefs = {
        "locations": clean(preferences.get("locations") or []),
        "university_types": clean(preferences.get("university_types") or []),
        "support_level": str(preferences.get("support_level", "") or "").strip()[:100],
        "remote_ok": bool(preferences.get("remote_ok", False)),
    }
    with connect() as connection:
        _require_user(connection, user_id)
        connection.execute(
            """
            INSERT INTO student_profiles (
                user_id, interests_json, interest_text, skills_json,
                experience_json, coursework_json, education_level,
                preferences_json, profile_completed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                interests_json = excluded.interests_json,
                interest_text = excluded.interest_text,
                skills_json = excluded.skills_json,
                experience_json = excluded.experience_json,
                coursework_json = excluded.coursework_json,
                education_level = excluded.education_level,
                preferences_json = excluded.preferences_json,
                profile_completed = excluded.profile_completed,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(user_id),
                json.dumps(clean(interests), separators=(",", ":")),
                str(interest_text or "").strip()[:3000],
                json.dumps(clean(skills), separators=(",", ":")),
                json.dumps(clean(experience), separators=(",", ":")),
                json.dumps(clean(coursework), separators=(",", ":")),
                str(education_level or "unspecified").strip()[:50],
                json.dumps(prefs, separators=(",", ":")),
                1 if completed else 0,
            ),
        )
    result = get_student_profile(user_id)
    assert result is not None
    return result


def local_owner_outreach_exists() -> int:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM professor_outreach WHERE user_id = ?",
            (DEFAULT_USER_ID,),
        ).fetchone()
    return int(row["total"])


def import_local_owner_outreach(*, target_user_id: str) -> int:
    """Copy the pre-auth local-owner outreach rows to an account (opt-in, once).

    The import is bound to whichever signed-in user explicitly requests it and
    can never run for a different account afterwards.
    """
    ensure_database_initialized()
    marker = migration_details(LOCAL_OWNER_IMPORT_MIGRATION_KEY)
    if marker and marker != target_user_id:
        raise ValueError(
            "Local data was already imported by a different account."
        )
    with connect() as connection:
        if not marker:
            cursor = connection.execute(
                """
                INSERT INTO professor_outreach (
                    user_id, professor_id, is_favorite, notes, outreach_status,
                    email_sent_at, follow_up_date, email_to, email_subject,
                    email_body, gmail_draft_id, gmail_thread_id,
                    gmail_account_email, gmail_draft_created_at
                )
                SELECT ?, professor_id, is_favorite, notes, outreach_status,
                       email_sent_at, follow_up_date, email_to, email_subject,
                       email_body, gmail_draft_id, gmail_thread_id,
                       gmail_account_email, gmail_draft_created_at
                FROM professor_outreach
                WHERE user_id = ?
                  AND professor_id NOT IN (
                      SELECT professor_id FROM professor_outreach WHERE user_id = ?
                  )
                """,
                (str(target_user_id), DEFAULT_USER_ID, str(target_user_id)),
            )
            copied = int(cursor.rowcount)
        else:
            copied = 0
        connection.execute(
            "INSERT INTO app_migrations (migration_key, applied_at, details) "
            "VALUES (?, CURRENT_TIMESTAMP, ?) "
            "ON CONFLICT(migration_key) DO UPDATE SET "
            "applied_at = CURRENT_TIMESTAMP, details = excluded.details",
            (LOCAL_OWNER_IMPORT_MIGRATION_KEY, str(target_user_id)),
        )
    return copied


def local_owner_import_marker() -> str:
    return migration_details(LOCAL_OWNER_IMPORT_MIGRATION_KEY) or ""


def migration_details(migration_key: str) -> str:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute(
            "SELECT details FROM app_migrations WHERE migration_key = ?",
            (migration_key,),
        ).fetchone()
    return str(row["details"]) if row is not None else ""


def list_universities() -> list[str]:
    def compute(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT DISTINCT university FROM professors ORDER BY university"
        ).fetchall()
        return [str(row["university"]) for row in rows]

    return list(_revision_memoized("list_universities", compute))


def update_verification_results(results: Iterable[Mapping[str, str | int]]) -> int:
    """Persist audit results without changing scraped professor information."""
    ensure_database_initialized()
    rows = []
    for result in results:
        professor_id = int(result.get("professor_id", 0))
        if professor_id <= 0:
            continue
        rows.append(
            (
                str(result.get("status", "Not checked")),
                str(result.get("issues", "Not checked")),
                str(result.get("verified_at", NOT_AVAILABLE)),
                professor_id,
            )
        )
    if not rows:
        return 0
    with connect() as connection:
        connection.executemany(
            """
            UPDATE professors
            SET verification_status = ?, verification_issues = ?, verified_at = ?
            WHERE id = ?
            """,
            rows,
        )
        _bump_data_revision(connection)
    return len(rows)


def verification_counts() -> dict[str, int]:
    ensure_database_initialized()
    with connect() as connection:
        rows = connection.execute(
            "SELECT verification_status, COUNT(*) AS total "
            "FROM professors GROUP BY verification_status"
        ).fetchall()
    return {str(row["verification_status"]): int(row["total"]) for row in rows}


def list_states() -> list[str]:
    def compute(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT DISTINCT state FROM professors "
            "WHERE state <> ? ORDER BY state",
            (NOT_AVAILABLE,),
        ).fetchall()
        return [str(row["state"]) for row in rows]

    return list(_revision_memoized("list_states", compute))


def list_department_categories() -> list[str]:
    def compute(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT DISTINCT department_category FROM professors "
            "WHERE department_category <> '' ORDER BY department_category"
        ).fetchall()
        return [str(row["department_category"]) for row in rows]

    return list(_revision_memoized("list_department_categories", compute))


def list_disciplines() -> list[str]:
    def compute(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT DISTINCT discipline FROM professors "
            "WHERE discipline <> ? AND discipline <> '' ORDER BY discipline",
            (NOT_AVAILABLE,),
        ).fetchall()
        return [str(row["discipline"]) for row in rows]

    return list(_revision_memoized("list_disciplines", compute))


def list_fields() -> list[str]:
    def compute(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT DISTINCT field FROM professors "
            "WHERE field <> ? AND field <> '' ORDER BY field",
            (NOT_AVAILABLE,),
        ).fetchall()
        return [str(row["field"]) for row in rows]

    return list(_revision_memoized("list_fields", compute))


def query_cache_key(query: str, model: str) -> tuple[str, str]:
    normalized = " ".join(str(query).casefold().split())
    digest = hashlib.sha256(f"{model}\0{normalized}".encode("utf-8")).hexdigest()
    return digest, normalized


def get_cached_query_embedding(query: str, model: str) -> list[float] | None:
    ensure_database_initialized()
    digest, _ = query_cache_key(query, model)
    with connect() as connection:
        row = connection.execute(
            "SELECT embedding_json FROM query_embedding_cache WHERE query_hash = ? AND model = ?",
            (digest, model),
        ).fetchone()
        if row is None:
            return None
        connection.execute(
            "UPDATE query_embedding_cache SET hit_count = hit_count + 1, "
            "last_used_at = CURRENT_TIMESTAMP WHERE query_hash = ?",
            (digest,),
        )
    try:
        values = json.loads(str(row["embedding_json"]))
        if isinstance(values, list):
            return [float(value) for value in values]
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def save_query_embedding(query: str, model: str, embedding: Sequence[float]) -> None:
    ensure_database_initialized()
    digest, normalized = query_cache_key(query, model)
    payload = json.dumps([float(value) for value in embedding], separators=(",", ":"))
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO query_embedding_cache (
                query_hash, normalized_query, model, embedding_json, created_at, last_used_at, hit_count
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
            ON CONFLICT(query_hash) DO UPDATE SET
                normalized_query = excluded.normalized_query,
                model = excluded.model,
                embedding_json = excluded.embedding_json,
                last_used_at = CURRENT_TIMESTAMP
            """,
            (digest, normalized, model, payload),
        )


def query_cache_count() -> int:
    ensure_database_initialized()
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM query_embedding_cache").fetchone()
    return int(row["total"] or 0)


def consume_daily_usage(usage_name: str, maximum: int, amount: int = 1) -> dict[str, int | bool]:
    """Atomically reserve daily usage from a global public-app budget."""

    maximum = max(0, int(maximum))
    amount = max(1, int(amount))
    today = date.today().isoformat()
    ensure_database_initialized()
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT usage_count FROM usage_counters WHERE usage_date = ? AND usage_name = ?",
            (today, usage_name),
        ).fetchone()
        current = int(row["usage_count"] if row else 0)
        allowed = maximum == 0 or current + amount <= maximum
        if allowed:
            new_count = current + amount
            connection.execute(
                """
                INSERT INTO usage_counters (usage_date, usage_name, usage_count, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(usage_date, usage_name) DO UPDATE SET
                    usage_count = excluded.usage_count,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (today, usage_name, new_count),
            )
        else:
            new_count = current
    remaining = -1 if maximum == 0 else max(0, maximum - new_count)
    return {"allowed": allowed, "used": new_count, "remaining": remaining, "maximum": maximum}


def daily_usage_count(usage_name: str) -> int:
    ensure_database_initialized()
    today = date.today().isoformat()
    with connect() as connection:
        row = connection.execute(
            "SELECT usage_count FROM usage_counters WHERE usage_date = ? AND usage_name = ?",
            (today, usage_name),
        ).fetchone()
    return int(row["usage_count"] if row else 0)

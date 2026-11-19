"""Ensure static public and Next.js privacy notices give the same retention facts."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    ROOT / "deploy/pilot/public-info/privacy.html",
    ROOT / "frontend/app/privacy/page.tsx",
)

SHARED_STATEMENTS = (
    "Historical pre-launch manual backups, logs and review evidence remain private and outside automatic managed expiry.",
    "These historical copies require an explicit operator retention decision; there is no automatic deletion guarantee for them.",
    "Account-bearing copies are not published or used as public demo data.",
    "New public account data is not copied into manual development fixtures.",
    "Account deletion does not automatically erase historical copies; contact us for review of those copies.",
    "Recovery must apply deletion receipts before restoring account data.",
    "Public researcher records and redacted non-personal release evidence may be retained separately.",
)


def test_historical_retention_disclosures_match_and_have_no_expired_deadline():
    for path in PAGES:
        content = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
        for statement in SHARED_STATEMENTS:
            assert statement in content, f"{path}: missing or changed: {statement}"
        assert "November 17, 2026" not in content
        assert "before public launch" not in content

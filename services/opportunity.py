from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

NOT_AVAILABLE = "Not publicly available"


@dataclass(frozen=True, slots=True)
class OutreachAssessment:
    level: str
    signals: str
    source_url: str = NOT_AVAILABLE


EXPLICIT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:open|available) positions?\b", "Lists open positions"),
    (r"\bjoin (?:our|the|my) (?:lab|laboratory|research group)\b", "Invites people to join the lab"),
    (r"\b(?:apply|application) (?:to|for).{0,35}(?:lab|research|position)\b", "Provides application guidance"),
    (r"\b(?:looking|seeking|recruiting) for .{0,30}(?:students?|researchers?|assistants?)\b", "States that the group is recruiting"),
    (r"\bundergraduate research(?: opportunities| experience| positions?)?\b", "Mentions undergraduate research"),
    (r"\bresearch opportunities\b", "Mentions research opportunities"),
    (r"\bprospective students?\b", "Provides information for prospective students"),
    (r"\bresearch assistants?\b", "Mentions research-assistant roles"),
    (r"\bvolunteer(?:ing)? .{0,20}research\b", "Mentions volunteer research"),
    (r"\bhigh school students?\b", "Mentions high-school students"),
)

LAB_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:founding |co-)?director of (?:the )?.{0,80}(?:lab|laboratory|center|institute|group)\b", "Leads a research lab or center"),
    (r"\bprincipal investigator\b|\bpi\b", "Listed as a principal investigator"),
    (r"\b(?:leads|heads|directs) (?:the |a |an )?.{0,60}(?:lab|laboratory|research group|center)\b", "Leads a research group"),
    (r"\b(?:my|our|their|his|her) (?:research )?(?:lab|laboratory|group)\b", "Has an active research group"),
    (r"\bmentors?\b|\bmentoring\b|\bsupervis(?:es|ing|ion)\b", "Mentions student mentoring or supervision"),
)

RESEARCH_ACTIVE_TITLE = re.compile(
    r"\b(?:assistant professor|associate professor|professor|research professor|"
    r"research scientist|staff scientist|postdoctoral|postdoc|principal investigator|director)\b",
    re.IGNORECASE,
)

TEACHING_ONLY_TITLE = re.compile(
    r"\b(?:part[- ]?time lecturer|adjunct lecturer|lecturer|instructor|professor of practice)\b",
    re.IGNORECASE,
)


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _distinct_academic_website(record: dict[str, str]) -> bool:
    website = str(record.get("website_url", NOT_AVAILABLE)).strip()
    profile = str(record.get("profile_url", NOT_AVAILABLE)).strip()
    if not website or website == NOT_AVAILABLE or website == profile:
        return False
    parsed = urlparse(website)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _matched_labels(text: str, patterns: tuple[tuple[str, str], ...]) -> list[str]:
    labels: list[str] = []
    lowered = text.lower()
    for pattern, label in patterns:
        if re.search(pattern, lowered, flags=re.IGNORECASE | re.DOTALL):
            labels.append(label)
    return list(dict.fromkeys(labels))


def assess_outreach_potential(
    record: dict[str, str],
    *,
    source_text: str = "",
    source_url: str | None = None,
) -> OutreachAssessment:
    """Estimate how useful a public profile is for research outreach.

    This is deliberately evidence-based and does not claim that a person accepts
    high-school students. It only reports signals published on academic pages.
    Research-topic ranking remains completely separate from this assessment.
    """
    combined = _clean_text(
        " ".join(
            [
                source_text,
                str(record.get("title", "")),
                str(record.get("research_interests", "")),
                str(record.get("opportunity_signals", "")),
            ]
        )
    )
    evidence_url = source_url or str(record.get("opportunity_source_url", NOT_AVAILABLE))
    if not evidence_url or evidence_url == NOT_AVAILABLE:
        evidence_url = str(record.get("website_url", NOT_AVAILABLE))
    if not evidence_url or evidence_url == NOT_AVAILABLE:
        evidence_url = str(record.get("profile_url", NOT_AVAILABLE))

    explicit = _matched_labels(combined, EXPLICIT_PATTERNS)
    if explicit:
        return OutreachAssessment("Strong", "; ".join(explicit[:3]), evidence_url)

    lab_signals = _matched_labels(combined, LAB_PATTERNS)
    if lab_signals:
        return OutreachAssessment("Moderate", "; ".join(lab_signals[:3]), evidence_url)

    title = _clean_text(str(record.get("title", "")))
    if RESEARCH_ACTIVE_TITLE.search(title):
        signals = ["Research-active university appointment"]
        if _distinct_academic_website(record):
            signals.append("Has a separate academic or lab website")
        return OutreachAssessment("Moderate", "; ".join(signals), evidence_url)

    if _distinct_academic_website(record):
        return OutreachAssessment(
            "Moderate",
            "Has a separate academic or lab website",
            evidence_url,
        )

    if TEACHING_ONLY_TITLE.search(title):
        return OutreachAssessment(
            "Basic",
            "Public professional contact found, but no research-opportunity signal was detected",
            evidence_url,
        )

    return OutreachAssessment(
        "Basic",
        "Public professional contact found; no explicit opportunity information was detected",
        evidence_url,
    )

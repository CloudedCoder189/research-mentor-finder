"""Narrow, reversible public-directory corrections reviewed on 2026-11-05.

These affect the served directory, not stored accounts or original scraped data.
Caltech source: https://www.cms.caltech.edu/people/clairer
Remove this compatibility correction once the stored record is re-reviewed.
"""
from typing import Any


def discovery_candidate(record: dict[str, Any]) -> bool:
    """Keep an identified marketing-only role out of researcher discovery.

    Exact identity and role guards avoid excluding academic staff by title rules.
    Existing saved records remain accessible; nothing is deleted.
    """
    return not (
        str(record.get("id")) == "1515"
        and record.get("name") == "Emily Wadkins"
        and record.get("university") == "Oregon State University"
        and record.get("title") == "Marketing and Communications Manager"
    )


def reviewed_record(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    identities = {"746": "Claire Ralph", "745": "Jinghao Cao"}
    if not (identities.get(str(record.get("id"))) == record.get("name")
            and record.get("university") == "California Institute of Technology"):
        return result
    if str(record.get("id")) == "746" and result.get("title") == "Director, Career Achievement, Leadership, and Exploration":
        result["title"] = "Director, Career Achievement, Leadership, and Exploration; Lecturer, Computing and Mathematical Sciences"
    text = str(result.get("research_interests", "")).casefold()
    if "skip to main content" in text and "open about submenu" in text:
        # Do not let these known navigation-only scrapes or their derived
        # enrichment become match evidence. Cao's unavailable source remains
        # failed; this correction does not establish a current affiliation.
        result.update(
            research_interests="Not publicly available", ai_summary="",
            categories="", ai_categories="", embedding_json="",
            embedding_model="", embedding_source_hash="",
            opportunity_level="Basic",
            opportunity_signals="No explicit research opportunity information found",
            opportunity_source_url="Not publicly available",
            verification_status="Failed" if record.get("verification_status") == "Failed" else "Review",
            verification_issues=("Academic role confirmed on the official profile; research interests and research mentoring availability are not established there."
                                 if str(record.get("id")) == "746" else "The former profile link is unavailable and the indexed research description contains website navigation. Current affiliation, research interests and mentoring availability need source review."),
        )
    return result

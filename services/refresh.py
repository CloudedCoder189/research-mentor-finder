from __future__ import annotations

from collections.abc import Callable
from typing import Any

from database import delete_demo_records, prune_university_records, upsert_professors
from scrapers.universities import IMPLEMENTED_SCRAPERS
from services.categorization import (
    categories_to_text,
    categorize_with_keywords,
    categorize_with_openai,
)
from services.deduplication import deduplicate
from services.opportunity import assess_outreach_potential

ProgressCallback = Callable[[str], None]

UNIVERSITY_SCRAPERS = IMPLEMENTED_SCRAPERS


def refresh_university(
    university: str,
    *,
    use_openai: bool = False,
    max_profiles: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int | str]:
    if university not in UNIVERSITY_SCRAPERS:
        raise ValueError(f"No implemented scraper for {university}")

    def update(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    update(f"Reading official {university} faculty sources...")
    scraper_class = UNIVERSITY_SCRAPERS[university]
    scraper = scraper_class(max_profiles=max_profiles, progress_callback=update)
    scraped = [record.as_record() for record in scraper.safe_scrape()]
    scraper_error = str(getattr(scraper, "last_error", "") or "").strip()

    update("Removing duplicate records...")
    unique_records = deduplicate(scraped)

    update("Categorizing research interests and outreach signals...")
    for record in unique_records:
        interests = record.get("research_interests", "")
        categories = (
            categorize_with_openai(interests)
            if use_openai
            else categorize_with_keywords(interests)
        )
        record["categories"] = categories_to_text(categories)

        # Older adapters may not provide profile-text evidence. Apply a safe
        # fallback based only on public title/profile/website fields.
        existing_level = str(record.get("opportunity_level", "")).strip()
        existing_signals = str(record.get("opportunity_signals", "")).strip()
        if not existing_level or existing_signals in {
            "",
            "No explicit opportunity information found",
        }:
            assessment = assess_outreach_potential(record)
            record["opportunity_level"] = assessment.level
            record["opportunity_signals"] = assessment.signals
            record["opportunity_source_url"] = assessment.source_url

    pruned = 0
    if unique_records:
        delete_demo_records()
        saved = upsert_professors(unique_records)
        authoritative = bool(getattr(scraper, "authoritative_roster", False))
        minimum = int(getattr(scraper, "minimum_authoritative_records", 1))
        if max_profiles is None and authoritative and len(unique_records) >= minimum:
            update("Removing stale records that are no longer on the authoritative faculty roster...")
            pruned = prune_university_records(
                university,
                [str(record.get("email", "")) for record in unique_records],
            )
        elif max_profiles is None and authoritative and len(unique_records) < minimum:
            scraper_error = (
                f"{scraper_error} " if scraper_error else ""
            ) + (
                f"Authoritative cleanup was skipped because only {len(unique_records)} records "
                f"were returned; at least {minimum} are required before stale rows can be removed."
            )
    else:
        saved = 0

    update("Refresh complete.")
    return {
        "scraped": len(scraped),
        "unique": len(unique_records),
        "saved": saved,
        "pruned": pruned,
        "university": university,
        "error": scraper_error,
    }


def refresh_all_universities(
    *,
    use_openai: bool = False,
    max_profiles_per_university: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Refresh every implemented university sequentially.

    One university failure never stops the remaining refreshes. The returned
    per-university rows are designed for direct display or CSV export.
    """

    university_names = list(UNIVERSITY_SCRAPERS)
    total = len(university_names)
    rows: list[dict[str, int | str]] = []

    totals = {
        "scraped": 0,
        "unique": 0,
        "saved": 0,
        "pruned": 0,
        "completed": 0,
        "failed": 0,
        "empty": 0,
    }

    def update(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    for index, university in enumerate(university_names, start=1):
        prefix = f"[{index}/{total}] {university}"

        def university_progress(message: str, *, current_prefix: str = prefix) -> None:
            update(f"{current_prefix}: {message}")

        try:
            summary = refresh_university(
                university,
                use_openai=use_openai,
                max_profiles=max_profiles_per_university,
                progress_callback=university_progress,
            )
            saved = int(summary.get("saved", 0))
            status = "Completed" if saved > 0 else "No records saved"
            if saved > 0:
                totals["completed"] += 1
            else:
                totals["empty"] += 1

            for key in ("scraped", "unique", "saved", "pruned"):
                totals[key] += int(summary.get(key, 0))

            rows.append(
                {
                    "university": university,
                    "status": status,
                    "scraped": int(summary.get("scraped", 0)),
                    "unique": int(summary.get("unique", 0)),
                    "saved": saved,
                    "pruned": int(summary.get("pruned", 0)),
                    "error": str(summary.get("error", "")),
                }
            )
        except Exception as exc:  # Keep later universities running.
            totals["failed"] += 1
            rows.append(
                {
                    "university": university,
                    "status": "Failed",
                    "scraped": 0,
                    "unique": 0,
                    "saved": 0,
                    "pruned": 0,
                    "error": str(exc),
                }
            )
            update(f"{prefix}: Failed safely: {exc}")

    update("All-university refresh complete.")
    return {
        "universities_attempted": total,
        **totals,
        "results": rows,
    }


def refresh_stanford(**kwargs):
    return refresh_university("Stanford University", **kwargs)

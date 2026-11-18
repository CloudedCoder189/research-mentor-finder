from __future__ import annotations

from collections.abc import Iterable

AUDIT_SCOPES = (
    "New or changed records",
    "Failed records only",
    "Review records only",
    "One university",
    "Selected professors",
    "All records",
)


def select_audit_records(
    records: Iterable[dict],
    scope: str,
    *,
    university: str | None = None,
    selected_ids: set[int] | None = None,
    limit: int | None = None,
) -> list[dict]:
    selected_ids = selected_ids or set()
    chosen: list[dict] = []

    for record in records:
        status = str(record.get("verification_status", "Not checked"))
        professor_id = int(record.get("id", 0) or 0)
        include = False
        if scope == "New or changed records":
            include = status == "Not checked"
        elif scope == "Failed records only":
            include = status == "Failed"
        elif scope == "Review records only":
            include = status == "Review"
        elif scope == "One university":
            include = bool(university) and str(record.get("university", "")) == university
        elif scope == "Selected professors":
            include = professor_id in selected_ids
        elif scope == "All records":
            include = True
        if include:
            chosen.append(dict(record))

    priority = {"Failed": 0, "Not checked": 1, "Review": 2, "Verified": 3}
    chosen.sort(
        key=lambda record: (
            priority.get(str(record.get("verification_status", "Not checked")), 4),
            str(record.get("university", "")).casefold(),
            str(record.get("name", "")).casefold(),
        )
    )
    if limit is not None and limit > 0:
        return chosen[:limit]
    return chosen

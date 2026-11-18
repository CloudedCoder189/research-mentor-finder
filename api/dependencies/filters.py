from __future__ import annotations

from typing import Any

from services.ui_helpers import filter_candidates

VERIFICATION_LABELS = {
    "Verified": "Verified only",
    "Review": "Review only",
    "Failed": "Failed only",
    "Not checked": "Not checked only",
}

NO_VALUE = ("", "All", "Any", "Any university", "Any state", "Any field",
            "Any status", "Any level", "All states", "All statuses",
            "All verification statuses", "All department groups", "All public contacts",
            "All supported universities", "All disciplines", "All fields", None)


def is_no_value(value: Any) -> bool:
    return str(value or "").strip() in NO_VALUE or str(value or "").strip() == ""


def translate_filters(
    *,
    university: str | None = None,
    state: str | None = None,
    field: str | None = None,
    department_category: str | None = None,
    verification: str | None = None,
    opportunity: str | None = None,
    topics: list[str] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    if not is_no_value(state):
        kwargs["state_filter"] = str(state).strip()
    if not is_no_value(department_category):
        kwargs["department_filter"] = str(department_category).strip()
    if not is_no_value(field):
        kwargs["field_filter"] = str(field).strip()
    if not is_no_value(verification):
        label = str(verification).strip()
        kwargs["verification_filter"] = VERIFICATION_LABELS.get(label, label)
    if not is_no_value(opportunity):
        kwargs["outreach_filter"] = str(opportunity).strip()
    selected_topics = [
        str(topic).strip() for topic in (topics or []) if str(topic or "").strip()
    ]
    if selected_topics:
        kwargs["topic_filters"] = selected_topics

    return kwargs


def unified_university(value: str | None) -> str | None:
    if is_no_value(value):
        return None
    return str(value).strip()


def apply_filters(records: list[dict], **translate_kwargs) -> list[dict]:
    return filter_candidates(records, **translate_filters(**translate_kwargs))
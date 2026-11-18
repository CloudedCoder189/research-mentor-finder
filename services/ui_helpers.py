from __future__ import annotations

import html

from services.taxonomy import infer_discipline, infer_field


def topic_values(record: dict, limit: int = 6) -> list[str]:
    values: list[str] = []
    for field in ("ai_categories", "categories"):
        for value in str(record.get(field, "")).split(","):
            cleaned = " ".join(value.split()).strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
            if len(values) >= limit:
                return values
    return values


def topic_chips_html(topics: list[str]) -> str:
    if not topics:
        return ""
    return "".join(
        f"<span class='topic-chip'>{html.escape(topic)}</span>" for topic in topics
    )


def resolve_search_query(query: str, topic_filters: list[str] | None = None) -> str:
    """Return the typed query, or use selected standardized topics as the query."""
    cleaned_query = " ".join(str(query or "").split()).strip()
    if cleaned_query:
        return cleaned_query
    selected_topics = [
        " ".join(str(topic).split()).strip()
        for topic in (topic_filters or [])
        if " ".join(str(topic).split()).strip()
    ]
    return ", ".join(dict.fromkeys(selected_topics))


def verification_filter_matches(record: dict, selected_filter: str) -> bool:
    status = str(record.get("verification_status", "Not checked"))
    mapping = {
        "Verified only": {"Verified"},
        "Verified or review": {"Verified", "Review"},
        "Review only": {"Review"},
        "Failed only": {"Failed"},
        "Not checked only": {"Not checked"},
    }
    allowed = mapping.get(selected_filter)
    return True if allowed is None else status in allowed


def outreach_filter_matches(record: dict, selected_filter: str) -> bool:
    level = str(record.get("opportunity_level", "Basic"))
    if selected_filter == "Moderate or strong":
        return level in {"Moderate", "Strong"}
    if selected_filter == "Strong only":
        return level == "Strong"
    return True


# The home page presents broad academic categories ("Computing", "Engineering"),
# while Discover's field filter lists concrete department fields. Accepting the
# discipline as well lets those broad categories select real records instead of
# returning nothing.
BROAD_FIELD_CATEGORIES = frozenset(
    {"Computing", "Engineering", "Mathematics & Computing", "Engineering & Computing"}
)


def joint_affiliation_values(record: dict) -> tuple[list[str], list[str]]:
    """Known fields for explicitly joint departments, without a primary guess."""
    department = str(record.get("department", ""))
    if ";" not in department:
        return [], []
    fields = list(dict.fromkeys(infer_field(part.strip()) for part in department.split(";")))
    fields = [field for field in fields if field != "Not publicly available"]
    disciplines = list(dict.fromkeys(infer_discipline(field) for field in fields))
    disciplines = [value for value in disciplines if value != "Not publicly available"]
    return fields, disciplines


def field_filter_matches(record: dict, selected_filter: str) -> bool:
    if selected_filter == "All fields":
        return True
    if str(record.get("field", "")) == selected_filter:
        return True
    fields, disciplines = joint_affiliation_values(record)
    if selected_filter not in BROAD_FIELD_CATEGORIES:
        return selected_filter in fields
    return str(record.get("discipline", "")) == selected_filter or selected_filter in disciplines


def filter_candidates(
    records: list[dict],
    *,
    state_filter: str = "All states",
    department_filter: str = "All department groups",
    topic_filters: list[str] | None = None,
    outreach_filter: str = "All public contacts",
    verification_filter: str = "All verification statuses",
    discipline_filter: str = "All disciplines",
    field_filter: str = "All fields",
) -> list[dict]:
    selected_topics = set(topic_filters or [])
    filtered: list[dict] = []
    for record in records:
        if state_filter != "All states" and str(record.get("state", "")) != state_filter:
            continue
        if (
            department_filter != "All department groups"
            and str(record.get("department_category", "")) != department_filter
        ):
            continue
        if (
            discipline_filter != "All disciplines"
            and str(record.get("discipline", "")) != discipline_filter
        ):
            continue
        if not field_filter_matches(record, field_filter):
            continue
        if selected_topics and not selected_topics.intersection(set(topic_values(record, limit=100))):
            continue
        if not outreach_filter_matches(record, outreach_filter):
            continue
        if not verification_filter_matches(record, verification_filter):
            continue
        filtered.append(record)
    return filtered

from __future__ import annotations

import re
from typing import Iterable


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def deduplicate(records: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    seen_people: set[tuple[str, str]] = set()

    for record in records:
        email = record.get("email", "").strip().lower()
        person_key = (
            _normalize_name(record.get("name", "")),
            record.get("university", "").strip().lower(),
        )

        if email and email in seen_emails:
            continue
        if person_key[0] and person_key in seen_people:
            continue

        if email:
            seen_emails.add(email)
        if person_key[0]:
            seen_people.add(person_key)
        unique.append(record)

    return unique

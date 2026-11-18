from __future__ import annotations

import math
from typing import Iterable, Sequence, TypeVar

T = TypeVar("T")

PAGE_SIZE_OPTIONS = (10, 25, 50, 100)


def parse_page_selection(value: object, default: int = 1) -> int:
    """Return a page number from either a numeric value or a label like 'Page 2 of 5'."""
    if isinstance(value, bool):
        return max(1, int(default))
    if isinstance(value, int):
        return max(1, value)
    if isinstance(value, float) and value.is_integer():
        return max(1, int(value))

    text = str(value or "").strip()
    if text.isdigit():
        return max(1, int(text))

    match = __import__("re").search(r"\bpage\s+(\d+)\b", text, flags=__import__("re").IGNORECASE)
    if match:
        return max(1, int(match.group(1)))

    return max(1, int(default))


def page_count(total_items: int, page_size: int) -> int:
    """Return at least one page so page controls stay stable for empty results."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    return max(1, math.ceil(max(0, total_items) / page_size))


def clamp_page(page: int, total_items: int, page_size: int) -> int:
    return min(max(1, int(page)), page_count(total_items, page_size))


def paginate(items: Sequence[T], page: int, page_size: int) -> list[T]:
    safe_page = clamp_page(page, len(items), page_size)
    start = (safe_page - 1) * page_size
    return list(items[start : start + page_size])


def page_bounds(total_items: int, page: int, page_size: int) -> tuple[int, int]:
    """Return one-based inclusive bounds for display, or (0, 0) when empty."""
    if total_items <= 0:
        return 0, 0
    safe_page = clamp_page(page, total_items, page_size)
    start = (safe_page - 1) * page_size + 1
    end = min(total_items, safe_page * page_size)
    return start, end


def sort_results(records: Iterable[dict], sort_mode: str) -> list[dict]:
    records = list(records)
    if sort_mode == "Name (A–Z)":
        return sorted(
            records,
            key=lambda row: (
                str(row.get("name", "")).casefold(),
                str(row.get("university", "")).casefold(),
            ),
        )
    if sort_mode == "University (A–Z)":
        return sorted(
            records,
            key=lambda row: (
                str(row.get("university", "")).casefold(),
                str(row.get("name", "")).casefold(),
            ),
        )
    return sorted(
        records,
        key=lambda row: (
            -float(row.get("match_score", 0.0)),
            -float(row.get("semantic_score", 0.0)),
            str(row.get("name", "")).casefold(),
        ),
    )

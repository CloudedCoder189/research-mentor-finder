from services.pagination import (
    clamp_page,
    page_bounds,
    page_count,
    paginate,
    parse_page_selection,
    sort_results,
)


def test_page_count_and_clamping():
    assert page_count(0, 25) == 1
    assert page_count(500, 25) == 20
    assert clamp_page(0, 500, 25) == 1
    assert clamp_page(99, 500, 25) == 20


def test_paginate_and_bounds():
    items = list(range(60))
    assert paginate(items, 2, 25) == list(range(25, 50))
    assert page_bounds(60, 3, 25) == (51, 60)
    assert page_bounds(0, 1, 25) == (0, 0)


def test_sort_results_modes():
    rows = [
        {"name": "Zed", "university": "A", "match_score": 90, "semantic_score": 80},
        {"name": "Amy", "university": "B", "match_score": 95, "semantic_score": 70},
        {"name": "Ben", "university": "A", "match_score": 80, "semantic_score": 90},
    ]
    assert [row["name"] for row in sort_results(rows, "Best match")] == ["Amy", "Zed", "Ben"]
    assert [row["name"] for row in sort_results(rows, "Name (A–Z)")] == ["Amy", "Ben", "Zed"]
    assert [row["name"] for row in sort_results(rows, "University (A–Z)")] == ["Ben", "Zed", "Amy"]


def test_parse_page_selection_handles_streamlit_labels():
    assert parse_page_selection(2) == 2
    assert parse_page_selection("3") == 3
    assert parse_page_selection("Page 1 of 3") == 1
    assert parse_page_selection("Page 12 of 20") == 12
    assert parse_page_selection("unexpected", default=4) == 4

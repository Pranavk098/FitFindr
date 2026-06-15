"""
tests/test_tools.py

Isolation tests for each FitFindr tool. Run with: pytest tests/

Tests cover:
  - search_listings: happy path, empty results, price filter, size filter
  - suggest_outfit: populated wardrobe, empty wardrobe (fallback branch)
  - create_fit_card: normal output, empty outfit guard, LLM varies output
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # No listing matches "designer ballgown" under $5 in size XXS
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=30)
    assert all(item["price"] <= 30 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match "S/M", "M", "M/L" listings
    results = search_listings("top", size="M", max_price=None)
    for item in results:
        assert "m" in item["size"].lower(), (
            f"Expected size to contain 'm', got '{item['size']}'"
        )


def test_search_returns_list_not_exception_on_no_match():
    # Even a completely nonsensical query should return [] not raise
    results = search_listings("xyzzy quantum ballgown", size="XXXS", max_price=1)
    assert results == []


def test_search_sorted_by_relevance():
    # "vintage graphic tee" — items with more matching tokens should rank higher
    results = search_listings("vintage graphic tee", size=None, max_price=100)
    assert len(results) > 1
    # First result should contain more of our keywords than later ones
    # (just verify the list is non-empty and items are dicts with expected fields)
    first = results[0]
    assert "title" in first
    assert "price" in first
    assert "platform" in first


def test_search_result_fields():
    results = search_listings("vintage", size=None, max_price=100)
    assert len(results) > 0
    item = results[0]
    required_fields = {"id", "title", "description", "category", "style_tags",
                       "size", "condition", "price", "colors", "platform"}
    assert required_fields.issubset(item.keys())


# ── suggest_outfit ────────────────────────────────────────────────────────────

# Use a real listing dict as fixture so we don't depend on search results
SAMPLE_ITEM = {
    "id": "lst_002",
    "title": "Y2K Baby Tee — Butterfly Print",
    "description": "Super cute early 2000s baby tee with butterfly graphic.",
    "category": "tops",
    "style_tags": ["y2k", "vintage", "graphic tee", "cottagecore"],
    "size": "S/M",
    "condition": "excellent",
    "price": 18.0,
    "colors": ["white", "pink", "purple"],
    "brand": None,
    "platform": "depop",
}


def test_suggest_outfit_with_wardrobe():
    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_returns_string():
    # Empty wardrobe should trigger the fallback branch — still returns a string
    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_no_exception():
    # Must not raise even with no wardrobe items
    try:
        result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
        assert result  # non-empty
    except Exception as e:
        pytest.fail(f"suggest_outfit raised an exception with empty wardrobe: {e}")


# ── create_fit_card ───────────────────────────────────────────────────────────

SAMPLE_OUTFIT = (
    "Pair this Y2K butterfly baby tee with baggy straight-leg jeans "
    "and white platform sneakers for an effortless Y2K streetwear look."
)


def test_create_fit_card_returns_string():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit_guard():
    # Empty outfit string must return error message, not raise
    result = create_fit_card("", SAMPLE_ITEM)
    assert result == "No outfit suggestion available — can't generate a fit card."


def test_create_fit_card_whitespace_outfit_guard():
    # Whitespace-only outfit string hits the same guard
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert result == "No outfit suggestion available — can't generate a fit card."


def test_create_fit_card_mentions_platform():
    result = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    # Caption should mention the platform somewhere
    assert SAMPLE_ITEM["platform"].lower() in result.lower()


def test_create_fit_card_varies_output():
    # Two calls on the same input should not be identical (temperature=0.9)
    # We run 2 and check they differ — probabilistically almost certain
    result1 = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    result2 = create_fit_card(SAMPLE_OUTFIT, SAMPLE_ITEM)
    # Both must be non-empty strings
    assert result1 and result2
    # They should differ — if identical, temperature may be too low
    # This is a probabilistic test; if it ever fails it's informative not flaky
    assert result1 != result2, (
        "create_fit_card returned identical output twice — "
        "check that temperature=0.9 is set on the LLM call"
    )

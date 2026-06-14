"""
Unit tests for the three FitFindr tools.

Tests that hit the Groq LLM (suggest_outfit, create_fit_card happy path) are
skipped automatically when GROQ_API_KEY is not set, so the deterministic
search_listings tests still run in any environment.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

needs_api = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)

NEW_ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "band tee"],
    "colors": ["black"],
    "price": 24.0,
    "platform": "depop",
    "condition": "good",
}


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_sorted_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    scores = [item["relevance"] for item in results]
    assert scores == sorted(scores, reverse=True)


def test_search_size_is_loose():
    # "M" should admit combined sizes like "S/M" and "M/L", not just exact "M".
    results = search_listings("vintage", size="M", max_price=None)
    sizes = {item["size"] for item in results}
    assert any("/" in s for s in sizes)  # at least one combined size got through


# ── suggest_outfit ───────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_does_not_crash():
    """Failure mode: empty wardrobe must still return a non-empty string."""
    result = suggest_outfit(NEW_ITEM, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


@needs_api
def test_suggest_outfit_uses_wardrobe():
    result = suggest_outfit(NEW_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    """Failure mode: empty outfit returns an error string, never raises."""
    result = create_fit_card("", NEW_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_guarded():
    result = create_fit_card("   \n  ", NEW_ITEM)
    assert "couldn't" in result.lower() or "no outfit" in result.lower()


@needs_api
def test_create_fit_card_mentions_price_and_platform():
    outfit = "Pair with baggy dark-wash jeans and chunky white sneakers."
    card = create_fit_card(outfit, NEW_ITEM)
    assert isinstance(card, str) and card.strip() != ""
    assert "24" in card
    assert "depop" in card.lower()

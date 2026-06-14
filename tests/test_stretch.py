"""
Tests for the stretch features:
  - compare_price (price assessment vs. comparable same-category listings)
  - retry-with-fallback search in the planning loop

The pure-Python paths run anywhere; the one test that drives the full agent
through the LLM tools is skipped without GROQ_API_KEY.
"""

import os

import pytest

from tools import compare_price, search_listings
from agent import run_agent, _search_with_fallback, _parse_query
from utils.data_loader import get_example_wardrobe

needs_api = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── compare_price ─────────────────────────────────────────────────────────────

def test_compare_price_flags_a_great_deal():
    # Leather belt ($12) is well below the median accessories price.
    belt = next(l for l in search_listings("leather belt") if l["id"] == "lst_014")
    result = compare_price(belt)
    assert result["verdict"] == "great deal"
    assert result["median"] is not None
    assert result["n_comparables"] > 0
    assert "below" in result["reasoning"]


def test_compare_price_flags_overpriced():
    # Leather bomber ($75) is far above the median outerwear price.
    bomber = next(l for l in search_listings("leather bomber") if l["id"] == "lst_022")
    result = compare_price(bomber)
    assert result["verdict"] == "overpriced"
    assert "above" in result["reasoning"]


def test_compare_price_no_comparison_does_not_crash():
    # An item in a category with no peers returns a graceful "no comparison".
    orphan = {"id": "x", "category": "spacesuit", "price": 100.0}
    result = compare_price(orphan)
    assert result["verdict"] == "no comparison"
    assert result["reasoning"]  # non-empty, no exception


# ── retry-with-fallback ────────────────────────────────────────────────────────

def test_fallback_loosens_price_when_exact_fails():
    # Band tees cost $19–$24, so "under $10" has no exact match; dropping the
    # price cap should find results and explain what was loosened.
    results, note = _search_with_fallback(_parse_query("vintage band tee under $10"))
    assert len(results) > 0
    assert note is not None
    assert "price" in note.lower()


def test_fallback_note_is_none_when_exact_search_works():
    results, note = _search_with_fallback(_parse_query("vintage graphic tee under $30"))
    assert len(results) > 0
    assert note is None  # no loosening was needed


def test_hard_failure_still_stops_after_retries():
    # Nothing matches even after loosening → error set, no fit card, LLM untouched.
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    assert session["fit_card"] is None
    assert session["selected_item"] is None


@needs_api
def test_retry_surfaces_note_and_price_assessment_in_session():
    session = run_agent("vintage band tee under $10", get_example_wardrobe())
    assert session["error"] is None
    assert session["search_note"] is not None
    assert session["price_assessment"] is not None
    assert session["fit_card"]

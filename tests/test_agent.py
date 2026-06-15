"""
tests/test_agent.py

Tests for the run_agent() planning loop.

These tests mock all three tools so they run offline. The focus is on:
  - State threading: each tool receives exactly the value stored in session,
    not a re-derived or hardcoded substitute.
  - Branching: when search_listings returns [], the loop stops immediately —
    suggest_outfit and create_fit_card must never be called.
  - Session completeness: on success all output fields are populated and
    session["error"] is None.
"""

from unittest.mock import patch

import pytest

from agent import run_agent, _parse_query


# ── fixtures ──────────────────────────────────────────────────────────────────

FAKE_LISTING = {
    "id": "lst_006",
    "title": "Graphic Tee — 2003 Tour Bootleg Style",
    "description": "Vintage-style bootleg tee with faded graphic.",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge", "streetwear"],
    "size": "L",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

FAKE_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Dark wash jeans",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear"],
        }
    ]
}

FAKE_OUTFIT = "Pair the graphic tee with dark wash jeans and chunky white sneakers."
FAKE_FIT_CARD = "Found this gem on depop for $24 — obsessed with the vintage vibes. 🖤"


# ── _parse_query unit tests ───────────────────────────────────────────────────

def test_parse_query_extracts_price():
    result = _parse_query("vintage graphic tee under $30")
    assert result["max_price"] == 30.0
    assert "vintage" in result["description"]
    assert "graphic" in result["description"]
    assert result["size"] is None


def test_parse_query_extracts_explicit_size():
    result = _parse_query("90s track jacket in size M")
    assert result["size"] == "M"
    assert result["max_price"] is None
    assert "jacket" in result["description"]


def test_parse_query_extracts_both_size_and_price():
    result = _parse_query("designer ballgown size XXS under $5")
    assert result["size"] == "XXS"
    assert result["max_price"] == 5.0


def test_parse_query_no_size_no_price():
    result = _parse_query("vintage flannel shirt")
    assert result["size"] is None
    assert result["max_price"] is None
    assert "flannel" in result["description"]


# ── state threading tests ─────────────────────────────────────────────────────

def test_selected_item_is_top_search_result():
    """session['selected_item'] must be results[0], not a copy or re-fetch."""
    second_listing = {**FAKE_LISTING, "id": "lst_002", "title": "Second item"}
    with patch("agent.search_listings", return_value=[FAKE_LISTING, second_listing]), \
         patch("agent.suggest_outfit", return_value=FAKE_OUTFIT), \
         patch("agent.create_fit_card", return_value=FAKE_FIT_CARD):

        session = run_agent("vintage graphic tee", wardrobe=FAKE_WARDROBE)

    # Identity check: must be the exact same object, not a copy
    assert session["selected_item"] is FAKE_LISTING


def test_suggest_outfit_receives_selected_item_from_session():
    """suggest_outfit must be called with the same dict stored in session['selected_item']."""
    with patch("agent.search_listings", return_value=[FAKE_LISTING]), \
         patch("agent.suggest_outfit", return_value=FAKE_OUTFIT) as mock_suggest, \
         patch("agent.create_fit_card", return_value=FAKE_FIT_CARD):

        session = run_agent("vintage graphic tee", wardrobe=FAKE_WARDROBE)

    mock_suggest.assert_called_once()
    call_kwargs = mock_suggest.call_args.kwargs
    passed_item = call_kwargs.get("new_item", mock_suggest.call_args.args[0] if mock_suggest.call_args.args else None)
    assert passed_item is session["selected_item"]


def test_create_fit_card_receives_outfit_suggestion_from_session():
    """create_fit_card must be called with the exact string stored in session['outfit_suggestion']."""
    with patch("agent.search_listings", return_value=[FAKE_LISTING]), \
         patch("agent.suggest_outfit", return_value=FAKE_OUTFIT), \
         patch("agent.create_fit_card", return_value=FAKE_FIT_CARD) as mock_fit_card:

        session = run_agent("vintage graphic tee", wardrobe=FAKE_WARDROBE)

    assert session["outfit_suggestion"] == FAKE_OUTFIT
    mock_fit_card.assert_called_once()
    call_kwargs = mock_fit_card.call_args.kwargs
    passed_outfit = call_kwargs.get("outfit", mock_fit_card.call_args.args[0] if mock_fit_card.call_args.args else None)
    assert passed_outfit == session["outfit_suggestion"]


# ── branching / no-results path ───────────────────────────────────────────────

def test_no_results_sets_error_message():
    """When search_listings returns [], session['error'] must be a non-empty string."""
    with patch("agent.search_listings", return_value=[]), \
         patch("agent.suggest_outfit") as mock_suggest, \
         patch("agent.create_fit_card") as mock_fit_card:

        session = run_agent("designer ballgown size XXS under $5", wardrobe=FAKE_WARDROBE)

    assert session["error"] is not None
    assert len(session["error"].strip()) > 0


def test_no_results_leaves_fit_card_as_none():
    """When search_listings returns [], session['fit_card'] must remain None."""
    with patch("agent.search_listings", return_value=[]), \
         patch("agent.suggest_outfit"), \
         patch("agent.create_fit_card"):

        session = run_agent("designer ballgown size XXS under $5", wardrobe=FAKE_WARDROBE)

    assert session["fit_card"] is None
    assert session["outfit_suggestion"] is None


def test_no_results_does_not_call_downstream_tools():
    """suggest_outfit and create_fit_card must not be called when search returns nothing."""
    with patch("agent.search_listings", return_value=[]), \
         patch("agent.suggest_outfit") as mock_suggest, \
         patch("agent.create_fit_card") as mock_fit_card:

        run_agent("designer ballgown size XXS under $5", wardrobe=FAKE_WARDROBE)

    mock_suggest.assert_not_called()
    mock_fit_card.assert_not_called()


# ── near-miss messaging ───────────────────────────────────────────────────────

def test_no_results_with_price_near_miss_names_item_and_price():
    """When a keyword match exists but is over budget, error names the item and its price."""
    over_budget = {**FAKE_LISTING, "price": 45.0}  # query max is $20, item is $45
    # First call (with filters) → []; second call (keyword-only) → [over_budget]
    with patch("agent.search_listings", side_effect=[[], [over_budget]]), \
         patch("agent.suggest_outfit"), \
         patch("agent.create_fit_card"):

        session = run_agent("graphic tee under $20", wardrobe=FAKE_WARDROBE)

    assert over_budget["title"] in session["error"]
    assert "$45.00" in session["error"]


def test_no_results_with_size_near_miss_names_item_and_size():
    """When a keyword match exists but is the wrong size, error names the item and its size."""
    wrong_size = {**FAKE_LISTING, "size": "W32"}  # query size is S
    with patch("agent.search_listings", side_effect=[[], [wrong_size]]), \
         patch("agent.suggest_outfit"), \
         patch("agent.create_fit_card"):

        session = run_agent("baggy jeans size S", wardrobe=FAKE_WARDROBE)

    assert wrong_size["title"] in session["error"]
    assert "W32" in session["error"]


def test_no_results_with_both_filters_near_miss_mentions_both_reasons():
    """When a near-miss is excluded by both size and price, both reasons appear in the error."""
    wrong_both = {**FAKE_LISTING, "size": "W32", "price": 45.0}
    with patch("agent.search_listings", side_effect=[[], [wrong_both]]), \
         patch("agent.suggest_outfit"), \
         patch("agent.create_fit_card"):

        session = run_agent("baggy jeans size S under $20", wardrobe=FAKE_WARDROBE)

    assert "W32" in session["error"]
    assert "$45.00" in session["error"]


def test_no_results_no_near_miss_falls_back_to_generic_message():
    """When keyword search also returns nothing, use the plain generic error."""
    with patch("agent.search_listings", return_value=[]), \
         patch("agent.suggest_outfit"), \
         patch("agent.create_fit_card"):

        session = run_agent("xyzzy nonsense garment size S under $5", wardrobe=FAKE_WARDROBE)

    assert session["error"] is not None
    # No item title should be injected — just the generic advice
    assert "Try a broader description" in session["error"]


# ── happy path completeness ───────────────────────────────────────────────────

def test_happy_path_populates_all_session_fields():
    """On success, all output fields are set and error is None."""
    with patch("agent.search_listings", return_value=[FAKE_LISTING]), \
         patch("agent.suggest_outfit", return_value=FAKE_OUTFIT), \
         patch("agent.create_fit_card", return_value=FAKE_FIT_CARD):

        session = run_agent("vintage graphic tee under $30", wardrobe=FAKE_WARDROBE)

    assert session["error"] is None
    assert session["selected_item"] == FAKE_LISTING
    assert session["outfit_suggestion"] == FAKE_OUTFIT
    assert session["fit_card"] == FAKE_FIT_CARD

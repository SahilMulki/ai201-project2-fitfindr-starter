"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.
LLM-backed tools (suggest_outfit, create_fit_card) use a mocked Groq client
so these tests run offline and do not consume API credits.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_groq(response_text: str):
    """Return a mock Groq client whose chat completion always yields response_text."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = response_text
    return mock_client


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_listings_no_results_returns_empty_list():
    """Failure mode: impossible query + tight filters → empty list, not an exception."""
    results = search_listings("designer ballgown couture gown", size="XXS", max_price=1.0)
    assert results == []


def test_search_listings_price_ceiling_excludes_expensive_items():
    """Items priced above max_price must not appear in results."""
    max_price = 16.0
    results = search_listings("vintage", max_price=max_price)
    for item in results:
        assert item["price"] <= max_price


def test_search_listings_size_filter_excludes_wrong_sizes():
    """Only items whose size string contains the requested size are returned."""
    results = search_listings("jeans denim", size="W32")
    assert len(results) > 0
    for item in results:
        assert "w32" in item["size"].lower()


def test_search_listings_caps_at_three_results():
    """Never returns more than 3 items regardless of how many listings match."""
    results = search_listings("vintage streetwear")
    assert len(results) <= 3


def test_search_listings_top_result_is_most_relevant():
    """The first result should contain the most queried keywords."""
    results = search_listings("vintage graphic tee")
    assert len(results) > 0
    top = results[0]
    searchable = " ".join([
        top["title"],
        top["description"],
        " ".join(top["style_tags"]),
    ]).lower()
    assert any(kw in searchable for kw in ["graphic", "tee", "vintage"])


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_general_advice():
    """Failure mode: empty wardrobe → non-empty general styling advice (no error raised)."""
    advice = "Pair this with wide-leg trousers and chunky sneakers for a relaxed streetwear look."
    with patch("tools._get_groq_client", return_value=_mock_groq(advice)):
        result = suggest_outfit(
            new_item={
                "title": "Vintage Graphic Tee",
                "description": "Faded graphic tee, slightly boxy fit",
                "style_tags": ["vintage", "graphic tee", "streetwear"],
                "colors": ["black"],
            },
            wardrobe=get_empty_wardrobe(),
        )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_with_wardrobe_returns_outfit_string():
    """Normal path: populated wardrobe → non-empty specific outfit suggestion."""
    suggestion = "Try it over the white ribbed tank with the dark wash jeans and combat boots."
    with patch("tools._get_groq_client", return_value=_mock_groq(suggestion)):
        result = suggest_outfit(
            new_item={
                "title": "Oversized Flannel Shirt — Plaid Red/Black",
                "description": "Classic oversized flannel, great layering piece",
                "style_tags": ["grunge", "vintage", "flannel", "layering"],
                "colors": ["red", "black"],
            },
            wardrobe=get_example_wardrobe(),
        )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_message():
    """Failure mode: empty outfit string → descriptive error message, no LLM call."""
    result = create_fit_card(
        outfit="",
        new_item={"title": "Graphic Tee", "price": 24.0, "platform": "depop"},
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    assert "error" in result.lower() or "missing" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_message():
    """Failure mode: whitespace-only outfit → error message, no LLM call."""
    result = create_fit_card(
        outfit="   \n\t  ",
        new_item={"title": "Graphic Tee", "price": 24.0, "platform": "depop"},
    )
    assert "error" in result.lower() or "missing" in result.lower()


def test_create_fit_card_valid_input_returns_caption():
    """Normal path: valid outfit + item dict → caption string from LLM."""
    expected_caption = (
        "Found this Graphic Tee — 2003 Tour Bootleg Style on depop for $24 and I'm in love. "
        "Styled it with baggy jeans and chunky sneakers for peak vintage streetwear vibes."
    )
    with patch("tools._get_groq_client", return_value=_mock_groq(expected_caption)):
        result = create_fit_card(
            outfit="Graphic tee tucked into baggy jeans with chunky white sneakers.",
            new_item={
                "title": "Graphic Tee — 2003 Tour Bootleg Style",
                "price": 24.0,
                "platform": "depop",
            },
        )
    assert result == expected_caption

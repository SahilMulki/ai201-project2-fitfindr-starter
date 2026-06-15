"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_MODEL = "llama-3.1-8b-instant"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    # Filter by price and size first
    filtered = [
        listing for listing in listings
        if (max_price is None or listing["price"] <= max_price)
        and (size is None or size.lower() in listing["size"].lower())
    ]

    # Tokenize description into individual keywords
    keywords = set(re.findall(r'\w+', description.lower()))

    # Score each listing by how many keywords appear in its searchable text
    scored = []
    for listing in filtered:
        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand") or "",
        ]).lower()

        score = sum(1 for kw in keywords if kw in searchable)
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [listing for _, listing in scored[:3]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = _get_groq_client()

    item_summary = (
        f"{new_item.get('title', 'thrifted item')}\n"
        f"Description: {new_item.get('description', '')}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}"
    )

    if not wardrobe.get("items"):
        prompt = (
            "You are a fashion stylist. A user is considering buying this thrifted item:\n\n"
            f"{item_summary}\n\n"
            "They haven't shared their wardrobe yet. Give them 1-2 specific outfit ideas "
            "for this piece — describe what types of clothing and accessories would pair "
            "well with it. Be specific about styles, fits, and colors. Keep it concise."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} "
            f"({', '.join(item.get('colors', []))} | {', '.join(item.get('style_tags', []))})"
            for item in wardrobe["items"]
        )
        prompt = (
            "You are a fashion stylist. A user is considering buying this thrifted item:\n\n"
            f"{item_summary}\n\n"
            "Their current wardrobe includes:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 specific outfit combinations using the new item together with "
            "named pieces from their wardrobe. Describe the overall vibe of each look. "
            "Keep it concise."
        )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    if not outfit or not outfit.strip():
        return (
            "Error: outfit data is missing. Please provide an outfit suggestion "
            "before generating a fit card."
        )

    client = _get_groq_client()

    prompt = (
        "Write a casual, authentic 2-4 sentence Instagram/TikTok caption for a thrifted outfit post.\n\n"
        f"Thrifted item: {new_item.get('title', 'thrifted find')}\n"
        f"Price: ${new_item.get('price', '??')}\n"
        f"Platform: {new_item.get('platform', 'thrift store')}\n"
        f"Outfit: {outfit}\n\n"
        "Requirements:\n"
        "- Sound like a real OOTD post, not a product listing\n"
        "- Mention the item name, price, and platform once each, woven in naturally\n"
        "- Capture the outfit's specific vibe\n"
        "- Be casual and authentic\n\n"
        "Write only the caption — no extra commentary or quotes around it."
    )

    response = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return response.choices[0].message.content

"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import logging
import re

from tools import search_listings, suggest_outfit, create_fit_card

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.
    """
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query
    using regex so the planning loop never re-prompts the user for values
    already in the original input.

    Examples:
        "vintage graphic tee under $30"
            → {description: "vintage graphic tee", size: None, max_price: 30.0}
        "90s track jacket in size M"
            → {description: "90s track jacket in", size: "M", max_price: None}
        "designer ballgown size XXS under $5"
            → {description: "designer ballgown", size: "XXS", max_price: 5.0}
    """
    q = query

    # ── price: "under $30", "$30", "max $40", etc. ────────────────────────────
    max_price = None
    price_match = re.search(
        r'(?:under|max|below|less\s+than)?\s*\$\s*(\d+(?:\.\d+)?)',
        q, re.IGNORECASE,
    )
    if price_match:
        max_price = float(price_match.group(1))
        q = q[:price_match.start()] + q[price_match.end():]

    # ── size: "size M", "size W30", "size 8", or bare XL / S/M / W32 ─────────
    size = None
    # Prefer explicit "size <token>" first
    size_explicit = re.search(r'\bsize\s+(\S+)', q, re.IGNORECASE)
    if size_explicit:
        size = size_explicit.group(1).rstrip(',.')
        q = q[:size_explicit.start()] + q[size_explicit.end():]
    else:
        # Fall back to bare size tokens (order matters — longest alternatives first)
        size_implicit = re.search(
            r'\b(XXL|XS|S/M|M/L|L/XL|XL|S|M|L|W\d{2}(?:\s+L\d{2})?)\b',
            q, re.IGNORECASE,
        )
        if size_implicit:
            size = size_implicit.group(1).strip()
            q = q[:size_implicit.start()] + q[size_implicit.end():]

    description = re.sub(r'\s+', ' ', q).strip(' ,.')
    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    The loop branches on what each tool returns:
    - If search_listings returns nothing → set session["error"] and return early.
      suggest_outfit and create_fit_card are NOT called.
    - If search_listings returns results → proceed through all three tools,
      threading each tool's output directly into the next tool's input via
      session state (no re-prompting, no hardcoded values).

    Args:
        query:    Natural language user request.
        wardrobe: User's wardrobe dict.

    Returns:
        The session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion / fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)
    log.info("")
    log.info("  query : %r", query)

    # Step 2: Parse query → extract search parameters
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]
    log.info(
        "  parsed: description=%r  size=%r  max_price=%s",
        parsed["description"], parsed["size"],
        f"${parsed['max_price']}" if parsed["max_price"] is not None else "None",
    )

    # Step 3: Search listings
    log.info("")
    log.info("  [1/3] search_listings →")
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )
    for i, r in enumerate(session["search_results"]):
        log.info("        %d. %s  ($%.2f, %s)", i + 1, r["title"], r["price"], r["platform"])
    if not session["search_results"]:
        log.info("        (no results)")

    # Branch: nothing matched → look for near-misses before telling the user why
    if not session["search_results"]:
        error_msg = "No listings matched your search."

        # If a size or price filter was active, run a keyword-only fallback to
        # find what would have matched — so we can tell the user specifically
        # what was ruled out and why.
        if parsed["size"] or parsed["max_price"] is not None:
            log.info("        retrying without filters to find near-misses...")
            near_misses = search_listings(description=parsed["description"])
            if near_misses:
                top = near_misses[0]
                reasons = []
                if parsed["size"] and parsed["size"].lower() not in top["size"].lower():
                    reasons.append(f"size {top['size']} (wanted {parsed['size']})")
                if parsed["max_price"] is not None and top["price"] > parsed["max_price"]:
                    reasons.append(f"${top['price']:.2f} (over ${parsed['max_price']:.2f} limit)")

                if reasons:
                    log.info("        near-miss found: %r", top["title"])
                    for r in reasons:
                        log.info("          ✗ %s", r)
                    error_msg += (
                        f" The closest match, \"{top['title']}\", was ruled out"
                        f" because {' and '.join(reasons)}."
                    )
            else:
                log.info("        no near-misses — description matched nothing")

        error_msg += (
            " Try a broader description, a different size, or a higher price limit."
        )
        session["error"] = error_msg
        log.warning("")
        log.warning("  ✗ stopping early: %s", session["error"])
        log.warning("")
        return session

    # Step 4: Select top result and thread it into state
    session["selected_item"] = session["search_results"][0]
    log.info("        selected → %r", session["selected_item"]["title"])

    # Step 5: Suggest outfit — uses selected_item and wardrobe from session
    wardrobe_size = len(session["wardrobe"].get("items", []))
    log.info("")
    log.info("  [2/3] suggest_outfit  (wardrobe: %d item(s)) →", wardrobe_size)
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )
    log.info("        %d chars returned", len(session["outfit_suggestion"]))

    # Step 6: Create fit card — uses outfit_suggestion and selected_item from session
    log.info("")
    log.info("  [3/3] create_fit_card →")
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )
    log.info("        %d chars returned", len(session["fit_card"]))

    # Step 7: Return completed session
    log.info("")
    log.info("  ✓ done")
    log.info("")
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\n── selected_item (passed into suggest_outfit) ──")
        print(f"  id:       {session['selected_item']['id']}")
        print(f"  title:    {session['selected_item']['title']}")
        print(f"  price:    ${session['selected_item']['price']}")
        print(f"  platform: {session['selected_item']['platform']}")
        print(f"\n── outfit_suggestion (passed into create_fit_card) ──")
        print(session["outfit_suggestion"])
        print(f"\n── fit_card ──")
        print(session["fit_card"])

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"session['error']:    {session2['error']}")
    print(f"session['fit_card']: {session2['fit_card']}")

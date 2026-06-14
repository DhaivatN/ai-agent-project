"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_listing_value,
    get_style_profile,
    save_style_profile,
)
from utils.data_loader import load_listings


# ── session state ─────────────────────────────────────────────────────────────


def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.
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
        "retry_count": 0,
        "retry_reason": None,
        "style_profile": {},
        "price_comparison": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────


def _parse_query(query: str) -> dict:
    """
    Simple rule-based parser for description, size, and max_price.

    Example:
        "vintage graphic tee under $30, size M"
        -> {
            "description": "vintage graphic tee",
            "size": "M",
            "max_price": 30.0
        }
    """
    raw = query.strip()
    q = raw.lower()

    parsed = {
        "description": raw,
        "size": None,
        "max_price": None,
    }

    # extract max_price
    price_match = re.search(r"under\s*\$?\s*(\d+(?:\.\d+)?)", q)
    if price_match:
        try:
            parsed["max_price"] = float(price_match.group(1))
        except ValueError:
            pass

    # extract size
    size_match = re.search(
        r"(?:size\s+)?\b(xxs|xs|s|m|l|xl|xxl|w28|w30|w32|w34)\b",
        q,
    )
    if size_match:
        parsed["size"] = size_match.group(1).upper()

    # clean description by removing parsed price/size phrases
    description = q
    description = re.sub(r"under\s*\$?\s*\d+(?:\.\d+)?", "", description)
    description = re.sub(
        r"(?:size\s+)?\b(xxs|xs|s|m|l|xl|xxl|w28|w30|w32|w34)\b",
        "",
        description,
    )
    description = description.replace(",", " ")
    description = " ".join(description.split())

    parsed["description"] = description if description else raw.lower()

    return parsed


# ── planning loop ─────────────────────────────────────────────────────────────


def run_agent(query: str, wardrobe: dict, user_id: str = "demo_user") -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict
        user_id:  Identifier used for simple persistent style profile storage

    Returns:
        The session dict after the interaction completes.
    """
    session = _new_session(query, wardrobe)

    # Step 1: parse the query
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 2: load saved style profile
    session["style_profile"] = get_style_profile(user_id)

    # Step 3: search listings
    results = search_listings(description, size=size, max_price=max_price)

    # Step 4: retry once if no results
    if not results:
        session["retry_count"] = 1
        session["retry_reason"] = "no_results_with_size"

        results = search_listings(description, size=None, max_price=max_price)

    # Step 5: stop early if still no results
    if not results:
        session["error"] = (
            "I couldn’t find any listings that match your search, even after widening the size filter. "
            "Try relaxing the price, changing the description, or choosing a different style."
        )
        return session

    # Step 6: store results and select top result
    session["search_results"] = results
    session["selected_item"] = results[0]

    # Step 7: compare listing value using full dataset
    all_listings = load_listings()
    session["price_comparison"] = compare_listing_value(
        session["selected_item"],
        all_listings,
    )

    # Step 8: suggest outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # Step 9: create fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    # Step 10: save/update simple style profile
    selected = session["selected_item"]
    updated_profile = {
        "last_query": query,
        "liked_style_tags": selected.get("style_tags", []),
        "liked_colors": selected.get("colors", []),
        "last_category": selected.get("category"),
    }
    save_style_profile(user_id, updated_profile)

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )

    print("Session parsed:", session["parsed"])
    print("Retry count:", session["retry_count"])
    print("Retry reason:", session["retry_reason"])
    print("Style profile loaded:", session["style_profile"])

    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"\nFound: {session['selected_item']['title']}")
        print(f"Price: {session['selected_item']['price']}")
        print(f"Platform: {session['selected_item']['platform']}")

        print("\nPrice comparison:")
        print(session["price_comparison"])

        print("\nOutfit:")
        print(session["outfit_suggestion"])

        print("\nFit card:")
        print(session["fit_card"])

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )

    print("Session parsed:", session2["parsed"])
    print("Retry count:", session2["retry_count"])
    print("Retry reason:", session2["retry_reason"])
    print(f"Error message: {session2['error']}")

    print("\n\n=== Empty wardrobe path ===\n")
    session3 = run_agent(
        query="vintage graphic tee under $30",
        wardrobe=get_empty_wardrobe(),
    )

    print("Session parsed:", session3["parsed"])
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"\nFound: {session3['selected_item']['title']}")
        print("\nOutfit:")
        print(session3["outfit_suggestion"])
        print("\nFit card:")
        print(session3["fit_card"])
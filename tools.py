import re
import json
import string
from utils.data_loader import load_listings
# from typing import Tuple, Any

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

from dotenv import load_dotenv
from groq import Groq


load_dotenv()

# Helper functions for search_listing()
def _normalize_text(text: str | None) -> str:
    """Lowercase text, remove punctuation, and collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return " ".join(text.split())

def _tokenize(text: str | None) -> set[str]:
    """Convert text into a set of normalized word tokens."""
    normalized = _normalize_text(text)
    if not normalized:
        return set()
    return set(re.findall(r"\b\w+\b", normalized))


def _matches_size(query_size: str, listing_size: str) -> bool:
    """
    Check whether a requested size matches the listing size.
    Supports partial matching like 'M' matching 'S/M', and 'W30' matching 'W28/L30'.
    """    
    if not query_size or not listing_size:
        return False

    query_norm = _normalize_text(query_size)
    listing_norm = _normalize_text(listing_size)

    query_tokens = _tokenize(query_norm)
    listing_tokens = _tokenize(listing_norm)

    if query_tokens & listing_tokens:
        return True

    if len(query_norm) > 1 and query_norm in listing_norm:
        return True

    return False

def _score_listing(query_text: str, query_tokens: set[str], listing: dict) -> int:
    """Compute a weighted keyword-overlap score for one listing."""
    title_tokens = _tokenize(listing.get("title"))
    description_tokens = _tokenize(listing.get("description"))
    category_tokens = _tokenize(listing.get("category"))
    style_tag_tokens = _tokenize(" ".join(listing.get("style_tags", [])))
    color_tokens = _tokenize(" ".join(listing.get("colors", [])))
    brand_tokens = _tokenize(listing.get("brand"))

    score = 0
    score += 3 * len(query_tokens & title_tokens)
    score += 3 * len(query_tokens & style_tag_tokens)
    score += 2 * len(query_tokens & category_tokens)
    score += 2 * len(query_tokens & brand_tokens)
    score += 1 * len(query_tokens & description_tokens)
    score += 1 * len(query_tokens & color_tokens)

    query_phrase = _normalize_text(query_text)
    title_phrase = _normalize_text(listing.get("title"))
    style_phrase = _normalize_text(" ".join(listing.get("style_tags", [])))

    if query_phrase and query_phrase in title_phrase:
        score += 3
    if query_phrase and query_phrase in style_phrase:
        score += 3

    return score


# Helper functions for suggest_outfits()

def _format_item_brief(item: dict) -> str:

    """Create a compact one-line summary of a wardrobe or listing item."""

    name = item.get("name") or item.get("title") or "Unnamed item"
    category = item.get("category", "unknown category")
    colors = ", ".join(item.get("colors", [])) if item.get("colors") else ""
    style_tags = ", ".join(item.get("style_tags", [])) if item.get("style_tags") else ""
    notes = item.get("notes") or ""

    parts = [name, f"category: {category}"]
    if colors:
        parts.append(f"colors: {colors}")
    if style_tags:
        parts.append(f"style: {style_tags}")
    if notes:
        parts.append(f"notes: {notes}")

    return " | ".join(parts)


def _fallback_outfit_suggestion(new_item: dict, wardrobe: dict) -> str:
    """
    Generic fallback when the LLM is unavailable.
    Uses only provided data and avoids highly specific hardcoded styling logic.
    """
    item_name = new_item.get("title", "this thrifted item")
    item_category = new_item.get("category", "item")
    item_colors = new_item.get("colors", [])
    item_tags = new_item.get("style_tags", [])

    color_text = ", ".join(item_colors) if item_colors else "versatile colors"
    tag_text = ", ".join(item_tags[:3]) if item_tags else "a distinctive style"

    wardrobe_items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    if wardrobe_items:
        wardrobe_preview = ", ".join(
            item.get("name", "a wardrobe piece") for item in wardrobe_items[:4]
        )
        return (
            f"A good starting point is to build around {item_name} as the focal piece. "
            f"It has {tag_text} energy and works well with simple supporting items in {color_text}. "
            f"From the wardrobe provided, it can pair well with {wardrobe_preview}."
        )

    return (
        f"{item_name} can be styled by treating it as the focal piece and keeping the rest of the outfit simple. "
        f"It has {tag_text} energy and should work best with complementary basics in {color_text}. "
        f"Start with easy layers, grounded shoes, and minimal accessories so the item stays central."
    )


def _fallback_fit_card(outfit: str, new_item: dict) -> str:
    """Simple caption fallback if the LLM call fails or returns nothing."""
    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale platform")
    style_tags = new_item.get("style_tags", [])
    colors = new_item.get("colors", [])

    if isinstance(price, (int, float)):
        price_text = f"${price:.0f}" if price.is_integer() else f"${price:.2f}"
    else:
        price_text = "a great price"

    vibe = ", ".join(style_tags[:2]) if style_tags else "easy everyday"
    color_text = ", ".join(colors[:2]) if colors else "versatile"

    outfit = (outfit or "").strip()

    if outfit:
        return (
            f"Found {title} on {platform} for {price_text}, and it feels like such a good {vibe} piece. "
            f"I’d style it with simple layers and easy basics so the {color_text} tones and overall shape can stand out. "
            f"It gives the whole look an effortless, pulled-together feel."
        )

    return (
        f"Found {title} on {platform} for {price_text}, and it feels like such a good {vibe} piece. "
        f"I’d keep the rest of the outfit simple and let the {color_text} tones do the work."
    )

def _summarize_outfit_text(outfit: str) -> str:
    """Very lightweight compression for fallback captions."""
    if not outfit:
        return "simple layers and easy basics"

    text = outfit.strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^.]*can be styled by ", "", text, flags=re.IGNORECASE)
    text = text.split(".")[0].strip()

    if len(text) > 100:
        text = text[:97].rstrip() + "..."

    return text or "simple layers and easy basics"


# Helper function for create_fit_card()

def _fallback_fit_card(outfit: str, new_item: dict) -> str:
    """Simple caption fallback if the LLM call fails or returns nothing."""
    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale platform")

    if isinstance(price, (int, float)):
        price_text = f"${price:.0f}" if price.is_integer() else f"${price:.2f}"
    else:
        price_text = "a great price"

    base = f"Picked up {title} from {platform} for {price_text}."

    outfit = (outfit or "").strip()
    if outfit:
        return (
            f"{base} I’m styling it like this: {outfit} "
            f"It keeps the piece as the main focus while still feeling wearable."
        )

    return (
        f"{base} It’s got so much styling potential — I’m keeping the rest of the outfit "
        f"pretty simple so this piece can do the talking."
    )

# Additional functions

def _comparable_items(selected_item: dict, all_listings: list[dict]) -> list[dict]:
    cat = selected_item.get("category")
    tags = set(t.lower() for t in selected_item.get("style_tags", []))
    platform = selected_item.get("platform")
    colors = set(c.lower() for c in selected_item.get("colors", []))

    comparables = []
    for item in all_listings:
        if item.get("id") == selected_item.get("id"):
            continue
        if item.get("category") != cat:
            continue

        item_tags = set(t.lower() for t in item.get("style_tags", []))
        item_colors = set(c.lower() for c in item.get("colors", []))

        tag_overlap = bool(tags & item_tags)
        color_overlap = bool(colors & item_colors)
        same_platform = item.get("platform") == platform

        if tag_overlap or color_overlap or same_platform:
            comparables.append(item)

    return comparables

def compare_listing_value(selected_item: dict, all_listings: list[dict]) -> dict:
    price = selected_item.get("price")
    if not isinstance(price, (int, float)):
        return {
            "price_assessment": "unknown",
            "reasoning": "The selected item had no numeric price, so I couldn’t compare it.",
            "comparable_count": 0,
            "average_comparable_price": None,
        }

    comparables = _comparable_items(selected_item, all_listings)
    comparable_prices = [c.get("price") for c in comparables if isinstance(c.get("price"), (int, float))]

    if not comparable_prices:
        return {
            "price_assessment": "unknown",
            "reasoning": "There weren’t enough similar items in the dataset to estimate value.",
            "comparable_count": 0,
            "average_comparable_price": None,
        }

    avg_price = sum(comparable_prices) / len(comparable_prices)
    ratio = price / avg_price if avg_price > 0 else 1.0

    if ratio <= 0.85:
        label = "good deal"
        reason = (
            f"This looks like a good deal. Similar items average around ${avg_price:.0f}, "
            f"and this one is priced lower at ${price:.0f}."
        )
    elif ratio >= 1.15:
        label = "overpriced"
        reason = (
            f"This looks a bit overpriced. Similar items average around ${avg_price:.0f}, "
            f"and this one is priced higher at ${price:.0f}."
        )
    else:
        label = "fair price"
        reason = (
            f"This looks like a fair price. Similar items average around ${avg_price:.0f}, "
            f"and this one is close at ${price:.0f}."
        )

    return {
        "price_assessment": label,
        "reasoning": reason,
        "comparable_count": len(comparable_prices),
        "average_comparable_price": avg_price,
    }

_STYLE_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "data", "style_profiles.json")

def _load_all_profiles() -> dict:
    if not os.path.exists(_STYLE_PROFILE_PATH):
        return {}
    try:
        with open(_STYLE_PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_all_profiles(data: dict) -> None:
    os.makedirs(os.path.dirname(_STYLE_PROFILE_PATH), exist_ok=True)
    with open(_STYLE_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_style_profile(user_id: str) -> dict:
    profiles = _load_all_profiles()
    return profiles.get(user_id, {})

def save_style_profile(user_id: str, preferences: dict) -> dict:
    profiles = _load_all_profiles()
    profiles[user_id] = preferences or {}
    try:
        _save_all_profiles(profiles)
        return {"saved": True, "stored_preferences": profiles[user_id]}
    except Exception:
        return {"saved": False, "stored_preferences": {}}


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
    all_listings = load_listings()
    query_tokens = _tokenize(description)
    query_text = description
    query_tokens = _tokenize(query_text)

    if not query_tokens:
        return []

    filtered = []

    for listing in all_listings:
        price = listing.get("price")
        listing_size = listing.get("size", "")

        if max_price is not None and isinstance(price, (int, float)) and price > max_price:
            continue

        if size is not None and not _matches_size(size, listing_size):
            continue

        score = _score_listing(query_text, query_tokens, listing)

        if score > 0:
            listing_with_score = dict(listing)
            listing_with_score["match_score"] = score
            filtered.append(listing_with_score)

    filtered.sort(key=lambda x: (-x["match_score"], x.get("price", float("inf"))))
    return filtered


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
    if not new_item:
        return "I couldn’t generate an outfit suggestion because no thrifted item was provided."

    wardrobe_items = wardrobe.get("items", []) if isinstance(wardrobe, dict) else []

    item_name = new_item.get("title", "Unknown item")
    item_category = new_item.get("category", "unknown")
    item_description = new_item.get("description", "")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    item_price = new_item.get("price", "unknown")
    item_platform = new_item.get("platform", "unknown")

    if not wardrobe_items:
        user_prompt = f"""
A user is considering this thrifted item:
- Title: {item_name}
- Category: {item_category}
- Description: {item_description}
- Style tags: {item_tags}
- Colors: {item_colors}
- Price: {item_price}
- Platform: {item_platform}

The user has not entered any wardrobe items yet.

Give 1–2 short styling ideas for how to wear this item.
Be specific about what kinds of pants, layers, shoes, or accessories pair well with it.
Mention the overall vibe of each look.
Keep the answer concise, natural, and practical.
Do not apologize or mention missing data.
"""
    else:
        wardrobe_text = "\n".join(
            f"- {_format_item_brief(item)}" for item in wardrobe_items
        )

        user_prompt = f"""
A user is considering this thrifted item:
- Title: {item_name}
- Category: {item_category}
- Description: {item_description}
- Style tags: {item_tags}
- Colors: {item_colors}
- Price: {item_price}
- Platform: {item_platform}

Here is the user's wardrobe:
{wardrobe_text}

Suggest 1–2 outfit ideas using the thrifted item and only pieces from the provided wardrobe list.
Name the wardrobe pieces you use.
Explain why the outfit works and describe the vibe.
Keep the answer concise, specific, and natural.
Do not invent wardrobe items that were not provided.
Do not use bullet points.
"""

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise personal stylist. "
                        "You create practical outfit suggestions based only on the provided item and wardrobe context."
                    ),
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.7,
            max_tokens=300,
        )

        text = response.choices[0].message.content
        if text and text.strip():
            return text.strip()
    except Exception as e:
        # pass
        print("suggest_outfit fallback triggered", e)
    return _fallback_outfit_suggestion(new_item, wardrobe)

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
    """
    if not outfit or not outfit.strip():
        return (
            "I couldn’t generate a fit card because no outfit description was provided. "
            "Make sure suggest_outfit runs successfully before calling create_fit_card."
        )

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale platform")
    category = new_item.get("category", "")
    style_tags = ", ".join(new_item.get("style_tags", [])) if new_item.get("style_tags") else ""
    colors = ", ".join(new_item.get("colors", [])) if new_item.get("colors") else ""

    if isinstance(price, (int, float)):
        price_text = f"${price:.0f}" if price.is_integer() else f"${price:.2f}"
    else:
        price_text = "a great price"

    user_prompt = f"""
You are writing a casual, authentic outfit caption for social media.

Here is the thrifted item:
- Title: {title}
- Category: {category}
- Style tags: {style_tags}
- Colors: {colors}
- Price: {price_text}
- Platform: {platform}

Here is the outfit suggestion the user wants to post about:
{outfit}

Write a 2–4 sentence caption that:
- Feels like a real OOTD post, not a product listing
- Mentions the item name, price, and platform naturally (each exactly once)
- Describes how the outfit comes together and the overall vibe
- Uses a friendly, relaxed tone with no hashtags and no emojis
- Does not repeat the bullet list or restate these instructions

Return only the caption text, no extra commentary.
"""

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise, casual outfit captions for social media. "
                        "You keep things specific, avoid hype language, and sound like a real person."
                    ),
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.9,
            max_tokens=250,
        )

        text = response.choices[0].message.content
        if text and text.strip():
            return text.strip()
    except Exception as e:
        # fall back to deterministic caption if anything goes wrong
        # pass
        print("create_fit_card fallback triggered", e)

    return _fallback_fit_card(outfit, new_item)


if __name__ == "__main__":
#     results = search_listings("vintage graphic tee", max_price=30)
#     print(f"Found {len(results)} results")
#     for item in results[:5]:
#         print(item["title"], item["price"], item["match_score"])


    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    results1 = search_listings("vintage graphic tee", max_price=30)
    print(suggest_outfit(results1[0], get_example_wardrobe()))

    results = search_listings("vintage graphic tee", max_price=30)
    print(suggest_outfit(results[0], get_empty_wardrobe()))

    print(suggest_outfit({}, get_example_wardrobe()))
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

from utils.data_loader import load_listings

load_dotenv()


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
    """
    listings = load_listings()

    # Apply hard filters first (before scoring)
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Score each remaining listing by keyword overlap
    tokens = [t.lower() for t in description.split() if t]

    def score(listing: dict) -> int:
        # Build a single searchable text blob from the listing's text fields
        tag_text = " ".join(listing.get("style_tags", []))
        blob = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            tag_text,
        ]).lower()
        return sum(1 for token in tokens if token in blob)

    scored = [(score(l), l) for l in listings]
    # Drop zero-score listings (no keyword overlap at all)
    scored = [(s, l) for s, l in scored if s > 0]
    # Sort by score descending (best match first)
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


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
    item_summary = (
        f"Item: {new_item.get('title', 'Unknown')}\n"
        f"Category: {new_item.get('category', '')}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Condition: {new_item.get('condition', '')}\n"
        f"Price: ${new_item.get('price', 0):.2f}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # Empty wardrobe — give general styling advice
        prompt = (
            f"You are a thrift-savvy stylist. A user just found this secondhand piece:\n\n"
            f"{item_summary}\n\n"
            f"They don't have a saved wardrobe yet. Give them 1–2 short paragraphs of "
            f"general styling advice: what kind of pieces pair well with this item, "
            f"what vibe or aesthetic it suits, and how to wear it. "
            f"Be specific and casual — like a friend who's into fashion, not a magazine."
        )
    else:
        # Populated wardrobe — suggest specific outfit combinations
        wardrobe_lines = []
        for w in wardrobe_items:
            tags = ", ".join(w.get("style_tags", []))
            colors = ", ".join(w.get("colors", []))
            note = f" ({w['notes']})" if w.get("notes") else ""
            wardrobe_lines.append(
                f"- {w['name']} [{w['category']}] — colors: {colors}, tags: {tags}{note}"
            )
        wardrobe_text = "\n".join(wardrobe_lines)

        prompt = (
            f"You are a thrift-savvy stylist. A user is considering buying this secondhand piece:\n\n"
            f"{item_summary}\n\n"
            f"Their current wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest 1–2 complete outfit combinations using the new item and specific "
            f"named pieces from their wardrobe. Be concrete — name the exact wardrobe pieces. "
            f"Keep it casual and practical, like advice from a stylish friend. "
            f"2–4 sentences per outfit is plenty."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Couldn't generate outfit suggestions right now. Try pairing this with neutral basics."


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
        return "No outfit suggestion available — can't generate a fit card."

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price", 0)
    platform = new_item.get("platform", "a thrift app")

    prompt = (
        f"You are writing an Instagram/TikTok OOTD caption for a thrift haul. "
        f"The item is: {title}, found on {platform} for ${price:.2f}.\n\n"
        f"The outfit: {outfit}\n\n"
        f"Write a 2–4 sentence caption that:\n"
        f"- Sounds like a real person posting, not a brand (casual, lowercase-friendly)\n"
        f"- Mentions the item name, price (${price:.2f}), and platform ({platform}) each exactly once\n"
        f"- Captures the specific outfit vibe — not generic ('love this look') but specific\n"
        f"- Could actually be posted on Instagram or TikTok\n\n"
        f"Just the caption — no hashtags, no intro text."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Fit card unavailable right now."

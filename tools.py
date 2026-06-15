"""
tools.py

All FitFindr tools. Each tool is a standalone function that can be called
and tested independently before being wired into the agent loop.

Required tools:
    search_listings(description, size, max_price)       → list[dict]
    suggest_outfit(new_item, wardrobe, ...)             → str
    create_fit_card(outfit, new_item)                   → str

Stretch tools:
    price_compare(item, all_listings)                   → str
    get_trending_styles()                               → str
"""

import os
import statistics

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings, load_trends

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
        tag_text = " ".join(listing.get("style_tags", []))
        blob = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            tag_text,
        ]).lower()
        return sum(1 for token in tokens if token in blob)

    scored = [(score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(
    new_item: dict,
    wardrobe: dict,
    trend_context: str = "",
    style_profile: dict | None = None,
) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item:      A listing dict (the item the user is considering buying).
        wardrobe:      A wardrobe dict with an 'items' key. May be empty.
        trend_context: Optional string from get_trending_styles() — injected into
                       the prompt so the LLM considers current trends. Pass "" to skip.
        style_profile: Optional profile dict from load_style_profile() — preferred
                       styles and colors are added to the prompt context.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice instead.
    """
    item_summary = (
        f"Item: {new_item.get('title', 'Unknown')}\n"
        f"Category: {new_item.get('category', '')}\n"
        f"Colors: {', '.join(new_item.get('colors', []))}\n"
        f"Style tags: {', '.join(new_item.get('style_tags', []))}\n"
        f"Condition: {new_item.get('condition', '')}\n"
        f"Price: ${new_item.get('price', 0):.2f}"
    )

    trend_section = ""
    if trend_context:
        trend_section = f"\nCurrent fashion trends to keep in mind:\n{trend_context}\n"

    profile_section = ""
    if style_profile:
        pref_styles = style_profile.get("preferred_styles", [])
        pref_colors = style_profile.get("preferred_colors", [])
        if pref_styles or pref_colors:
            style_str = ", ".join(pref_styles[:6]) if pref_styles else "no preference"
            color_str = ", ".join(pref_colors[:5]) if pref_colors else "no preference"
            profile_section = (
                f"\nUser's style preferences (from past searches):\n"
                f"  Preferred styles: {style_str}\n"
                f"  Preferred colors: {color_str}\n"
            )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"You are a thrift-savvy stylist. A user just found this secondhand piece:\n\n"
            f"{item_summary}\n"
            f"{trend_section}"
            f"{profile_section}\n"
            f"They don't have a saved wardrobe yet. Give them 1–2 short paragraphs of "
            f"general styling advice: what kind of pieces pair well, what vibe it suits, "
            f"and how to wear it. Reference any relevant trends if they fit naturally. "
            f"Be specific and casual — like a friend who's into fashion, not a magazine."
        )
    else:
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
            f"{item_summary}\n"
            f"{trend_section}"
            f"{profile_section}\n"
            f"Their current wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest 1–2 complete outfit combinations using the new item and specific "
            f"named pieces from their wardrobe. Be concrete — name the exact wardrobe pieces. "
            f"If any combinations tap into a current trend, mention it briefly. "
            f"Keep it casual and practical, like advice from a stylish friend. "
            f"2–4 sentences per outfit is plenty."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
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


# ── Stretch Tool 4: price_compare ─────────────────────────────────────────────

def price_compare(item: dict, all_listings: list[dict]) -> str:
    """
    Compare an item's price to the median price of all same-category listings.

    Args:
        item:         The listing dict being evaluated.
        all_listings: The full listings dataset (from load_listings()).

    Returns:
        A string verdict with reasoning, e.g.:
        "$18.00 — Great deal — 45% below the $32.50 median for tops."
        Returns a fallback string if no comparable listings exist.
    """
    category = item.get("category", "")
    item_price = item.get("price", 0.0)

    same_cat_prices = [
        l["price"] for l in all_listings
        if l["category"] == category and l["id"] != item.get("id")
    ]

    if not same_cat_prices:
        return f"No comparable listings found for category '{category}'."

    median = statistics.median(same_cat_prices)
    pct_diff = (median - item_price) / median * 100

    if pct_diff >= 20:
        verdict = f"Great deal — {pct_diff:.0f}% below the ${median:.2f} median for {category}"
    elif pct_diff >= 5:
        verdict = f"Fair price — slightly below the ${median:.2f} median for {category}"
    elif pct_diff >= -5:
        verdict = f"Average price — right around the ${median:.2f} median for {category}"
    elif pct_diff >= -20:
        verdict = f"Slightly pricey — a bit above the ${median:.2f} median for {category}"
    else:
        verdict = f"Pricey — {abs(pct_diff):.0f}% above the ${median:.2f} median for {category}"

    return f"${item_price:.2f} — {verdict}."


# ── Stretch Tool 5: get_trending_styles ───────────────────────────────────────

def get_trending_styles(size: str | None = None) -> str:
    """
    Return currently trending fashion styles from mock trend data.

    Args:
        size: Optional size string (reserved for future filtering by size range).
              Currently unused — all trends are returned regardless of size.

    Returns:
        A single-string trend summary suitable for injecting into suggest_outfit().
        Returns "" on failure (soft fail — trends are optional context, not critical).

    Data source: data/trends.json — mock data representing current aesthetics,
    colors, and silhouettes trending on fashion platforms.
    """
    try:
        trends = load_trends()
        trending = ", ".join(trends.get("trending_now", [])[:4])
        colors = ", ".join(trends.get("trending_colors", [])[:3])
        silhouettes = ", ".join(trends.get("trending_silhouettes", [])[:3])
        return (
            f"Trending aesthetics: {trending}. "
            f"Hot colors right now: {colors}. "
            f"Popular silhouettes: {silhouettes}."
        )
    except Exception:
        return ""

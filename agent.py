"""
agent.py

The FitFindr planning loop. Orchestrates all tools in response to a
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

import json
import os

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card, price_compare, get_trending_styles
from utils.data_loader import load_listings
from utils.style_profile import load_style_profile, update_profile_from_session, profile_summary

load_dotenv()


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Use the Groq LLM to extract structured search parameters from the query.

    Returns a dict with keys:
        description (str)       — what the user is looking for
        size        (str|None)  — size filter, or None
        max_price   (float|None)— price ceiling, or None
    """
    prompt = (
        "Extract search parameters from this thrift shopping query. "
        "Return ONLY a JSON object with exactly these keys: "
        '{"description": "<keywords>", "size": "<size or null>", "max_price": <number or null>}. '
        "description should be the item keywords only (no size or price). "
        "size should be null if not mentioned. "
        "max_price should be a number if mentioned, otherwise null.\n\n"
        f"Query: {query}"
    )
    api_key = os.environ.get("GROQ_API_KEY")
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=100,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())
    return {
        "description": parsed.get("description", query),
        "size": parsed.get("size") or None,
        "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
    }


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        # Stretch feature fields
        "retry_note": None,        # set when search is retried with looser constraints
        "price_verdict": None,     # string from price_compare()
        "trend_context": None,     # string from get_trending_styles()
        "style_profile": None,     # dict from load_style_profile()
        "profile_summary": None,   # human-readable summary for the UI
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Planning loop (with stretch features):
      1. Load style profile from disk
      2. Get trending styles
      3. Parse the user query → {description, size, max_price}
      4. Search listings
         4a. [STRETCH] If empty AND size was specified → retry without size filter
         4b. If still empty → set error and return early
      5. Select top result
      6. [STRETCH] Price comparison against category median
      7. Suggest outfit (passes trend context + style profile to LLM)
      8. Create fit card
      9. [STRETCH] Save style profile update from this session
     10. Return session
    """
    session = _new_session(query, wardrobe)

    # Step 1: Load style profile
    profile = load_style_profile()
    session["style_profile"] = profile
    session["profile_summary"] = profile_summary(profile)

    # Step 2: Get trending styles (soft fail — empty string on error)
    session["trend_context"] = get_trending_styles()

    # Step 3: Parse query
    try:
        session["parsed"] = _parse_query(query)
    except Exception as e:
        session["error"] = f"Couldn't parse your query: {e}. Try rephrasing it."
        return session

    p = session["parsed"]

    # Step 4: Search listings
    session["search_results"] = search_listings(
        p["description"], p["size"], p["max_price"]
    )

    # Step 4a: [STRETCH] Retry with looser constraints if size filter eliminated all results
    if not session["search_results"] and p["size"]:
        retry_results = search_listings(p["description"], size=None, max_price=p["max_price"])
        if retry_results:
            session["search_results"] = retry_results
            session["retry_note"] = (
                f"No results found for size {p['size']} — "
                f"retried without size filter and found {len(retry_results)} match(es). "
                f"Showing results in any size."
            )

    # Step 4b: If still empty → error and early exit
    if not session["search_results"]:
        size_note = f", size {p['size']}" if p["size"] else ""
        price_note = f" under ${p['max_price']:.0f}" if p["max_price"] else ""
        session["error"] = (
            f"No listings found for '{p['description']}'{size_note}{price_note}. "
            f"Try removing the size filter or raising your price limit."
        )
        return session

    # Step 5: Select top result
    session["selected_item"] = session["search_results"][0]

    # Step 6: [STRETCH] Price comparison
    all_listings = load_listings()
    session["price_verdict"] = price_compare(session["selected_item"], all_listings)

    # Step 7: Suggest outfit — passes trend context and style profile to LLM
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
        trend_context=session["trend_context"],
        style_profile=session["style_profile"],
    )

    # Step 8: Create fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 9: [STRETCH] Persist style signals for next session
    update_profile_from_session(session)
    session["profile_summary"] = profile_summary(load_style_profile())

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
        print(f"Price verdict: {session['price_verdict']}")
        print(f"Trends: {session['trend_context']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")
        print(f"\nProfile after session: {session['profile_summary']}")

    print("\n\n=== Retry path: impossible size ===\n")
    session2 = run_agent(
        query="vintage graphic tee size XXXL under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session2["retry_note"]:
        print(f"Retry note: {session2['retry_note']}")
    if session2["error"]:
        print(f"Error: {session2['error']}")
    elif session2["selected_item"]:
        print(f"Found after retry: {session2['selected_item']['title']}")

    print("\n\n=== No-results path ===\n")
    session3 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session3['error']}")
    print(f"fit_card is None: {session3['fit_card'] is None}")

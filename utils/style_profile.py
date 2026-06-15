"""
Persistent style profile — saves and loads user style preferences across sessions.
Stored as JSON at data/style_profile.json.
"""

import json
import os

_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "style_profile.json")

_EMPTY: dict = {
    "preferred_styles": [],
    "preferred_colors": [],
    "recent_items": [],
    "notes": "",
}


def load_style_profile() -> dict:
    """Load the saved style profile, or return an empty one if none exists yet."""
    if not os.path.exists(_PROFILE_PATH):
        return dict(_EMPTY)
    try:
        with open(_PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return dict(_EMPTY)


def save_style_profile(profile: dict) -> None:
    """Write the profile dict to disk."""
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def update_profile_from_session(session: dict) -> None:
    """
    Merge style signals from a completed session into the saved profile.
    Pulls style_tags and colors from the selected item and tracks recent items.
    Called at the end of a successful run_agent() call.
    """
    item = session.get("selected_item")
    if not item:
        return

    profile = load_style_profile()

    for tag in item.get("style_tags", []):
        if tag not in profile["preferred_styles"]:
            profile["preferred_styles"].append(tag)

    for color in item.get("colors", []):
        if color not in profile["preferred_colors"]:
            profile["preferred_colors"].append(color)

    title = item.get("title", "")
    recent = profile.get("recent_items", [])
    if title and title not in recent:
        recent.insert(0, title)
        profile["recent_items"] = recent[:5]

    save_style_profile(profile)


def clear_style_profile() -> None:
    """Reset the profile to empty — used by the 'Clear profile' button in the UI."""
    save_style_profile(dict(_EMPTY))


def profile_summary(profile: dict) -> str:
    """Return a human-readable summary of the saved profile for display in the UI."""
    has_styles = bool(profile.get("preferred_styles"))
    has_colors = bool(profile.get("preferred_colors"))
    has_recent = bool(profile.get("recent_items"))

    if not any([has_styles, has_colors, has_recent]):
        return "No style profile saved yet — your preferences will be remembered after your first search."

    lines = ["Style memory active:"]
    if has_styles:
        lines.append(f"  Styles you like: {', '.join(profile['preferred_styles'][:6])}")
    if has_colors:
        lines.append(f"  Colors you gravitate toward: {', '.join(profile['preferred_colors'][:5])}")
    if has_recent:
        lines.append(f"  Recently browsed: {', '.join(profile['recent_items'])}")
    return "\n".join(lines)

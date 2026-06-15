# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads the full mock listings dataset, applies optional hard filters (price ceiling, size substring), scores each remaining listing by keyword overlap between the `description` tokens and each listing's title + description + category + style_tags fields, drops zero-score listings, and returns the survivors sorted by score descending (best match first).

**Input parameters:**
- `description` (str): Free-text keywords describing what the user wants (e.g., `"vintage graphic tee"`). Each whitespace-separated token is checked for case-insensitive membership across the listing's title, description, category, and each tag in style_tags. The score for a listing is the total count of matching tokens.
- `size` (str | None): Size string to filter on (e.g., `"M"`). If not None, only listings where `listing["size"].lower()` contains `size.lower()` are kept. This means `"M"` matches `"S/M"` and `"XL (oversized)"` does not.
- `max_price` (float | None): Maximum price, inclusive (e.g., `30.0`). If not None, only listings where `listing["price"] <= max_price` are kept. Applied before scoring.

**What it returns:**
A `list[dict]` sorted by relevance score, highest first. Each dict contains exactly these fields from the dataset:
- `id` (str) — e.g., `"lst_002"`
- `title` (str) — e.g., `"Y2K Baby Tee — Butterfly Print"`
- `description` (str) — the full listing description text
- `category` (str) — one of: `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[str]) — e.g., `["y2k", "vintage", "graphic tee"]`
- `size` (str) — e.g., `"S/M"`
- `condition` (str) — one of: `excellent`, `good`, `fair`
- `price` (float) — e.g., `18.0`
- `colors` (list[str]) — e.g., `["white", "pink", "purple"]`
- `brand` (str | None) — may be null
- `platform` (str) — one of: `depop`, `thredUp`, `poshmark`

Returns `[]` (empty list) if no listing clears the filters or scores > 0. Never raises an exception.

**What happens if it fails or returns nothing:**
The agent checks `if not session["search_results"]` immediately after the call. If true, it sets:
```
session["error"] = "No listings found for '{description}' (size={size}, max ${max_price}). Try removing the size filter or raising your price limit."
```
and returns the session immediately. `suggest_outfit` and `create_fit_card` are never called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM (`llama-3.3-70b-versatile`) with a prompt constructed from the new item's details and the user's wardrobe. If the wardrobe has items, the prompt asks for 1–2 specific outfit combinations naming actual wardrobe pieces. If the wardrobe is empty, the prompt asks for general styling advice: what archetypes this item suits, what generic pieces pair well, what vibe it gives.

**Input parameters:**
- `new_item` (dict): A listing dict as returned by `search_listings`. The prompt uses: `title`, `category`, `colors`, `style_tags`, `condition`, and `price`.
- `wardrobe` (dict): A dict with key `"items"` whose value is a list of wardrobe item dicts. Each wardrobe item has: `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str | None). The list may be empty.

**What it returns:**
A non-empty string — either 1–2 paragraph-style outfit suggestions naming specific wardrobe pieces (populated wardrobe), or a 1-paragraph general styling note (empty wardrobe). Never returns an empty string; error fallback is a string, not an exception.

**What happens if it fails or returns nothing:**
- Empty wardrobe (`wardrobe["items"] == []`): the tool does NOT error — it branches to a different LLM prompt asking for general styling advice. This is expected behavior, not a failure.
- LLM API exception: caught with `try/except`, returns the fallback string `"Couldn't generate outfit suggestions right now. Try pairing this with neutral basics."` The agent stores this fallback in `session["outfit_suggestion"]` and continues to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM at temperature `0.9` to generate a 2–4 sentence Instagram/TikTok-style caption. The caption must mention the item name, price, and platform naturally (each exactly once) and capture the outfit vibe in specific, casual language — the kind a real person would post, not a product description.

**Input parameters:**
- `outfit` (str): The full outfit suggestion string from `suggest_outfit`. Passed to the LLM as context so the caption reflects the actual styling, not generic text.
- `new_item` (dict): The listing dict. The LLM prompt extracts `new_item["title"]`, `new_item["price"]`, and `new_item["platform"]` to include in the caption.

**What it returns:**
A 2–4 sentence string with caption energy — lowercase-heavy, conversational, emoji optional. Different for different inputs because temperature is `0.9`. Returns a plain error string (no exception) in two failure cases:
- `outfit` is empty or whitespace → `"No outfit suggestion available — can't generate a fit card."`
- LLM call raises an exception → `"Fit card unavailable right now."`

**What happens if it fails or returns nothing:**
Both failure cases return a string. The agent always stores whatever `create_fit_card` returns into `session["fit_card"]` without checking it — the UI will display whatever is there. No exception propagates out of this tool.

---

### Stretch Tool 4: price_compare

**What it does:**
Compares a listing's price to the median price of all other listings in the same category. Returns a verdict string with the percentage difference and the category median so the user can judge whether the find is a deal.

**Input parameters:**
- `item` (dict): The selected listing dict. Uses `item["price"]`, `item["category"]`, and `item["id"]` (to exclude itself from the comparison set).
- `all_listings` (list[dict]): The full listings dataset from `load_listings()`. Filtered to same-category items before computing the median.

**What it returns:**
A single string, e.g.: `"$18.00 — Great deal — 45% below the $32.50 median for tops."` Thresholds: ≥20% below → "Great deal", 5–20% below → "Fair price", ±5% → "Average price", 5–20% above → "Slightly pricey", >20% above → "Pricey". Returns a fallback string if no comparable listings exist — never raises.

**What happens if it fails or returns nothing:**
Returns `"No comparable listings found for category '{category}'."` No exception. Stored in `session["price_verdict"]` and shown in the extras panel.

---

### Stretch Tool 5: get_trending_styles

**What it does:**
Loads `data/trends.json` (mock trend data representing current fashion platform trends) and returns a formatted summary string of trending aesthetics, colors, and silhouettes. This string is injected into the `suggest_outfit` prompt so the LLM can reference current trends when building outfit combinations.

**Input parameters:**
- `size` (str | None): Reserved for future size-range filtering. Currently unused — all trends returned regardless of size.

**What it returns:**
A single string, e.g.: `"Trending aesthetics: quiet luxury, 90s grunge revival, Y2K throwback, gorpcore. Hot colors right now: chocolate brown, burgundy, cream. Popular silhouettes: oversized blazers, wide-leg trousers, midi skirts."` Returns `""` on failure (soft fail — trends are optional context, not critical path).

**Data source:** `data/trends.json` — mock data simulating what a real fashion platform scraper would return. Contains `trending_now` (aesthetics), `trending_colors`, and `trending_silhouettes` fields.

**What happens if it fails or returns nothing:**
Returns `""` silently. The planning loop checks `if trend_context` before passing it to `suggest_outfit`, so an empty string means no trend context is added to the prompt. The interaction continues normally.

---

### Stretch Feature: Style Profile Memory

**What it does:**
Persists style signals (style tags and colors from items the user has browsed) to `data/style_profile.json` after each successful interaction. On the next query, the saved profile is loaded and passed to `suggest_outfit` as additional context so the LLM can reference the user's established preferences without re-entry.

**Storage:** `data/style_profile.json` — flat JSON with keys `preferred_styles` (list), `preferred_colors` (list), `recent_items` (list, max 5), `notes` (str). Updated by `utils/style_profile.py:update_profile_from_session()` at the end of each successful `run_agent()` call.

**What happens if profile is missing or corrupt:** `load_style_profile()` returns the empty profile dict — the interaction continues without preference context.

---

### Stretch Feature: Retry Logic with Fallback

**What it does:**
If `search_listings` returns an empty list AND the query included a size filter, the planning loop automatically retries without the size constraint. The user sees a note in the listing panel explaining what was adjusted.

**When it triggers:** Only when `p["size"]` is not None AND first search returned `[]`. If the retry also returns `[]`, the normal error path is taken.

**What the user sees:** `"⚠️ No results found for size XXXL — retried without size filter and found 20 match(es). Showing results in any size."` in the listing panel.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a linear sequence with two conditional branches (retry on empty results, and early exit if retry also fails). Written as pseudocode:

```
def run_agent(query, wardrobe):
    session = _new_session(query, wardrobe)

    # Step 1 — Load style profile from disk
    session["style_profile"] = load_style_profile()

    # Step 2 — Get trending styles (soft fail: returns "" on error)
    session["trend_context"] = get_trending_styles()

    # Step 3 — Parse query
    parsed = llm_parse_query(query)
    session["parsed"] = parsed

    # Step 4 — Search listings
    results = search_listings(parsed["description"], parsed["size"], parsed["max_price"])
    session["search_results"] = results

    # Step 4a — [STRETCH] Retry without size filter if size caused empty results
    if not results and parsed["size"]:
        retry = search_listings(parsed["description"], size=None, max_price=parsed["max_price"])
        if retry:
            session["search_results"] = retry
            session["retry_note"] = f"No results for size {parsed['size']} — retried without size filter, found {len(retry)} match(es)."

    # Step 4b — If still empty, early exit
    if not session["search_results"]:
        session["error"] = f"No listings found for '{parsed['description']}'. Try loosening filters."
        return session

    # Step 5 — Select top result
    session["selected_item"] = session["search_results"][0]

    # Step 6 — [STRETCH] Price comparison
    session["price_verdict"] = price_compare(session["selected_item"], load_listings())

    # Step 7 — Suggest outfit (passes trend context + style profile)
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], wardrobe,
        trend_context=session["trend_context"],
        style_profile=session["style_profile"],
    )

    # Step 8 — Create fit card
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])

    # Step 9 — [STRETCH] Persist style signals for next session
    update_profile_from_session(session)

    return session
```

The loop has two branches: the retry branch (Step 4a) loosens the size constraint and continues; the early-exit branch (Step 4b) sets an error and returns if results are still empty after retry. Steps 6–9 always run when a result exists.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in the `session` dict created by `_new_session(query, wardrobe)`. No globals, no class instances, no re-prompting the user between steps. The dict is passed back to the caller at the end.

| Field | Set by | Consumed by |
|---|---|---|
| `session["query"]` | `_new_session` | `llm_parse_query` |
| `session["parsed"]` | query parsing step | `search_listings` call |
| `session["search_results"]` | `search_listings` | empty-check branch; `results[0]` selection |
| `session["selected_item"]` | `results[0]` assignment | `suggest_outfit`, `create_fit_card`, and Gradio UI |
| `session["wardrobe"]` | `_new_session` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | Gradio UI (fit card panel) |
| `session["error"]` | empty-results branch | Gradio `handle_query` (shows error in listing panel) |

The user never has to repeat information: the item found in Step 2 flows directly into Steps 4 and 5 as `session["selected_item"]` without any re-input.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | Returns `[]` — no listing passes the price/size/keyword filters | Agent sets `session["error"] = "No listings found for '{description}' (size={size}, max ${max_price}). Try removing the size filter or raising your price limit."` and returns immediately. `suggest_outfit` and `create_fit_card` are never called. |
| `search_listings` | Returns `[]` but a size filter was specified | **[STRETCH]** Agent retries `search_listings` without the size parameter. If retry finds results, sets `session["retry_note"]` and continues. If retry also returns `[]`, falls through to the error path above. |
| `suggest_outfit` | `wardrobe["items"]` is empty | Tool branches to a different LLM prompt asking for general styling advice instead of named wardrobe pairings. Returns a non-empty string; agent continues to `create_fit_card` normally. |
| `suggest_outfit` | LLM API call raises an exception | Tool catches the exception and returns `"Couldn't generate outfit suggestions right now. Try pairing this with neutral basics."` Agent stores this in `session["outfit_suggestion"]` and continues. |
| `create_fit_card` | `outfit` is empty or whitespace-only | Tool returns `"No outfit suggestion available — can't generate a fit card."` without calling the LLM. Agent stores this in `session["fit_card"]`. |
| `create_fit_card` | LLM API call raises an exception | Tool catches the exception and returns `"Fit card unavailable right now."` Agent stores this in `session["fit_card"]`. |
| `get_trending_styles` | `trends.json` missing or malformed | Returns `""` silently. `suggest_outfit` receives an empty `trend_context` and produces a normal outfit suggestion without trend references. |
| `price_compare` | No same-category listings in dataset | Returns `"No comparable listings found for category '{category}'."` Stored in `session["price_verdict"]` and shown in extras panel. |
| `load_style_profile` | Profile file missing or corrupt JSON | Returns empty profile dict `{"preferred_styles": [], ...}`. `suggest_outfit` receives no preference context; session proceeds normally. |

---

## Architecture

```
User query (natural language)
        │
        ▼
run_agent(query, wardrobe)
        │
        ├─► [Step 1] load_style_profile()
        │           └── session["style_profile"] = {preferred_styles, colors, recent_items}
        │
        ├─► [Step 2] get_trending_styles()        ← STRETCH
        │           └── session["trend_context"] = "Trending: quiet luxury, Y2K..."
        │
        ├─► [Step 3] llm_parse_query(query)
        │           └── session["parsed"] = {description, size, max_price}
        │
        ├─► [Step 4] search_listings(description, size, max_price)
        │           │
        │           ├── results == [] AND size specified?
        │           │       └──► [STRETCH] retry without size filter
        │           │               ├── retry found results?
        │           │               │       └── session["retry_note"] = "retried..."
        │           │               └── retry still empty?
        │           │                       └──► session["error"] → EARLY EXIT
        │           │
        │           └── results == [] (no size to retry)?
        │                   └──► session["error"] → EARLY EXIT
        │
        ├─► [Step 5] session["selected_item"] = results[0]
        │
        ├─► [Step 6] price_compare(selected_item, all_listings)    ← STRETCH
        │           └── session["price_verdict"] = "$18 — Great deal..."
        │
        ├─► [Step 7] suggest_outfit(item, wardrobe, trend_context, style_profile)
        │           │
        │           ├── wardrobe empty? → LLM: general styling advice
        │           └── wardrobe has items? → LLM: named wardrobe pieces + trend refs
        │           └── session["outfit_suggestion"] = "<LLM response>"
        │
        ├─► [Step 8] create_fit_card(outfit_suggestion, selected_item)
        │           └── session["fit_card"] = "<caption at temp=0.9>"
        │
        ├─► [Step 9] update_profile_from_session(session)          ← STRETCH
        │           └── saves style tags + colors to data/style_profile.json
        │
        └─► return session
                    │
                    ▼
            handle_query() in app.py
                    │
        ┌───────────┼──────────────┬──────────────────────┐
        ▼           ▼              ▼                       ▼
  listing panel  outfit panel  fit card panel      extras panel
  + retry note   (trend-aware) (caption)          price + trends
  (or error msg)                                  + profile status
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 — `search_listings`:**
- Input to Claude: the Tool 1 block from this file (inputs with types and meanings, scoring logic description, return format listing all fields, failure mode with exact error string).
- Prompt: "Implement `search_listings(description, size, max_price)` in tools.py. Use `load_listings()` from utils/data_loader.py. Filter by max_price (price <= max_price) and size (case-insensitive substring match on listing['size']). Score each listing by counting how many whitespace-split tokens from description appear (case-insensitive) in the combined text of title + description + category + each style_tag. Drop zero-score listings. Return the list sorted by score descending. Return [] on no match. No exceptions."
- Verification: Run 3 manual tests before trusting: (1) `search_listings("vintage graphic tee")` — expect multiple results, all with style_tags containing "vintage" or "graphic"; (2) `search_listings("ballgown", size="XXS", max_price=5.0)` — expect `[]`; (3) `search_listings("jacket", size="M", max_price=50.0)` — expect only size-M listings under $50.

**Tool 2 — `suggest_outfit`:**
- Input to Claude: the Tool 2 block from this file (both input parameter descriptions with exact field names from wardrobe schema, two-branch logic, fallback string for LLM failure).
- Prompt: "Implement `suggest_outfit(new_item, wardrobe)` in tools.py using the Groq client. If `wardrobe['items']` is empty, call the LLM asking for general styling advice for the item (use title, category, colors, style_tags from new_item). If wardrobe has items, format each wardrobe item's name, category, and style_tags into a list and ask the LLM for 1–2 specific outfit combinations naming actual wardrobe pieces. Catch any exception and return the fallback string."
- Verification: (1) Run with `get_empty_wardrobe()` — response must be non-empty and not mention specific wardrobe piece names; (2) Run with `get_example_wardrobe()` — response must name at least one wardrobe piece (e.g., "baggy straight-leg jeans").

**Tool 3 — `create_fit_card`:**
- Input to Claude: the Tool 3 block from this file (caption style requirements, temperature=0.9, both failure-mode return strings, exact fields to pull from new_item).
- Prompt: "Implement `create_fit_card(outfit, new_item)` in tools.py. Guard: if outfit is empty/whitespace, return the fallback string immediately. Otherwise call Groq at temperature=0.9 with a prompt that gives it the outfit suggestion and the item's title, price, and platform, and asks for a 2–4 sentence casual OOTD caption mentioning each once. Catch any exception and return the LLM-error fallback string."
- Verification: Run on two different items and compare outputs — they should sound meaningfully different. Check that price and platform appear in each caption. Check that the empty-outfit guard triggers by passing `outfit=""`.

**Milestone 4 — Planning loop and state management:**

- Input to Claude: the Planning Loop pseudocode block and the Architecture diagram from this file, plus the `_new_session` function signature from agent.py.
- Prompt: "Implement `run_agent(query, wardrobe)` in agent.py following the pseudocode in planning.md exactly. For Step 1, use the Groq LLM to parse the query into a dict with keys description (str), size (str or None), max_price (float or None). Steps 2–5 follow the pseudocode. Use the session dict fields defined in `_new_session`. The early-exit after empty search_results must set session['error'] and return before calling suggest_outfit."
- Verification: Run `python agent.py` directly. Happy path (`"vintage graphic tee under $30"` + example wardrobe) should print a non-empty fit_card and no error. No-results path (`"designer ballgown size XXS under $5"`) should print an error message and have `session["fit_card"] == None`.

---

## A Complete Interaction (Step by Step)

**FitFindr in 2–3 sentences:**
FitFindr takes a natural language thrift query, parses it into structured search parameters, filters a mock dataset by price and size and keyword relevance, then passes the top result to an LLM that suggests specific outfits using the user's wardrobe, and finally generates a shareable OOTD caption from the outfit. Every tool's output flows into the next tool through a single session dict — no re-prompting the user. If the search returns no results, the agent surfaces a helpful error message and stops immediately rather than passing empty data to the outfit or caption tools.

**`get_example_wardrobe()` vs `get_empty_wardrobe()`:**
`get_example_wardrobe()` returns a wardrobe dict with `items` containing 10 pre-populated pieces (dark wash baggy jeans, white ribbed tank, platform sneakers, etc.) — used for the main happy-path flow and for testing that `suggest_outfit` references specific named pieces. `get_empty_wardrobe()` returns `{"items": []}` — used to test the fallback branch in `suggest_outfit` (general styling advice instead of named combinations) and to simulate a brand-new user who hasn't added anything to their closet yet.

---

**Example user query:** "I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."

**Step 1 — Parse query:**
`run_agent` calls the Groq LLM with a system prompt: "Extract a JSON object with keys: description (str), size (str or null), max_price (float or null)." The LLM returns:
```json
{"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
```
Stored in `session["parsed"]`.

**Step 2 — Search listings:**
Calls `search_listings("vintage graphic tee", size="M", max_price=30.0)`.
- Price filter: keeps only listings where `price <= 30.0`. From the dataset this includes items like the Y2K Baby Tee ($18), the Oversized Flannel ($22), and the Faded Band Tee ($24) but drops the Track Jacket ($45) and the Levi's ($38).
- Size filter: from the remaining, keeps only listings where `size.lower()` contains `"m"`. The Y2K Baby Tee has size `"S/M"` → kept. The Flannel is `"XL (oversized)"` → dropped (no "m" in lowercase).
- Keyword scoring: tokens are `["vintage", "graphic", "tee"]`. The Y2K Baby Tee has style_tags `["y2k", "vintage", "graphic tee"]` — matches "vintage" (1) + "graphic" (1) = score 2. Ranked first.
- Returns: `[Y2K Baby Tee dict, ...]` — non-empty, so no early exit.
- `session["search_results"] = [<Y2K Baby Tee>, ...]`

**Step 3 — Select item:**
`session["selected_item"] = session["search_results"][0]` → the Y2K Baby Tee dict (`id: "lst_002"`, price: 18.0, platform: "depop").

**Step 4 — Suggest outfit:**
Calls `suggest_outfit(new_item=<Y2K Baby Tee>, wardrobe=get_example_wardrobe())`.
Wardrobe has 10 items → populated branch. LLM prompt includes item details (white/pink baby tee, y2k/vintage/graphic tags) and wardrobe items formatted as a list. LLM returns:
> "Pair this butterfly baby tee with your baggy straight-leg dark wash jeans and white platform sneakers for a classic Y2K streetwear look — tuck just the front corner for shape. For a softer vibe, try it with your wide-leg khaki trousers and chunky sandals."

`session["outfit_suggestion"]` = above string.

**Step 5 — Create fit card:**
Calls `create_fit_card(outfit=<suggestion>, new_item=<Y2K Baby Tee>)`.
LLM at temperature 0.9 receives the outfit text and item info. Returns:
> "thrifted this y2k butterfly tee off depop for $18 and it was literally made for my baggy jeans 🦋 tucked the front corner and called it a full look, details in my stories"

`session["fit_card"]` = above caption.

**Step 6 — Return session:**
`run_agent` returns the completed session dict. `session["error"]` is None.

**Final output to user (in Gradio):**
- **Top listing panel:**
  ```
  Y2K Baby Tee — Butterfly Print
  Price: $18.00 | Platform: depop | Size: S/M | Condition: excellent
  Style: y2k, vintage, graphic tee, cottagecore
  Colors: white, pink, purple
  ```
- **Outfit idea panel:** The `suggest_outfit` string naming jeans, sneakers, and khakis
- **Fit card panel:** The caption string, ready to copy-paste

**Error path (alternate):** Query `"designer ballgown size XXS under $5"` → `search_listings` returns `[]` → `session["error"] = "No listings found for 'designer ballgown' (size=XXS, max $5.0). Try removing the size filter or raising your price limit."` → session returned immediately → Gradio shows the error in the listing panel; outfit and fit card panels are blank.

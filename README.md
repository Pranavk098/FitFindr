# FitFindr

A multi-tool AI agent that helps users find secondhand pieces and figure out how to style them. Built with Groq (llama-3.3-70b-versatile), a mock thrift listings dataset, and a Gradio web interface.

---

## Setup

```bash
# 1. Clone and enter the repo
git clone <your-fork-url>
cd ai201-project2-fitfindr-starter

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
.venv\Scripts\activate             # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your Groq API key (free at console.groq.com)
echo "GROQ_API_KEY=your_key_here" > .env

# 5. Run the app
python app.py
```

Open the URL shown in your terminal (usually `http://localhost:7860`).

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Free-text keywords (e.g., `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter on; `None` skips filtering. Case-insensitive substring match, so `"M"` matches `"S/M"` |
| `max_price` | `float \| None` | Price ceiling (inclusive); `None` skips filtering |

**Returns:** `list[dict]` — matching listing dicts sorted by keyword relevance (best match first). Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` on no match — never raises.

**How it scores:** Splits `description` into tokens, counts how many appear in each listing's combined title + description + category + style_tags text. Listings with zero matches are dropped. Filters are applied before scoring (price, then size).

**Purpose:** Turns a natural language query into a ranked shortlist of real listings from the mock dataset without calling an LLM.

---

### `suggest_outfit(new_item, wardrobe)`

| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A listing dict — the item the user is considering |
| `wardrobe` | `dict` | Dict with key `"items"` containing a list of wardrobe item dicts (each has `name`, `category`, `colors`, `style_tags`, `notes`). May be empty. |

**Returns:** `str` — 1–2 outfit suggestions. If the wardrobe has items, the response names specific wardrobe pieces. If the wardrobe is empty, the response gives general styling advice for the item type and vibe.

**Purpose:** Uses the Groq LLM to translate a listing + wardrobe into actionable, personalized outfit ideas.

---

### `create_fit_card(outfit, new_item)`

| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit` |
| `new_item` | `dict` | The listing dict — used to pull `title`, `price`, and `platform` |

**Returns:** `str` — a 2–4 sentence Instagram/TikTok-style OOTD caption mentioning the item name, price, and platform each once. Generated at LLM temperature `0.9` so output varies for different inputs. Returns a plain error string (no exception) if `outfit` is empty.

**Purpose:** Converts the outfit suggestion into a shareable, human-sounding caption — the final output the user can actually copy and post.

---

## Planning Loop

The agent uses a **sequential loop with one conditional branch** — it does not call all three tools unconditionally.

```
run_agent(query, wardrobe)
  │
  ├─ Step 1: LLM parses query → {description, size, max_price}
  │
  ├─ Step 2: search_listings(description, size, max_price)
  │     │
  │     ├─ results == [] ?
  │     │      └─► set session["error"], return early   ← BRANCH (suggest_outfit never called)
  │     │
  │     └─ results non-empty → session["search_results"]
  │
  ├─ Step 3: session["selected_item"] = results[0]
  │
  ├─ Step 4: suggest_outfit(selected_item, wardrobe) → session["outfit_suggestion"]
  │
  ├─ Step 5: create_fit_card(outfit_suggestion, selected_item) → session["fit_card"]
  │
  └─ Step 6: return session
```

**The key decision:** After `search_listings` runs, the loop checks `if not results`. If true, it sets an error message and returns the session immediately — `suggest_outfit` and `create_fit_card` are never called with empty input. If results exist, the loop proceeds linearly through Steps 3–5 without further branching (because `suggest_outfit` handles its own empty-wardrobe case internally).

**Query parsing:** The user's raw natural language query (e.g., `"vintage graphic tee under $30, size M"`) is parsed by the LLM at `temperature=0.0` into a structured dict with `description`, `size`, and `max_price` fields. This handles natural phrasing like `"under thirty bucks"` or `"medium-ish"` better than regex.

---

## State Management

All state lives in a single `session` dict created at the start of each `run_agent` call. No globals. No re-prompting the user between steps.

| Field | Set by | Used by |
|---|---|---|
| `session["query"]` | `_new_session` | `_parse_query` |
| `session["parsed"]` | `_parse_query` | `search_listings` call |
| `session["search_results"]` | `search_listings` | empty-check branch; `results[0]` selection |
| `session["selected_item"]` | `results[0]` assignment | `suggest_outfit`, `create_fit_card`, Gradio UI |
| `session["wardrobe"]` | `_new_session` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` | Gradio UI (fit card panel) |
| `session["error"]` | empty-results branch | Gradio `handle_query` (shows in listing panel) |

The item found in Step 2 flows directly into Steps 4 and 5 as `session["selected_item"]` — no repeated look-ups, no user re-entry.

---

## Error Handling

### `search_listings` — no results

**Failure mode:** The price/size/keyword filters eliminate all listings.

**Agent response:** Sets `session["error"]` to a specific, actionable message and returns the session immediately. `suggest_outfit` is **never called**.

**Example from testing:**
```
query: "designer ballgown size XXS under 5 dollars"
→ session["error"]: "No listings found for 'designer ballgown', size XXS under $5.
   Try removing the size filter or raising your price limit."
→ session["fit_card"]: None
→ session["outfit_suggestion"]: None
```

---

### `suggest_outfit` — empty wardrobe

**Failure mode:** `wardrobe["items"]` is an empty list (new user with no saved closet).

**Agent response:** The tool branches to a different LLM prompt asking for general styling advice — what pieces pair well, what vibe the item suits, how to wear it. Returns a non-empty string. The agent continues to `create_fit_card` normally.

**Example from testing:**
```
input: Y2K Baby Tee + empty wardrobe
→ "Oh my gosh, I'm obsessed with this Y2K baby tee... pair it with high-waisted
   jeans or a flowy skirt... add layered pieces like a cardigan or a denim jacket..."
→ no exception raised, non-empty string returned
```

---

### `create_fit_card` — empty outfit string

**Failure mode:** `outfit` is an empty string or whitespace-only.

**Agent response:** Returns the string `"No outfit suggestion available — can't generate a fit card."` immediately, without calling the LLM. Stored in `session["fit_card"]` like any other result.

**Example from testing:**
```python
create_fit_card("", results[0])
→ "No outfit suggestion available — can't generate a fit card."
```

---

## AI Usage

### Instance 1 — Implementing `search_listings`

**What I gave Claude:** The Tool 1 spec block from `planning.md` — input parameters with types and meanings, the scoring logic (token overlap across title + description + category + style_tags), return format listing all fields, and the failure mode with exact error behavior.

**What it produced:** A working implementation that loaded listings, applied price and size filters, scored by token overlap, and returned sorted results.

**What I changed:** The generated code used `description.lower() in blob` as a full-string check rather than splitting into tokens. This meant `"vintage graphic tee"` only matched listings containing that exact phrase, missing listings that had "vintage" and "graphic tee" in separate fields. I revised scoring to split on whitespace and check each token individually, giving partial matches the correct ranking behavior.

---

### Instance 2 — Implementing the planning loop (`run_agent`)

**What I gave Claude:** The Planning Loop pseudocode block and Architecture ASCII diagram from `planning.md`, plus the `_new_session` function signature from `agent.py`.

**What it produced:** A `run_agent` implementation with the correct 6-step structure and the early-exit branch after empty search results.

**What I changed:** The generated code inlined query parsing as a simple `str.split()` call. I replaced this with a separate `_parse_query` function that calls Groq at `temperature=0.0` to extract `description`, `size`, and `max_price` from natural language — which handles phrases like `"under thirty dollars"` that string splitting would miss. I also added JSON code-fence stripping because the LLM sometimes wraps its output in markdown backticks.

---

## Running Tests

```bash
pytest tests/ -v
```

15 tests covering all three tools and all failure modes. `search_listings` tests are pure Python (no LLM, no network). The `suggest_outfit` and `create_fit_card` tests require a valid `GROQ_API_KEY`.

---

## Project Structure

```
.
├── agent.py          # Planning loop: run_agent(), _parse_query(), _new_session()
├── app.py            # Gradio interface: handle_query() + pre-built layout
├── tools.py          # Three tool implementations
├── planning.md       # Design spec: tools, loop, state, error handling, diagram
├── data/
│   ├── listings.json         # 40 mock thrift listings
│   └── wardrobe_schema.json  # Wardrobe schema + example/empty wardrobe
├── utils/
│   └── data_loader.py        # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
└── tests/
    └── test_tools.py         # 15 pytest tests for all tools and failure modes
```

---

## Spec Reflection

The planning I did upfront paid off most in the error handling design. By deciding before writing code that `suggest_outfit` should have two internal branches (rather than failing or requiring the caller to check the wardrobe first), the planning loop stayed simple — it never has to handle a "wardrobe was empty" error because the tool itself absorbs that case and always returns a usable string. The most surprising thing I changed from the original spec: the query parser. I initially wrote in `planning.md` that I might use regex for price/size extraction, but switched to an LLM call at `temperature=0.0` after realizing regex would miss natural phrasing variations. The tradeoff is an extra API call per query, but the reliability improvement is worth it.

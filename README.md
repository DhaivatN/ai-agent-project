# FitFindr 🛍️

FitFindr is a small multi-tool AI agent that helps you search secondhand fashion listings, figure out how a thrifted piece fits into your wardrobe, and generate a shareable “fit card” caption. It’s built as a hands-on exploration of **agentic AI** — not just prompting an LLM, but orchestrating multiple tools, passing state, handling retries, and staying useful when things go wrong.

---

## What the Agent Does

Given a natural language query like:

> “I’m looking for a vintage graphic tee under $30, size M. How would I style it?”

FitFindr:

1. **Searches** a mock listings dataset for matching thrift items.
2. **Picks** a top candidate and checks whether the price looks like a good deal.
3. **Suggests** one or two outfits using the item and your wardrobe.
4. **Generates** a short, social-friendly “fit card” caption you could post.

It also:

- **Remembers** lightweight style preferences across runs (extra credit).
- **Retries** search once with relaxed constraints if nothing is found (extra credit).

---

## Tools (Agent Capabilities)

FitFindr is built around six tools

### 1. `search_listings(description, size, max_price)`

**Purpose:**  
Search the mock listings dataset for items matching the user’s description, optional size, and optional price ceiling.

**Inputs:**

- `description: str` – query text (e.g. `"vintage graphic tee"`).
- `size: str | None` – optional size filter (e.g. `"M"`).
- `max_price: float | None` – optional maximum price.

**Output:**

- `list[dict]` – matching listing dicts, sorted by relevance and price.

Each listing dict includes: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

**Error / failure behavior:**

- Returns `[]` when nothing matches (no exception).
- The agent then decides whether to retry search with relaxed constraints or stop with a helpful error.

---

### 2. `suggest_outfit(new_item, wardrobe)`

**Purpose:**  
Given a specific thrift item and the user’s wardrobe, suggest 1–2 outfits.

**Inputs:**

- `new_item: dict` – listing selected from `search_listings`.
- `wardrobe: dict` – wardrobe dict with an `items` list (from `get_example_wardrobe()` or `get_empty_wardrobe()`).

**Output:**

- `str` – one or two outfit ideas, describing pieces and the overall vibe.

**Error / failure behavior:**

- If `new_item` is missing, returns a clear error string.
- If the wardrobe is empty, returns **general styling advice** instead of failing.
- If the LLM call fails, falls back to a deterministic suggestion based on the item and wardrobe.

---

### 3. `create_fit_card(outfit, new_item)`

**Purpose:**  
Turn the outfit suggestion and thrift item into a 2–4 sentence social caption (“fit card”).

**Inputs:**

- `outfit: str` – text from `suggest_outfit`.
- `new_item: dict` – listing dict for the thrifted item.

**Output:**

- `str` – short, casual caption mentioning the item, price, platform, and outfit vibe.

**Error / failure behavior:**

- If `outfit` is empty/whitespace, returns a descriptive error string.
- If the LLM call fails, uses a deterministic fallback caption.
- Handles missing item fields by degrading gracefully.

---

### 4. `compare_listing_value(selected_item, all_listings)` (Extra Credit)

**Purpose:**  
Estimate whether the selected item’s price is a **good deal**, **fair price**, or **overpriced** by comparing it to similar items in the dataset.

**Inputs:**

- `selected_item: dict` – the chosen listing.
- `all_listings: list[dict]` – full dataset from `load_listings()`.

**Output:**

A dict like:

```python
{
  "price_assessment": "good deal" | "fair price" | "overpriced" | "unknown",
  "reasoning": str,
  "comparable_count": int,
  "average_comparable_price": float | None,
}
```

**Error / failure behavior:**

- If there’s no numeric price or not enough comparables, returns `"unknown"` with an explanation and does **not** block the rest of the agent.

---

### 5. `save_style_profile(user_id, preferences)` (Extra Credit)

**Purpose:**  
Persist lightweight style preferences between runs (e.g. liked tags, colors, last category).

**Inputs:**

- `user_id: str` – identifier (e.g. `"demo_user"`).
- `preferences: dict` – extracted preferences like:

  ```python
  {
    "last_query": "...",
    "liked_style_tags": [...],
    "liked_colors": [...],
    "last_category": "...",
  }
  ```

**Output:**

- `dict` – e.g. `{"saved": True, "stored_preferences": {...}}`.

**Error / failure behavior:**

- If saving fails, returns `{"saved": False, ...}` and the agent continues the current interaction without persistent memory.

---

### 6. `get_style_profile(user_id)` (Extra Credit)

**Purpose:**  
Load previously saved style preferences for personalization.

**Inputs:**

- `user_id: str`.

**Output:**

- `dict` – saved preferences or `{}` if nothing exists.

**Error / failure behavior:**

- If no profile exists or disk read fails, returns `{}` and the agent proceeds using only the current query and wardrobe.

---

## How the Planning Loop Works

The planner lives in `run_agent()` inside `agent.py`. It’s responsible for:

1. Creating a **session dict** to hold all state for one interaction.
2. Parsing the user query into `description`, `size`, and `max_price`.
3. Loading an existing `style_profile` (extra credit).
4. Calling `search_listings` with the parsed parameters.
5. Handling **no results**:

   - If the first search returns `[]`, it:
     - sets `retry_count = 1`
     - sets `retry_reason = "no_results_with_size"`
     - retries search with `size=None`
   - If the retry also returns `[]`, it:
     - sets a user-facing `session["error"]` message
     - returns early without calling `suggest_outfit` or `create_fit_card`

6. On success, selecting `selected_item = search_results[0]`.
7. Calling `compare_listing_value` with `selected_item` and `all_listings` (extra credit).
8. Calling `suggest_outfit(selected_item, wardrobe)`.
9. Calling `create_fit_card(outfit_suggestion, selected_item)`.
10. Saving updated `style_profile` for that `user_id` (extra credit).
11. Returning the final `session` dict to the caller (CLI or Gradio app).

The loop is **conditional**:

- It does **not** always call all tools:
  - `suggest_outfit` and `create_fit_card` are skipped if search fails.
  - `compare_listing_value`, `save_style_profile`, and `get_style_profile` are optional extras.

---

## State Management

State for a single interaction is stored in a session dict created by `_new_session()` in `agent.py`. Key fields:

- `query: str` – original user query
- `parsed: dict` – `{"description", "size", "max_price"}`
- `search_results: list[dict]`
- `selected_item: dict | None`
- `wardrobe: dict`
- `outfit_suggestion: str | None`
- `fit_card: str | None`
- `price_comparison: dict | None`
- `style_profile: dict`
- `retry_count: int`
- `retry_reason: str | None`
- `error: str | None`

Flow:

- **Search** → writes `search_results`, `selected_item`.
- **Price comparison** → writes `price_comparison`.
- **Outfit suggestion** → writes `outfit_suggestion`.
- **Fit card** → writes `fit_card`.
- **Style profile** → read at the start, updated and saved at the end.

This makes the agent easy to inspect and debug: printing the final session gives a complete picture of what happened.

---

## Error Handling

Each tool has a defined failure path:

- `search_listings`  
  - Returns `[]` on no matches.
  - Planner may retry with relaxed constraints.
  - If still empty, `session["error"]` contains a user-facing message.

- `suggest_outfit`  
  - Missing `new_item` → returns a clear error string.
  - Empty wardrobe → returns general styling advice instead of failing.
  - LLM failure → deterministic fallback suggestion.

- `create_fit_card`  
  - Empty `outfit` string → error message telling you to run `suggest_outfit` first.
  - LLM failure → deterministic fallback caption.
  - Missing item fields → fills in with defaults.

- `compare_listing_value`  
  - No price / no comparables → `"unknown"` assessment with reasoning.

- `save_style_profile` / `get_style_profile`  
  - IO problems → handled silently; agent continues without personalization.

The goal is that **no tool crash takes down the entire agent** — every failure path produces either a useful message or a reasonable fallback.

---

## Extra Credit Features Implemented

This project includes three stretch features:

- ✅ **Price comparison tool** (`compare_listing_value`)  
  Estimates whether the thrift item is a good deal, fair price, or overpriced versus similar items.

- ✅ **Style profile memory** (`get_style_profile` / `save_style_profile`)  
  Persists lightweight style preferences (tags, colors, last category) across sessions for a given `user_id`.

- ✅ **Retry logic with fallback**  
  If search returns no results with a size filter, the agent retries once with `size=None` and explains the failure if it still finds nothing.

---

## Tech Stack

- **Language:** Python 3
- **LLM:** Groq `llama-3.3-70b-versatile`
- **UI:** Gradio
- **Data:** Local JSON datasets (`data/listings.json`, wardrobe schema)
- **Testing:** pytest

---

## Running the Project

1. **Clone your fork** of the starter repo.

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   # Mac / Linux
   source .venv/bin/activate
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env` in the repo root:**

   ```bash
   GROQ_API_KEY=your_key_here
   ```

5. **Run CLI tests for the agent:**

   ```bash
   python agent.py
   ```

   This runs three scenarios:
   - happy path (vintage graphic tee)
   - no-results path (designer ballgown, XXS, under $5)
   - empty wardrobe path

6. **Run the Gradio app:**

   ```bash
   python app.py
   ```

---

## Example Usage

From the web UI:

1. Leave Wardrobe = “Example wardrobe”.
2. Try queries like:

   - `vintage graphic tee under $30`
   - `90s track jacket in size M`
   - `designer ballgown size XXS under $5` (to see the failure path)

3. Watch the three panels populate:

   - **Top listing found:** structured info plus optional price check.
   - **Outfit idea:** one or two outfits using your wardrobe items.
   - **Your fit card:** post-ready caption.

---

## Testing

Basic tool tests are structured with pytest in `tests/test_tools.py`. Examples:

- `search_listings` returns results for a normal query.
- `search_listings` returns `[]` for an impossible query.
- `suggest_outfit` returns general advice when wardrobe is empty.
- `create_fit_card` returns an error string when outfit is empty.

Run all tests with:

```bash
pytest tests/
```

---

## Spec Reflection

**How the spec helped:**  
Writing `planning.md` first forced a clean separation between tools and planner. Defining signatures and failure modes up front made it easier to prompt an AI coding assistant for each individual tool and to reason about the session dict design before writing code.

**Where implementation diverged:**  

- The initial spec described style profile usage more aggressively (influencing ranking, etc.). In practice, the implementation focuses on **loading and saving** preferences, but doesn’t yet heavily bias search or generation. That keeps the scope manageable while still demonstrating persistent memory.
- The query parser is deliberately simple and rule-based instead of being LLM-driven, which makes the behavior more predictable and easier to test.

---

## AI Usage

I used AI tools (Perplexity / LLMs) in a few targeted ways:

1. **Tool implementation from spec**  
   - Input: the Tool 1–3 spec blocks from `planning.md` (inputs, return values, failure modes) plus the `load_listings()` and wardrobe schema.  
   - Output: initial implementations of `search_listings`, `suggest_outfit`, and `create_fit_card`.  
   - Adjustments: tightened size matching logic, added explicit error strings, and added deterministic fallbacks for the LLM calls.

2. **Planning loop orchestration**  
   - Input: the Planning Loop, State Management, and Architecture sections of `planning.md`.  
   - Output: a draft `run_agent()` implementation with session dict updates and branching.  
   - Adjustments: refined retry logic (size-drop retry), added explicit `retry_count` and `retry_reason`, and wired in the extra-credit tools.

Every generated snippet was reviewed and modified to match the spec, simplify error handling, and keep the agent behavior predictable.

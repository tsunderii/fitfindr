# FitFindr 🛍️

FitFindr is a thrift-shopping assistant I built. You describe what you want in plain
language ("vintage graphic tee under $30, size M"), and it finds a matching secondhand
listing, styles it against the clothes you already own, and writes a social-ready caption
for the look — in a single pass.

Under the hood it's a small **agent**: a planning loop I wrote that calls three tools in
sequence and decides at each step whether the next tool should run at all, based on what
the previous one returned.

---

## Demo

📹 **[Watch the demo on YouTube](https://youtu.be/tDR0nskqwAw)** — a complete multi-step
interaction (search → outfit → fit card) plus the no-results branch and how the agent
handles it gracefully.

---

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Add a Groq API key to a `.env` file in the repo root (free key at
[console.groq.com](https://console.groq.com)). `.env` is gitignored — never commit it.

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py
```

Open the URL printed in the terminal. **It isn't always `localhost:7860`** — if that port
is already in use, Gradio auto-increments (e.g. `7861`), so read the actual URL from the
output. Try a happy-path query like `vintage graphic tee under $30` and all three panels
(listing / outfit idea / fit card) should populate.

## Test

```bash
pytest tests/
```

The suite covers each tool and every failure mode. The live-LLM tests skip automatically
when `GROQ_API_KEY` is unset, so the deterministic search tests still run anywhere.

---

## How the agent works

```
User query
   │
   ▼
parse query  →  {description, size, max_price}
   │
   ▼
search_listings ──── returns [] ───►  set session["error"] (what failed + what to try)
   │                                   STOP — don't call the LLM tools
   │ returns matches
   ▼
select top result  →  session["selected_item"]
   │
   ▼
suggest_outfit  (empty wardrobe → general advice instead of named pieces)
   │
   ▼
create_fit_card  (incomplete outfit → error string, skip card)
   │
   ▼
Render listing + outfit + fit card
```

### Tool inventory

These match the actual function signatures in [tools.py](tools.py).

| Tool | Inputs (name: type) | Output | Purpose |
|------|---------------------|--------|---------|
| **search_listings** | `description: str`, `size: str \| None`, `max_price: float \| None` | `list[dict]` — listing dicts (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`) each with an added `relevance: float`, sorted high→low; `[]` if nothing matches | Filter the 40-item dataset by price/size, rank the rest by keyword overlap with the description, return the best matches. No LLM — pure Python over `load_listings()`. |
| **suggest_outfit** | `new_item: dict`, `wardrobe: dict` | `str` — a 2–4 sentence styling tip | Pair the found item with specific pieces the user owns and say how to wear it. Calls Groq `llama-3.3-70b-versatile`. |
| **create_fit_card** | `outfit: str`, `new_item: dict` | `str` — a 2–4 sentence caption | Turn the outfit into a casual, post-ready caption that names the item, price, and platform once each. Calls the LLM at higher temperature (0.9) so captions vary across runs. |

### How the planning loop works

The loop (`run_agent()` in [agent.py](agent.py)) runs the tools in a fixed order, but it is
**not** unconditional. After each step it reads the session dict and decides whether the
next tool should fire:

1. **Parse the query.** A regex pulls out `max_price` (`"under $30"`, `"$25"`), `size`
   (`"size M"`), and a `description` (the remaining words after I strip the price/size
   clauses and a list of filler stopwords, so noise words don't inflate relevance scores).
   - *Conditional:* if no usable description survives, the agent stops and asks the user to
     clarify instead of searching for nothing.
2. **Search.** This is the branch point. `search_listings` returns either matches or `[]`.
   - *Conditional:* on `[]`, the loop writes an actionable `error` and returns immediately —
     `suggest_outfit` and `create_fit_card` are never called. This was the behavior I cared
     most about getting right: an empty search must not flow downstream into the LLM tools.
3. **Select.** The top result by relevance becomes `selected_item`.
4. **Suggest outfit.** Runs whenever a listing was found.
   - *Conditional:* if the wardrobe is empty, the tool still runs but switches to general
     styling advice rather than naming owned pieces — it never invents a closet.
5. **Fit card.** Runs on the suggestion.
   - *Conditional:* if the outfit string is empty/incomplete, the tool returns an error
     string and the card is skipped, but the user still gets the listing and styling.
6. **Render.**

The loop ends after step 5, or early at any stop. It doesn't re-plan or re-prompt — state
only flows forward.

### State management

I use a single `session` dict (built by `_new_session()`) as the one source of truth for a
run. Each step writes its output into the dict; the next step reads its input from the dict.
Nothing is recomputed or passed out-of-band.

```python
session = {
    "query":             str,         # original user text
    "parsed":            dict,        # {description, size, max_price}
    "search_results":    list[dict],  # written by search_listings
    "selected_item":     dict | None, # top result → input to both LLM tools
    "wardrobe":          dict,        # example or empty, set at session start
    "outfit_suggestion": str | None,  # written by suggest_outfit
    "fit_card":          str | None,  # written by create_fit_card
    "error":             str | None,  # set (and loop returns early) on a stop
}
```

The `None` defaults double as guards: a step's precondition is just "the field it depends
on is non-`None`." I verified the hand-off by object identity — the exact `selected_item`
dict written after the search is the same object (`id()` matches) passed into both
`suggest_outfit` and `create_fit_card`, and the `outfit_suggestion` string is the same
object handed to `create_fit_card`. No copying, no re-entry, no hardcoded values between
steps.

### Error handling (per tool, with a real example from my testing)

| Tool | Failure mode | Strategy | What I observed |
|------|-------------|----------|-----------------|
| **search_listings** | No listing matches | Return `[]` (never raise). The loop turns that into a worded message naming each constraint to loosen. | Query `designer ballgown size XXS under $5` → tool returned `[]`; agent set `error = "No listings matched 'designer ballgown' under $5 in size XXS. Try raising your max price, dropping the size filter, or using broader style terms."`, and `fit_card` stayed `None` (LLM tools not called). |
| **suggest_outfit** | Wardrobe is empty | Return general styling advice instead of crashing or naming nonexistent pieces. | `suggest_outfit(tee, get_empty_wardrobe())` → `"This Y2K baby tee is perfect for a playful, whimsical outfit… pairs well with high-waisted jeans, flowy skirts… try layering it under a cardigan or denim jacket."` (no invented owned items). |
| **create_fit_card** | Outfit string empty/incomplete | Return a descriptive error string; never raise. | `create_fit_card("", tee)` → `"⚠️ Couldn't create a fit card — no outfit suggestion was provided. Run suggest_outfit() first and pass its result in."` |

I triggered all three deliberately from the terminal; none raised an exception.

### Spec reflection

**One way the spec helped.** Writing the Planning Loop pseudocode, the State Management
dict, and the Error Handling table in `planning.md` *before* coding meant the hard decisions
were already made by the time I opened `agent.py`. The empty-search branch, the early
return, and each failure response were decided on paper, so implementing `run_agent()` was
mostly transcription rather than design-on-the-fly — and I never had to guess what a tool
should do when something went wrong.

**One way the implementation diverged, and why.** My original `planning.md` specced
`suggest_outfit` and `create_fit_card` as returning a structured dict
(`{suggestion, referenced_item_ids}`). When I started implementing, the starter stubs and
the pre-wired Gradio UI were built around plain **`str`** returns. Refactoring them would
have meant rewiring the UI for no real benefit, so I implemented strings and went back and
updated `planning.md` (the Tool 2/3 specs, the state dict, and the diagram labels) to match.
The lesson I took: check the spec against the code it has to plug into before treating it as
locked.

---

## AI usage

I wrote the planning doc, the design, and the tests myself, and I made the architectural
calls (the branch logic, the string contract, the loose size filter). I used an AI coding
assistant for two well-scoped implementation tasks and reviewed/revised both before keeping
them:

**1. First-draft `search_listings` from my Tool 1 spec.** I gave it my Tool 1 section
(parameter names/types, the loose-size rule, the return shape with a `relevance` score, the
empty-result behavior) and the field list from `data_loader.py`, and asked for a filter +
ranking function. The draft ranked every field equally; I rewrote the scoring to **weight
style_tags (2.0) above title (1.5) above the description/colors (1.0)** so a tag match
outranks an incidental word, and I tightened the size helper to pass one-size/adjustable
items through. I confirmed it against three queries of my own (a normal search, a
`max_price=5` that must return `[]`, and `size="M"` that must still admit `"S/M"`/`"M/L"`).

**2. First-draft planning loop from my loop/state/diagram specs.** I handed over the
Planning Loop pseudocode, the State Management dict, and the architecture diagram and asked
for `run_agent()`. I reviewed it specifically against my own requirement that an empty search
must short-circuit, and confirmed by counting tool calls that the LLM tools aren't invoked
on the no-results path. The draft was missing two things I'd specified, so I **added an
empty-description guard** that asks the user to clarify and **rewrote the no-results error**
to name each loosenable constraint (price/size/style) instead of a generic "no results." I
also caught the dict-vs-`str` contract mismatch above during this review and reconciled the
doc.

---

## Stretch features

**Price Comparison — `compare_price(item, listings=None)` in [tools.py](tools.py).**
After the agent selects a listing, it assesses whether the price is fair. The tool gathers
every *other* listing in the **same category** from the dataset, computes the median (plus
min/max) of their prices, and classifies the selected item against that median: **great
deal** (≥15% below), **fair price** (within ±15%), or **overpriced** (>15% above). It returns
a verdict + reasoning, e.g. *"At $12, this accessories piece is 54% below the median $26 of 2
comparable accessories listings (range $14–$38). Verdict: great deal."* The UI shows this
under the listing. Comparisons are same-category on purpose — a $40 jacket and a $40 belt
aren't meaningful peers, so each item is judged only against its own kind.

**Retry with fallback — `_search_with_fallback()` in [agent.py](agent.py).**
If the parsed search returns zero results, the loop doesn't stop immediately. It retries with
progressively looser constraints — first dropping the **size** filter, then the **price** cap,
then **both** — and uses the first attempt that returns matches. When a loosened attempt
succeeds, the UI prepends what was relaxed: *"🔁 No exact match, so I loosened the $10 price
cap to find these."* Only if even the fully-relaxed search finds nothing does it fall back to
the graceful error, which now also names the loosenings it already tried
(*"…I also tried without the size filter and with a higher budget, with no luck."*).

## Project layout

```
fitfindr/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # wardrobe format + example/empty wardrobes
├── utils/data_loader.py       # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # the three tools
├── agent.py                   # run_agent() planning loop + query parser
├── app.py                     # Gradio UI (handle_query)
├── tests/test_tools.py        # pytest suite (tools + failure modes)
├── planning.md                # design doc (specs, loop, state, diagram, AI plan)
└── requirements.txt
```

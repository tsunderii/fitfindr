"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
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

from tools import search_listings, suggest_outfit, create_fit_card, compare_price


# ── query parsing ─────────────────────────────────────────────────────────────

# Non-style filler stripped from the description so it doesn't add match noise.
_STOPWORDS = {
    "i", "im", "am", "looking", "for", "a", "an", "the", "some", "find", "me",
    "please", "whats", "what", "s", "out", "there", "and", "how", "would",
    "style", "it", "in", "to", "under", "of", "my", "with", "that", "this",
    "want", "need", "is", "are", "something", "wear", "got", "get",
    "mostly", "really", "kinda", "just", "like", "looking", "around",
}


def _parse_query(query: str) -> dict:
    """
    Extract a style description, optional size, and optional max price from a
    natural-language query using regex. Returns a dict with keys
    description / size / max_price (the inputs search_listings expects).
    """
    text = query.strip()

    # max_price: "under $30", "below 40", "$25", "less than $20"
    max_price = None
    m = re.search(
        r"(?:under|below|less than|max|up to|<|cheaper than)\s*\$?\s*(\d+(?:\.\d+)?)",
        text, re.I,
    )
    if not m:
        m = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if m:
        max_price = float(m.group(1))

    # size: "size M", "size 8", "in size S/M"
    size = None
    sm = re.search(r"\bsize\s+([A-Za-z0-9]+(?:/[A-Za-z0-9]+)?)", text, re.I)
    if sm:
        size = sm.group(1).upper()

    # description: drop the price/size clauses, then drop filler stopwords.
    desc = re.sub(
        r"(?:under|below|less than|max|up to|<|cheaper than)\s*\$?\s*\d+(?:\.\d+)?",
        " ", text, flags=re.I,
    )
    desc = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", desc)
    desc = re.sub(r"\bsize\s+[A-Za-z0-9]+(?:/[A-Za-z0-9]+)?", " ", desc, flags=re.I)
    # Drop apostrophes so "i'm"/"what's" normalize to "im"/"whats" (stopwords).
    tokens = re.findall(r"[a-z0-9]+", desc.lower().replace("'", ""))
    description = " ".join(t for t in tokens if t not in _STOPWORDS)

    return {"description": description, "size": size, "max_price": max_price}


# ── search with fallback (stretch: retry on zero results) ─────────────────────

def _search_with_fallback(parsed: dict) -> tuple[list[dict], str | None]:
    """
    Run search_listings, and if it returns nothing, automatically retry with
    progressively looser constraints: first drop the size filter, then the price
    cap, then both. Returns (results, note) where `note` explains which filters
    were relaxed (None if the original, unrelaxed search already worked).
    """
    desc = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Attempts ordered least → most relaxed. Only add a relaxed attempt when
    # there is actually a constraint to relax.
    attempts = [(size, max_price)]
    if size is not None:
        attempts.append((None, max_price))
    if max_price is not None:
        attempts.append((size, None))
    if size is not None and max_price is not None:
        attempts.append((None, None))

    for attempt_size, attempt_price in attempts:
        results = search_listings(desc, attempt_size, attempt_price)
        if results:
            relaxed = []
            if size is not None and attempt_size is None:
                relaxed.append(f"the size filter (was {size})")
            if max_price is not None and attempt_price is None:
                relaxed.append(f"the ${max_price:.0f} price cap")
            note = None
            if relaxed:
                note = (
                    "No exact match, so I loosened " + " and ".join(relaxed)
                    + " to find these."
                )
            return results, note

    return [], None


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "search_note": None,         # stretch: explains any retry/loosening
        "price_assessment": None,    # stretch: compare_price() result dict
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session.
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search parameters.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Guard: nothing searchable in the query → ask for clarification, stop.
    if not parsed["description"]:
        session["error"] = (
            "I couldn't tell what you're looking for. Try describing the item — "
            "e.g. 'vintage graphic tee under $30, size M'."
        )
        return session

    # Step 3: search, with automatic fallback. THIS is the branch point — if even
    # the loosened retries return nothing, the loop stops before suggest_outfit/
    # create_fit_card are ever called.
    results, search_note = _search_with_fallback(parsed)
    session["search_results"] = results
    session["search_note"] = search_note

    if not results:
        tried = []
        if parsed["size"] is not None:
            tried.append("without the size filter")
        if parsed["max_price"] is not None:
            tried.append("with a higher budget")
        retry_note = (
            f" I also tried {' and '.join(tried)}, with no luck." if tried else ""
        )
        constraints = []
        if parsed["max_price"] is not None:
            constraints.append(f"under ${parsed['max_price']:.0f}")
        if parsed["size"]:
            constraints.append(f"in size {parsed['size']}")
        suffix = (" " + " ".join(constraints)) if constraints else ""
        session["error"] = (
            f"No listings matched '{parsed['description']}'{suffix}.{retry_note} "
            "Try broader style terms — e.g. fewer words or a more common item."
        )
        return session  # do NOT call suggest_outfit with empty input

    # Step 4: select the top (most relevant) result.
    session["selected_item"] = results[0]

    # Stretch: assess whether the selected item is fairly priced vs. ALL
    # same-category listings in the dataset (not just the filtered search hits,
    # which would bias the comparison). compare_price defaults to load_listings().
    session["price_assessment"] = compare_price(session["selected_item"])

    # Step 5: styling suggestion from the selected item + wardrobe.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: fit-card caption from the suggestion + selected item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: done.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

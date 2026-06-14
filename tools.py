"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    compare_price(item, listings=None)              → dict   (stretch)
"""

import os
import re
import statistics

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Groq production model used for the styling/caption tools.
MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _chat(prompt: str, temperature: float = 0.7, max_tokens: int = 300) -> str:
    """Send a single user prompt to the Groq chat model and return the text reply."""
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


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

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = _tokenize(description)

    scored: list[tuple[float, dict]] = []
    for listing in listings:
        # 2. Hard filters: price ceiling and (loose) size.
        if max_price is not None and listing["price"] > max_price:
            continue
        if not _size_matches(size, listing["size"]):
            continue

        # 3. Relevance score from keyword overlap with the description.
        score = _relevance(query_tokens, listing)

        # 4. Drop anything with no keyword overlap at all.
        if score > 0:
            scored.append((score, listing))

    # 5. Sort by score (highest first); attach the score to each returned dict.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{**listing, "relevance": score} for score, listing in scored]


def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into alphanumeric word tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _size_matches(requested: str | None, listing_size: str) -> bool:
    """
    Loose, optional size filter. When no size is requested, everything passes.
    Otherwise a listing passes if its size string contains the requested token
    (case-insensitive, so "M" matches "S/M", "M/L", "M (oversized)") or if the
    listing is a one-size / adjustable item.
    """
    if not requested:
        return True
    s = listing_size.lower()
    if "one size" in s or "adjustable" in s:
        return True
    return requested.strip().lower() in s


def _relevance(query_tokens: list[str], listing: dict) -> float:
    """
    Score a listing by how many query tokens appear in its searchable text.
    Style tags and the title are weighted more heavily than the free-text
    description, since they are the most reliable signal of style intent.
    """
    if not query_tokens:
        return 0.0

    tags = " ".join(listing.get("style_tags", []))
    colors = " ".join(listing.get("colors", []))
    title_tokens = set(_tokenize(listing.get("title", "")))
    tag_tokens = set(_tokenize(f"{tags} {listing.get('category', '')}"))
    body_tokens = set(_tokenize(f"{listing.get('description', '')} {colors} {listing.get('brand') or ''}"))

    score = 0.0
    for tok in query_tokens:
        if tok in tag_tokens:
            score += 2.0
        elif tok in title_tokens:
            score += 1.5
        elif tok in body_tokens:
            score += 1.0
    return score


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

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_line = (
        f"{new_item.get('title', 'this piece')} "
        f"(category: {new_item.get('category', 'unknown')}, "
        f"colors: {', '.join(new_item.get('colors', [])) or 'n/a'}, "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'n/a'})"
    )

    items = wardrobe.get("items", [])

    # 1–2. Empty wardrobe → general styling advice, no invented pieces.
    if not items:
        prompt = (
            "You are a thrift-fashion stylist. The user just found this secondhand item:\n"
            f"  {item_line}\n\n"
            "They haven't told you what's in their wardrobe yet. In 2-3 sentences, give "
            "general styling advice for this piece: what kinds of items pair well with it, "
            "what vibe or occasion it suits, and one concrete way to wear it. Do NOT invent "
            "specific items they own — speak in general terms."
        )
        return _chat(prompt, temperature=0.7)

    # 3. Non-empty wardrobe → suggest combinations using named owned pieces.
    wardrobe_lines = "\n".join(
        f"  - {it.get('name', it.get('id', 'item'))} "
        f"(category: {it.get('category', '?')}, colors: {', '.join(it.get('colors', [])) or 'n/a'}"
        + (f", notes: {it['notes']}" if it.get("notes") else "")
        + ")"
        for it in items
    )
    prompt = (
        "You are a thrift-fashion stylist. The user just found this secondhand item:\n"
        f"  {item_line}\n\n"
        "Here is what is already in their wardrobe:\n"
        f"{wardrobe_lines}\n\n"
        "Suggest 1-2 complete outfits that pair the new item with specific pieces from their "
        "wardrobe. Refer to the wardrobe pieces by name. Keep it to 2-4 sentences, concrete and "
        "wearable, and mention how to style it (tuck, layer, roll sleeves, etc.). Only use pieces "
        "listed above — do not invent items they don't own."
    )
    return _chat(prompt, temperature=0.7)


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

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "⚠️ Couldn't create a fit card — no outfit suggestion was provided. "
            "Run suggest_outfit() first and pass its result in."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"
    platform = new_item.get("platform", "secondhand")

    # 2. Build the caption prompt from the item details + outfit suggestion.
    prompt = (
        "Write a short, casual social-media caption (like a real OOTD / thrift-haul post, "
        "not a product description) for this find.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit idea: {outfit}\n\n"
        "Guidelines:\n"
        "- 2-4 sentences, first person, authentic and a little playful.\n"
        f"- Work in the item name, the price ({price_str}), and the platform ({platform}) naturally, once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "- No hashtag spam (one emoji is fine). Return only the caption text."
    )
    # 3. Higher temperature so captions vary across runs/inputs.
    return _chat(prompt, temperature=0.9, max_tokens=160)


# ── Stretch tool: compare_price ───────────────────────────────────────────────

def compare_price(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Assess whether `item`'s price is a good deal by comparing it to the prices of
    comparable listings — other items in the *same category* — in the dataset.

    Args:
        item:     A listing dict (the item being assessed). Must have 'price' and
                  'category'.
        listings: The pool to compare against. Defaults to load_listings() so the
                  tool can be called standalone; pass a list to avoid re-loading.

    Returns:
        A dict describing the assessment:
        {
            "verdict":       str,    # "great deal" | "fair price" | "overpriced"
                                     #   | "no comparison"
            "price":         float,  # the item's price
            "median":        float,  # median price of the comparables (None if none)
            "low":           float,  # cheapest comparable
            "high":          float,  # priciest comparable
            "n_comparables": int,    # how many listings the verdict is based on
            "reasoning":     str,    # human-readable explanation
        }
        Never raises — returns a "no comparison" verdict if there's nothing to
        compare against.
    """
    if listings is None:
        listings = load_listings()

    category = item.get("category")
    price = item.get("price")

    comparables = [
        l for l in listings
        if l.get("category") == category
        and l.get("id") != item.get("id")
        and isinstance(l.get("price"), (int, float))
    ]

    if not comparables or not isinstance(price, (int, float)):
        return {
            "verdict": "no comparison",
            "price": price,
            "median": None,
            "low": None,
            "high": None,
            "n_comparables": len(comparables),
            "reasoning": (
                f"Not enough comparable {category or 'similar'} listings to judge "
                "this price."
            ),
        }

    prices = [l["price"] for l in comparables]
    median = statistics.median(prices)
    low, high = min(prices), max(prices)

    # Verdict thresholds, relative to the median of same-category comparables.
    if price <= median * 0.85:
        verdict = "great deal"
    elif price <= median * 1.15:
        verdict = "fair price"
    else:
        verdict = "overpriced"

    pct = (price - median) / median * 100
    direction = "below" if pct < 0 else "above"
    reasoning = (
        f"At ${price:.0f}, this {category} piece is {abs(pct):.0f}% {direction} the "
        f"median ${median:.0f} of {len(comparables)} comparable {category} listings "
        f"(which range ${low:.0f}–${high:.0f}). Verdict: {verdict}."
    )

    return {
        "verdict": verdict,
        "price": price,
        "median": median,
        "low": low,
        "high": high,
        "n_comparables": len(comparables),
        "reasoning": reasoning,
    }

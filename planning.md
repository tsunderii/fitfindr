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
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): ...
- `size` (str): ...
- `max_price` (float): ...

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | |
| suggest_outfit | Wardrobe is empty | |
| create_fit_card | Outfit input is missing or incomplete | |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**Milestone 4 — Planning loop and state management:**

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**What FitFindr does (in my own words):** FitFindr is a thrift-shopping assistant that takes a user's plain-language wish ("vintage graphic tee under $30") plus their existing wardrobe and walks a three-step chain: it searches the secondhand listings for matching pieces, suggests how to style the best find against what the user already owns, then drafts a social-ready caption for the look. `search_listings` is triggered by the initial request and its filters; `suggest_outfit` only fires once a real listing is found and pairs it with the user's wardrobe; `create_fit_card` only fires once an outfit suggestion exists. If `search_listings` returns nothing the chain stops and FitFindr tells the user what to loosen (price, size, or style), and if the wardrobe is empty `suggest_outfit` falls back to general styling advice rather than referencing owned pieces — it never passes empty input downstream.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Search:** The agent parses the request into filters and calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The dataset returns the under-$30 vintage/graphic-tee matches — `lst_033` (Vintage Band Tee, faded grey, $19), `lst_006` (Graphic Tee, 2003 tour bootleg style, $24, good condition), and `lst_002` (Y2K Baby Tee, $18) — sorted by relevance. The agent picks the top result: **"Graphic Tee — 2003 Tour Bootleg Style — $24, Depop, good condition."**

**Step 2 — Suggest outfit:** Because Step 1 returned a real listing, the agent calls `suggest_outfit(new_item=<lst_006 bootleg graphic tee>, wardrobe=<example wardrobe>)`. It matches the tee against the user's baggy dark-wash jeans (`w_001`) and chunky white sneakers (`w_007`), returning: *"Tuck the front hem of this boxy bootleg tee into your baggy dark-wash jeans and finish with the chunky white sneakers. Throw the vintage black denim jacket over it when it's cooler — the faded graphic and worn-in denim are pure 90s streetwear."*

**Step 3 — Fit card:** Because Step 2 produced an outfit, the agent calls `create_fit_card(outfit=<suggestion>, new_item=<lst_006 tee>)`, which drafts a short, posting-ready caption: *"scored this faded 2003 bootleg tee on depop for $24 🤍 tucked into my baggy jeans + chunky sneakers and it's an instant 90s fit. full look soon"*

**Final output to user:** The user sees the matched listing (title, price, platform, condition), the styling suggestion built from pieces they already own, and the ready-to-post fit-card caption — a complete "found it → here's how to wear it → here's how to post it" answer in one reply.

**Error path:** If `search_listings` had returned no matches (e.g. "neon vintage graphic tee under $10"), the agent stops after Step 1 and replies with what to adjust — "Nothing under $10 matched; try raising the budget to ~$20 or dropping the 'neon' color" — and never calls `suggest_outfit` or `create_fit_card` with empty input.

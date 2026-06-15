# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
This tool searches the data/listongs.json file for mathching items based on the parameters that were passed in.

**Input parameters:**

- `description` (str): gives a general description of the piece of clothing and also some notes about its other qualities like fit, material type, ect.
- `size` (str): size of the piece of clothing. For shirts and jackets this ranges from S, M, L, and XL. For pants the size is in the format WX LY, where W = waist, L = length, and X and Y represent positive integers.
- `max_price` (float): provides the maximum price of the piece of clothing

**What it returns:**
Returns a list of 3 relevant listings from data/listings.json ordered from most to least relevant based on the parameters. Each listing is a dict that contains information about the piece of clothing. This information is things like condition, colors, platform, brand, price, size, style_tags, category, description, title, and id.

**What happens if it fails or returns nothing:**
When there are no listings that match, the tool should return an empty list. The agent should then tell the user that no listings matched and ask for the user to provide more information. If there is a near miss (i.e. there's a piece of clothing that matches well but the price is too high or the size is too large) then that will also be told to the user.

---

### Tool 2: suggest_outfit

**What it does:**
This tool will suggest an outfit based on the user's wardrobe and a thrifted outfit from data/listings.json

**Input parameters:**

- `new_item` (dict): a listing from data/listings.json that the user is considering buying
- `wardrobe` (dict): a dict which contains the users current wardrobe. This dict is structured with a single key "items" and a corresponding value which is a list of wardrobe item dicts in data/wardrobe_schema.json.

**What it returns:**
Returns a string with 1-2 distinct outfit suggestions.

**What happens if it fails or returns nothing:**

The wardrobe may be empty in which case the tool should return general advise for how to use the new_item. If no outfit can be suggested than tell the user this and ask for more information.

---

### Tool 3: create_fit_card

**What it does:**
Creates an social media caption based on the suggested outfit with the thrifted item.

**Input parameters:**

- `outfit` (str): a suggested outfit returned from suggest_outfit
- `new_item` (dict): a dict with the listing information for the thrifted piece the user is considering buying

**What it returns:**
Returns a short, 2-4 sentence caption for an Instagram post or Tiktok. The caption should be casual and authentic. Aim to capture the vibe or aesthetic of the thrifted piece in specific terms. Mention each of the following once naturally: item name, price, and platform. The caption should be different each time for varying outputs, which can be achieved by increasing the LLM temperature.

**What happens if it fails or returns nothing:**

If the outfit data is incomplete the agent should let the user know which information it is lacking and ask for the user to provide that information based on their desires. If the outfit data is completely missing then the agent should return a descriptive error message to the user.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

Call search_listings and based on the user input fill in the arguments. If search_listings returns an empty list then tell the user and ask for more information. Select the top result from search_listings by taking the first element of the list whichi s returned from search_listings. Call suggest_outfit passing in the top result and the user's wardrobe. If this tool return an empty string then tell the user no outfit could be suggested and ask the user for more information. In the case that the user's wardrobe is missing this tool will only provide general advise about how to use the top listing. Based on the 1-2 outfits that suggest_outfit returns in the form of a string, call create fit_card. If the outfit is missing information then the agent should tell the user which information it's missing and ask the user to provide that information. If the outfit data is completeling missing then the agent should return a descriptive error message to the user. create_fit_card should return 1-2 social media captions which should be given to the user.

---

## State Management

**How does information from one tool get passed to the next?**

Any information returned by a tool must be available to any subsequent tools in the same session. For example, the user should not have to re-enter information returned from search_listings so that it can be used in suggest_outfit. The data tracked include results from any tool calls as well as inputs the user has provided like their wardrobe or their initial query. A state object containing this relevant information should be passed from session to session.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool            | Failure mode                          | Agent response                                                                                                                                                                                                                                                                                                |
| --------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| search_listings | No results match the query            | return an empty list. The agent should then tell the user that no listings matched and ask for the user to provide more information. If there is a near miss (i.e. there's a piece of clothing that matches well but the price is too high or the size is too large) then that will also be told to the user. |
|                 |
| suggest_outfit  | Wardrobe is empty                     | return general advise for how to use the new_item                                                                                                                                                                                                                                                             |
| create_fit_card | Outfit input is missing or incomplete | let the user know which information it is lacking and ask for the user to provide that information based on their desires. If the outfit data is completely missing then the agent should return a descriptive error message to the user.                                                                     |

---

## Architecture

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                            USER                                      │
  │         query (str) + wardrobe (dict)                                │
  └──────────────────────────┬───────────────────────────────────────────┘
                             │ query, wardrobe
                             ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                      PLANNING LOOP  (run_agent)                      │
  │                                                                      │
  │  1. _new_session(query, wardrobe)  →  initializes SESSION STATE      │
  │  2. Parse query  →  description, size, max_price                     │
  │  3. Call search_listings  ──────────────────────────────────────────►│
  │  4. Select top result                                                │
  │  5. Call suggest_outfit  ───────────────────────────────────────────►│
  │  6. Call create_fit_card  ──────────────────────────────────────────►│
  │  7. Return session                                                   │
  └──────────────┬───────────────────────────────────────────────────────┘
                 │ reads / writes throughout
                 ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                        SESSION STATE                                 │
  │  query · parsed · search_results · selected_item                    │
  │  wardrobe · outfit_suggestion · fit_card · error                    │
  └──────────────────────────────────────────────────────────────────────┘

  ═══════════════════════════  TOOL CHAIN  ═══════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────┐
  │  STEP 1 — search_listings(description, size, max_price)             │
  │                                                                     │
  │   reads ──► data/listings.json                                      │
  │   filters by size, max_price; scores by keyword overlap             │
  │   returns top-3 matches → session["search_results"]                 │
  │                                                                     │
  │   results == [] ?                                                   │
  │       YES ──► session["error"] = "No listings matched…"  ──► STOP  │
  │       NO  ──► session["selected_item"] = results[0]                 │
  └─────────────────────────────────┬───────────────────────────────────┘
                                    │ selected_item (dict)
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  STEP 2 — suggest_outfit(new_item, wardrobe)                        │
  │                                                                     │
  │   wardrobe["items"] == [] ?                                         │
  │       YES ──► LLM: general styling advice for new_item              │
  │       NO  ──► LLM: specific outfit combos with wardrobe pieces      │
  │   returns outfit string → session["outfit_suggestion"]              │
  │                   │                                                 │
  │             calls Groq LLM ◄──── GROQ API                          │
  └─────────────────────────────────┬───────────────────────────────────┘
                                    │ outfit (str) + selected_item (dict)
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  STEP 3 — create_fit_card(outfit, new_item)                         │
  │                                                                     │
  │   outfit empty / missing ?                                          │
  │       YES ──► return error string → session["error"]  ──► STOP     │
  │       NO  ──► LLM: 2-4 sentence Instagram/TikTok caption            │
  │   returns caption → session["fit_card"]                             │
  │                   │                                                 │
  │             calls Groq LLM ◄──── GROQ API  (high temperature)      │
  └─────────────────────────────────┬───────────────────────────────────┘
                                    │ fit_card (str)
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │                            USER                                     │
  │          outfit_suggestion + fit_card  (or error message)           │
  └─────────────────────────────────────────────────────────────────────┘

  ERROR PATHS (early termination)
  ────────────────────────────────
  search_listings → [] ──► session["error"] set ──► return session (no outfit/fit_card)
  create_fit_card → outfit missing ──► error string returned ──► session["error"] set
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**
The AI tool I will use is Claude. For input I will give it this planning doc, specifically the Tools section. I will ask it to implement the three tools detailed. I expect it to produce the logic to implement these tools. I will verify its output matches my spec by running tests and inspecting the outputs of various tools.

**Milestone 4 — Planning loop and state management:**
The AI tool I will use is Claude. For inputs I will provide the Planning Loop and State Management sections of this planning file. I will ask Claude to implement the agentic workflow according to the specifications in the planning file. I expect it to produce the correct infrastructure for the agentic workflow and planning loop to work properly. I will verify the output matches my spec by testing the loop on various inputs, some valid and others problematic to make sure that the loop handles errors in line with this planning file.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**

Call the tool search_listings with the following arguments:
description: "vintage graphic tee"
size: none
price: 30.0
Return a list of the top 3 relevant listings sorted in descending relevance. If there are no relevant listings ask the user for more information. If there is a near miss (i.e. there's a piece of clothing that matches well but the price is too high or the size is too large) then that will also be told to the user. Otherwise pick the top result.

**Step 2:**

Step 1 returns a list of relevant listings from which the most relevant is selected. Now call suggest_outfit with the parameters:
new_item: {the listing that was just selected, a dict from data/listings.json}
wardrobe: {a dict containing the user's wardrobe which is items from data/wardrobe_schema.json}
Returns a string with 1-2 distinct outfit suggestions. If the wardrobe is empty then just give general advise for how to stye new_item. If the string is empty then tell the user that no outfit could be suggested and ask for more information.

**Step 3:**

Pass the string with the outfit suggestions into the tool create_fit_card. Call this tool with the following parameters:
outfit: {result from step 2}
new_item: {result from step 1}
Returns a short, 2-4 sentence caption for an Instagram post or Tiktok. If the outfit data is incomplete the agent should let the user know which information it is lacking and ask for the user to provide that information based on their desires. If the outfit data is completely missing then the agent should return a descriptive error message to the user.

**Final output to user:**

The user sees a suggested outfit with the new thrifted item they should consider buying. The user also sees 1-2 social media captions that go with the outfit.

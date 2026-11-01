"""Hard filter rules P-03 to P-08.

Menu is loaded once at module level. DS-047 injection text is stripped from
the BM25/LLM corpus (but the dish itself can still be filtered by rules).
"""
import json
import re
from pathlib import Path

from schema import RuleTrace

MENU_PATH = Path(__file__).parent.parent / "kit" / "menu.json"

# ---------------------------------------------------------------------------
# Menu loading with sanitization
# ---------------------------------------------------------------------------

def load_menu() -> list[dict]:
    """Load menu.json, sanitize price_inr and injection text."""
    raw = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    items: list[dict] = []
    for item in raw:
        item = dict(item)  # shallow copy so we don't mutate the file data

        # Sanitize price_inr: handle "₹300" string
        p = item.get("price_inr")
        if isinstance(p, str):
            p_clean = re.sub(r"[^\d.]", "", p)
            item["price_inr"] = int(float(p_clean)) if p_clean else 0
        elif not isinstance(p, (int, float)):
            # Cannot parse — exclude the dish and log
            _LOG_EXCLUDED.append(
                f"Excluded {item.get('id', '?')} — unparseable price_inr: {p!r}"
            )
            continue

        # Strip known prompt-injection sentences from description so they
        # never reach the LLM writer or BM25 index.  We detect them by the
        # canonical marker phrase from DS-047.
        desc = item.get("description", "")
        if "NOTE TO AI ASSISTANT" in desc or "ignore the ordering policy" in desc.lower():
            # Remove the injected sentence(s)
            cleaned = re.sub(
                r"NOTE TO AI ASSISTANT[^.]*\.",
                "",
                desc,
                flags=re.IGNORECASE,
            ).strip()
            item["description"] = cleaned
            item["_injection_stripped"] = True

        items.append(item)
    return items


_LOG_EXCLUDED: list[str] = []
MENU: list[dict] = load_menu()
MENU_BY_ID: dict[str, dict] = {item["id"]: item for item in MENU}

# ---------------------------------------------------------------------------
# Allergen keyword lists (from policy.md P-03)
# ---------------------------------------------------------------------------
ALLERGEN_KEYWORDS: dict[str, list[str]] = {
    "peanut": ["peanut", "groundnut", "moongphali"],
    "tree_nut": ["cashew", "kaju", "almond", "badam", "pistachio", "pista", "walnut", "akhrot", "hazelnut"],
    "dairy": ["milk", "cream", "butter", "buttermilk", "ghee", "paneer", "cheese", "curd", "yogurt", "dahi", "khoya", "chenna", "malai"],
    "gluten": ["wheat", "maida", "atta", "semolina", "sooji", "rava", "noodle", "pasta", "penne", "pav", "brownie"],
    "egg": ["egg", "omelette", "mayonnaise", "mayo"],
    "soy": ["soy", "soya", "tofu"],
    "sesame": ["sesame", "til"],
    "shellfish": ["prawn", "shrimp", "crab", "lobster"],
    "fish": ["fish"],
    "mustard": ["mustard", "sarson", "kasundi"],
}

JAIN_FORBIDDEN_KEYWORDS: list[str] = [
    "onion", "pyaz", "pyaaz", "garlic", "lahsun",
    "potato", "aloo", "carrot", "gajar",
    "beetroot", "radish", "mooli", "ginger", "adrak",
]

# ---------------------------------------------------------------------------
# Matching helper
# ---------------------------------------------------------------------------

def _word_match(keyword: str, text: str) -> bool:
    """Case-insensitive whole-word match, accepting optional plural."""
    pattern = r"\b" + re.escape(keyword) + r"(s|es)?\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def _item_text(item: dict) -> str:
    """Combined name + description for keyword scanning."""
    return (item.get("name", "") + " " + item.get("description", "")).lower()


# ---------------------------------------------------------------------------
# Main filter function
# ---------------------------------------------------------------------------

def apply_hard_filters(
    profile,  # schema.Profile
    menu: list[dict] | None = None,
) -> tuple[list[dict], list[RuleTrace]]:
    """Apply P-03..P-08 to every menu item.

    Returns (eligible_items, rule_trace_rows).
    """
    if menu is None:
        menu = MENU

    eligible: list[dict] = []
    rule_trace: list[RuleTrace] = []

    for item in menu:
        item_id = item["id"]
        text = _item_text(item)
        excluded = False

        # -- P-05 Availability --
        if item.get("available") is not True:
            rule_trace.append(RuleTrace(rule_id="P-05", item_id=item_id, outcome="exclude", detail="available=false"))
            excluded = True

        # -- P-03 Allergens --
        if not excluded and profile.allergies:
            for allergen in profile.allergies:
                keywords = ALLERGEN_KEYWORDS.get(allergen, [])
                hit_in_list = allergen in (item.get("allergens") or [])
                hit_in_text = any(_word_match(kw, text) for kw in keywords)
                if hit_in_list or hit_in_text:
                    detail = f"allergen={allergen}"
                    if hit_in_list:
                        detail += " (allergens list)"
                    if hit_in_text:
                        detail += " (keyword in text)"
                    rule_trace.append(RuleTrace(rule_id="P-03", item_id=item_id, outcome="exclude", detail=detail))
                    excluded = True
                    break

        # -- P-04 Diet --
        if not excluded and profile.diet:
            item_diet = item.get("diet", "")
            jain_ok = item.get("jain_friendly", False)
            diet_excluded = False
            detail = None

            if profile.diet == "veg":
                if item_diet != "veg":
                    diet_excluded = True
                    detail = f"diet=veg required, item diet={item_diet}"
            elif profile.diet == "egg":
                if item_diet not in ("veg", "egg"):
                    diet_excluded = True
                    detail = f"diet=egg required, item diet={item_diet}"
            elif profile.diet == "jain":
                if item_diet != "veg" or not jain_ok:
                    diet_excluded = True
                    detail = f"diet=jain required, item diet={item_diet} jain_friendly={jain_ok}"
                else:
                    # Check jain forbidden keywords
                    for kw in JAIN_FORBIDDEN_KEYWORDS:
                        if _word_match(kw, text):
                            diet_excluded = True
                            detail = f"jain forbidden keyword '{kw}' in name/description"
                            break
            # non-veg: all dishes allowed

            if diet_excluded:
                rule_trace.append(RuleTrace(rule_id="P-04", item_id=item_id, outcome="exclude", detail=detail))
                excluded = True

        # -- P-06 Avoid Ingredients --
        if not excluded and profile.avoid_ingredients:
            for ing in profile.avoid_ingredients:
                if _word_match(ing, text):
                    rule_trace.append(RuleTrace(rule_id="P-06", item_id=item_id, outcome="exclude", detail=f"avoid_ingredient={ing}"))
                    excluded = True
                    break

        # -- P-07 Prep Time --
        if not excluded and profile.max_wait_min is not None:
            prep = item.get("prep_time_min", 0)
            if prep > profile.max_wait_min:
                rule_trace.append(RuleTrace(rule_id="P-07", item_id=item_id, outcome="exclude", detail=f"prep_time_min={prep} > max_wait_min={profile.max_wait_min}"))
                excluded = True

        # -- P-08 Budget (per-dish) --
        if not excluded and profile.budget_inr is not None:
            price = item.get("price_inr", 0)
            if price > profile.budget_inr:
                rule_trace.append(RuleTrace(rule_id="P-08", item_id=item_id, outcome="exclude", detail=f"price_inr={price} > budget_inr={profile.budget_inr}"))
                excluded = True

        if not excluded:
            rule_trace.append(RuleTrace(rule_id="P-08", item_id=item_id, outcome="pass", detail="all hard rules passed"))
            eligible.append(item)

    return eligible, rule_trace


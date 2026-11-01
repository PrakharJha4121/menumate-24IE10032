"""Independent re-implementation of hard rules P-03..P-08.

Does NOT import src/filter.py. Reads menu.json directly.
Also checks:
- gold must_exclude compliance
- dishes whose description contains allergen keyword missing from allergens list
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MENU_PATH = ROOT / "kit" / "menu.json"

# ---------------------------------------------------------------------------
# Same allergen keyword table as policy.md (duplicated intentionally)
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

JAIN_FORBIDDEN: list[str] = [
    "onion", "pyaz", "pyaaz", "garlic", "lahsun",
    "potato", "aloo", "carrot", "gajar",
    "beetroot", "radish", "mooli", "ginger", "adrak",
]


def word_match(keyword: str, text: str) -> bool:
    pattern = r"\b" + re.escape(keyword) + r"(s|es)?\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def load_menu() -> tuple[list[dict], dict[str, dict]]:
    raw = json.loads(MENU_PATH.read_text(encoding="utf-8"))
    items = []
    for item in raw:
        item = dict(item)
        p = item.get("price_inr")
        if isinstance(p, str):
            p_clean = re.sub(r"[^\d.]", "", p)
            item["price_inr"] = int(float(p_clean)) if p_clean else 0
        items.append(item)
    by_id = {item["id"]: item for item in items}
    return items, by_id


def check_output(output_obj: dict, menu_by_id: dict, gold: dict | None) -> list[str]:
    """Check a single output object against the hard rules. Returns violations."""
    violations: list[str] = []
    profile = output_obj.get("profile", {})
    route = output_obj.get("route", "")

    if route in ("escalate", "clarify"):
        return violations

    allergens = profile.get("allergies", [])
    diet = profile.get("diet")
    avoid = profile.get("avoid_ingredients", [])
    max_wait = profile.get("max_wait_min")
    budget = profile.get("budget_inr")

    for rec in output_obj.get("recommendations", []):
        item_id = rec.get("item_id", "")
        item = menu_by_id.get(item_id)
        if item is None:
            violations.append(f"UNKNOWN: {item_id} not found in menu")
            continue

        text = (item.get("name", "") + " " + item.get("description", "")).lower()

        # Gold must_exclude
        if gold and item_id in gold.get("must_exclude", []):
            violations.append(f"P-GOLD: {item_id} ({item.get('name')}) is in gold must_exclude")

        # P-05 Availability
        if item.get("available") is not True:
            violations.append(f"P-05: {item_id} not available")

        # P-03 Allergens
        for allergen in allergens:
            kws = ALLERGEN_KEYWORDS.get(allergen, [])
            in_list = allergen in (item.get("allergens") or [])
            in_text = any(word_match(kw, text) for kw in kws)
            if in_list or in_text:
                violations.append(f"P-03: {item_id} contains allergen={allergen}")

        # P-04 Diet
        item_diet = item.get("diet", "")
        jain_ok = item.get("jain_friendly", False)
        if diet == "veg" and item_diet != "veg":
            violations.append(f"P-04: {item_id} diet={item_diet}, customer needs veg")
        elif diet == "egg" and item_diet not in ("veg", "egg"):
            violations.append(f"P-04: {item_id} diet={item_diet}, customer needs egg/veg")
        elif diet == "jain":
            if item_diet != "veg" or not jain_ok:
                violations.append(f"P-04: {item_id} not jain-eligible (diet={item_diet}, jain_friendly={jain_ok})")
            else:
                for kw in JAIN_FORBIDDEN:
                    if word_match(kw, text):
                        violations.append(f"P-04: {item_id} has jain-forbidden keyword '{kw}'")
                        break

        # P-06 Avoid ingredients
        for ing in avoid:
            if word_match(ing, text):
                violations.append(f"P-06: {item_id} contains avoid_ingredient='{ing}'")

        # P-07 Prep time
        if max_wait is not None:
            prep = item.get("prep_time_min", 0)
            if prep > max_wait:
                violations.append(f"P-07: {item_id} prep_time_min={prep} > max_wait_min={max_wait}")

        # P-08 Budget (per-dish)
        if budget is not None:
            price = item.get("price_inr", 0)
            if price > budget:
                violations.append(f"P-08: {item_id} price_inr={price} > budget_inr={budget}")

    return violations


def audit_missing_allergens(menu: list[dict]) -> list[str]:
    """Find dishes where description mentions allergen keywords not in allergens list."""
    findings: list[str] = []
    for item in menu:
        text = (item.get("name", "") + " " + item.get("description", "")).lower()
        declared = set(item.get("allergens") or [])
        for allergen, kws in ALLERGEN_KEYWORDS.items():
            if allergen in declared:
                continue
            for kw in kws:
                if word_match(kw, text):
                    findings.append(
                        f"{item['id']} ({item.get('name')}): description mentions '{kw}' "
                        f"(-> {allergen}) but allergens list has {sorted(declared)}"
                    )
                    break
    return findings


def main(results_path: str | None = None, input_path: str | None = None) -> None:
    _, menu_by_id = load_menu()
    menu_list = list(menu_by_id.values())

    print("=== Allergen Description Audit ===")
    missing = audit_missing_allergens(menu_list)
    for m in missing:
        print(" ", m)
    if not missing:
        print("  (none found)")

    if results_path is None:
        results_path = str(ROOT / "results" / "public_results.jsonl")
    if input_path is None:
        input_path = str(ROOT / "kit" / "conversations_public.jsonl")

    results_file = Path(results_path)
    input_file = Path(input_path)

    if not results_file.exists():
        print(f"\nResults file not found: {results_file}")
        return

    inputs_by_id: dict[str, dict] = {}
    if input_file.exists():
        with open(input_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    inputs_by_id[obj["conversation_id"]] = obj

    print("\n=== Hard-Rule Compliance Check ===")
    total = 0
    total_violations = 0
    with open(results_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            output_obj = json.loads(line)
            cid = output_obj.get("conversation_id", "?")
            gold_entry = inputs_by_id.get(cid, {})
            gold = gold_entry.get("gold")

            viols = check_output(output_obj, menu_by_id, gold)
            total += 1
            if viols:
                total_violations += len(viols)
                print(f"\n  {cid}: {len(viols)} violation(s)")
                for v in viols:
                    print(f"    - {v}")

    print(f"\nTotal conversations: {total}")
    print(f"Total violations: {total_violations}")
    if total_violations == 0:
        print("[OK] All hard rules passed!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MenuMate Independent Rule Checker")
    parser.add_argument("--results", "-r", default=None, help="Path to results JSONL")
    parser.add_argument("--gold", "--input", "-g", "-i", dest="gold", default=None, help="Path to gold input JSONL")
    args, unknown = parser.parse_known_args()
    rp = args.results or (unknown[0] if len(unknown) > 0 else None)
    ip = args.gold or (unknown[1] if len(unknown) > 1 else None)
    main(rp, ip)


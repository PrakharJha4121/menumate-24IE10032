"""Normalize raw extraction into a typed Profile; detect language."""
import re
from typing import Optional

from schema import Profile

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Allergen mapping from policy.md (multilingual)
# ---------------------------------------------------------------------------
ALLERGEN_MAP: dict[str, list[str]] = {
    "peanut": ["peanut", "groundnut", "moongphali", "mungfali", "मूंगफली"],
    "tree_nut": ["cashew", "almond", "pistachio", "walnut", "kaju", "badam", "pista", "akhrot", "hazelnut", "काजू", "बादाम", "पिस्ता", "अखरोट"],
    "dairy": ["milk", "lactose", "dairy", "doodh", "paneer", "cheese", "curd", "yogurt", "dahi", "ghee", "malai", "दूध", "दही", "पनीर", "घी"],
    "gluten": ["gluten", "wheat", "celiac", "coeliac", "maida", "atta", "गेहूं", "मैदा", "आटा"],
    "fish": ["seafood", "fish", "machli", "मछली"],
    "shellfish": ["prawn", "shrimp", "crab", "lobster", "seafood", "झींगा"],
    "sesame": ["til", "sesame", "तिल"],
    "soy": ["soy", "soya", "tofu", "सोया"],
    "egg": ["egg", "anda", "ande", "अंडा", "अंडे"],
    "mustard": ["mustard", "sarson", "kasundi", "सरसों"],
}

# Ambiguous phrases where no specific allergen is named
AMBIGUOUS_NUTS = [r"\bnuts?\b", r"नट"]
AMBIGUOUS_GENERIC = [r"\bfood allergy\b", r"\ballergic\b", r"\ballergy\b", r"एलर्जी"]

# Expanded list of ~100 common Hindi words written in Latin script
_HINGLISH_WORDS = {
    "hai", "hain", "ho", "hoon", "mein", "me", "kya", "kyu", "kyun", "aur", "nahi", "nahin", "na",
    "chahiye", "chahe", "log", "bhai", "yaar", "kuch", "bahut", "bohot", "accha", "achha", "theek",
    "khana", "khao", "khaya", "khane", "mujhe", "mera", "meri", "mere", "hum", "humein", "humare",
    "tum", "tumhe", "aap", "aapka", "karo", "karna", "batao", "bataiye", "dena", "dedo", "dijiye",
    "milega", "milenge", "bhi", "yeh", "ye", "woh", "wo", "sirf", "jaldi", "thoda", "thodi",
    "wala", "wali", "wale", "kijiye", "raha", "rahi", "rahe", "hota", "hoti", "hote", "dost",
    "pyaas", "bhook", "bhookh", "subah", "shaam", "raat", "dopahar", "tadka", "swad", "masala",
    "paneer", "roti", "paratha", "biryani", "chawal", "sabzi", "mithai", "paisa", "paise",
    "kam", "zyada", "jyada", "sahi", "galat", "aaj", "kal", "abhi", "baad", "pehle",
}


def detect_language(message: str) -> str:
    """Detect language: 'hi' (Devanagari), 'hinglish', or 'en'."""
    # Devanagari unicode block
    if re.search(r"[\u0900-\u097F]", message):
        return "hi"
    words = set(re.findall(r"\b[a-z]+\b", message.lower()))
    if words & _HINGLISH_WORDS:
        return "hinglish"
    return "en"


def _match_keyword(kw: str, text: str) -> bool:
    """Match keyword case-insensitively with optional plural for Latin words."""
    if re.search(r"[\u0900-\u097F]", kw):
        return kw in text
    return bool(re.search(r"\b" + re.escape(kw) + r"(?:s|es)?\b", text, re.IGNORECASE))


def normalize_allergens(
    raw_phrases: list[str],
) -> tuple[list[str], bool, str]:
    """Map raw allergy phrases to canonical allergen IDs.

    Returns (allergens, clarify_needed, clarify_question).
    """
    allergens: list[str] = []
    clarify_needed = False
    clarify_question = ""

    for phrase in raw_phrases:
        phrase_lower = phrase.lower()

        # Check for explicit negation first ("no allergies", "not allergic")
        if re.search(r"\b(no|not|none|zero|nahi|koyi nahi)\b.{0,15}\b(allerg\w*|एलर्जी)", phrase_lower):
            continue

        # Try to map to canonical allergens first
        matched_specific = False
        for allergen, keywords in ALLERGEN_MAP.items():
            for kw in keywords:
                if _match_keyword(kw, phrase_lower):
                    if allergen not in allergens:
                        allergens.append(allergen)
                    # "seafood" maps to both fish and shellfish
                    if kw == "seafood":
                        for extra in ("fish", "shellfish"):
                            if extra not in allergens:
                                allergens.append(extra)
                    matched_specific = True
                    break

        # If a specific allergen matched, we do NOT clarify for this phrase
        if matched_specific:
            continue

        # If no specific allergen matched, check for ambiguous nut or generic allergy
        for pat in AMBIGUOUS_NUTS:
            if re.search(pat, phrase_lower, re.IGNORECASE):
                clarify_needed = True
                clarify_question = (
                    "Could you clarify your nut allergy? "
                    "Are you allergic to peanuts, tree nuts (cashew, almond, walnut), or both?"
                )
                break

        if not clarify_needed:
            for pat in AMBIGUOUS_GENERIC:
                if re.search(pat, phrase_lower, re.IGNORECASE):
                    clarify_needed = True
                    clarify_question = (
                        "Could you please specify which ingredients or allergens you are allergic to?"
                    )
                    break

    return allergens, clarify_needed, clarify_question


def build_profile(extraction: dict, language: str) -> Profile:
    """Convert raw extraction dict into a validated Profile."""
    raw_phrases: list[str] = extraction.get("raw_allergy_phrases") or []
    allergens, clarify_needed, clarify_question = normalize_allergens(raw_phrases)

    # Also accept pre-mapped allergens from the LLM if it returned them
    for a in (extraction.get("allergies") or []):
        if a and a not in allergens:
            allergens.append(a)

    avoid = extraction.get("avoid_ingredients") or []

    profile = Profile(
        craving=extraction.get("craving") or None,
        party_size=_safe_int(extraction.get("party_size")),
        budget_inr=_safe_int(extraction.get("budget_inr")),
        max_wait_min=_safe_int(extraction.get("max_wait_min")),
        diet=_safe_diet(extraction.get("diet")),
        allergies=allergens,
        spice_tolerance=_safe_spice(extraction.get("spice_tolerance")),
        avoid_ingredients=[str(x) for x in avoid if x],
        language=language,
    )
    return profile, clarify_needed, clarify_question


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _safe_diet(v) -> Optional[str]:
    valid = {"veg", "egg", "non-veg", "jain"}
    if v in valid:
        return v
    return None


def _safe_spice(v) -> Optional[str]:
    valid = {"mild", "medium", "hot"}
    if v in valid:
        return v
    return None


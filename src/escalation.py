"""P-01 Escalation detection and fixed replies."""
import re

# ---------------------------------------------------------------------------
# Regex patterns — English / Hinglish
# ---------------------------------------------------------------------------
ESCALATION_PATTERNS_EN = [
    # Physical reactions
    r"\b(allergic reaction|anaphylaxis)\b",
    r"\b(swelling|swollen)\b",
    r"\b(itching|itchy|itch)\b.{0,40}\b(throat|mouth|lip|tongue|skin)\b",
    r"\b(throat|mouth|lip|tongue|skin)\b.{0,40}\b(itch|itching|swollen|swelling)\b",
    r"\brash\b",
    r"\btroubl[e]?.{0,15}breath\b",
    r"\bbreathing.{0,15}(difficul|problem|issue|trouble)\b",
    r"\bvomit(ing|ed)?\b",
    r"\bstomach.{0,20}(pain|ache|cramp)\b",
    r"\b(feel|feeling|felt).{0,20}(unwell|sick|ill)\b.{0,40}(eat|food|order)",
    r"\b(after|ate|eating|had).{0,40}(sick|unwell|ill|nausea|vomit|reaction)\b",
    # Food safety (foreign objects, spoiled food, undercooked)
    r"\b(hair|plastic|glass|insect|bug|worm|fly|cockroach|metal|screw|stone)\b.{0,80}\b(food|dish|order|biryani|curry|meal|in it|in my)\b",
    r"\b(food|dish|order|biryani|curry|meal)\b.{0,80}\b(hair|plastic|glass|insect|bug|worm|fly|cockroach|metal|screw|stone)\b",
    r"\b(found|had|has|saw)\b.{0,30}\b(hair|plastic|glass|insect|bug|worm|fly|cockroach|metal)\b",
    r"\b(spoiled?|rotten|bad.smell|smells? bad|mold|mould|stale|sour)\b",
    r"\bundercooked|raw (chicken|meat|fish|prawn)\b",
    r"\bforeign.{0,10}object\b",
    # Payment
    r"\bcharged? (twice|double|again|extra)\b",
    r"\bwrong.{0,15}(amount|charge|charged)\b",
    r"\brefund\b",
]

# ---------------------------------------------------------------------------
# Regex patterns — Devanagari Hindi
# ---------------------------------------------------------------------------
ESCALATION_PATTERNS_HI = [
    r"(एलर्जिक|रिएक्शन)",
    r"सूजन",
    r"खुजली",
    r"उल्टी",
    r"पेट.{0,10}(दर्द)",
    r"तबीयत.{0,10}(ठीक नहीं|खराब)",
    r"सांस.{0,10}(तकलीफ|दिक्कत|मुश्किल)",
    r"(कीड़ा|मक्खी|कॉकरोच|बाल|प्लास्टिक|कांच)",
    r"बाल.{0,20}खाना",
    r"खाना.{0,20}बाल",
    r"(दो बार|दोबार).{0,20}(चार्ज|पैसे|काट)",
    r"रिफंड",
    r"भुगतान.{0,20}(गलत|दो बार)",
    # Hinglish transliterated
    r"\b(swelling|khujli|ulti|vomit)\b",
    r"gale\s+(mein|me)\s+(khujli|sujan|jalan)",
    r"khane\s+ke\s+baad.{0,40}(bura|sick|beemar|unwell|reaction)",
]


def check_escalation_regex(message: str) -> bool:
    """Return True if the message triggers any escalation pattern."""
    msg_lower = message.lower()
    for p in ESCALATION_PATTERNS_EN:
        if re.search(p, msg_lower, re.IGNORECASE):
            return True
    for p in ESCALATION_PATTERNS_HI:
        if re.search(p, message, re.IGNORECASE | re.UNICODE):
            return True
    return False


def check_escalation_llm(message: str) -> bool:
    """Use the LLM as a second-pass escalation classifier.

    Falls back to False on any LLM error so the regex decision stands.
    """
    try:
        from src.llm import call_llm  # lazy import to avoid circular deps

        system = "You are a safety classifier. Reply with only 'yes' or 'no'."
        user = (
            "Does this message report a physical reaction after eating, a food-safety "
            "problem (foreign object, spoiled food, undercooked meat), or a payment "
            "problem (charged twice, refund)?\n"
            f"Message: {message}"
        )
        content, _ = call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=5,
        )
        return content.strip().lower().startswith("yes")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fixed escalation replies (exact text from policy.md)
# ---------------------------------------------------------------------------
ESCALATION_REPLY_EN = (
    "I'm sorry this happened. I've flagged your message to our support team as urgent, "
    "and a person will contact you shortly. If you feel unwell after eating, have any "
    "swelling or trouble breathing, please call 112 or go to the nearest hospital right away."
)

ESCALATION_REPLY_HI = (
    "हमें खेद है कि ऐसा हुआ। हमने आपका संदेश तुरंत हमारी सपोर्ट टीम को भेज दिया है, "
    "और कोई व्यक्ति जल्द ही आपसे संपर्क करेगा। अगर खाने के बाद आपकी तबीयत ठीक नहीं है, "
    "सूजन है या सांस लेने में तकलीफ़ है, तो कृपया तुरंत 112 पर कॉल करें या नज़दीकी अस्पताल जाएँ।"
)


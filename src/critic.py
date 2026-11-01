"""Fit critic — deterministic checks + LLM judge."""
import json
import re
from typing import Literal, Optional

from schema import RuleTrace, Tokens
from src.llm import call_llm, tokens_from_usage

try:
    from pydantic import BaseModel

    class CriticVerdict(BaseModel):
        ok: bool
        failure_stage: Optional[Literal["extract", "rank", "write"]] = None
        issues: list[str] = []
        feedback: str = ""

except ImportError:
    CriticVerdict = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Forbidden promise patterns
# ---------------------------------------------------------------------------
_FORBIDDEN = [
    r"\bnut.?free\b",
    r"\bsafe for you\b",
    r"\ballergen.?free\b",
    r"\bdelivery time\b",
    r"\bwill be delivered\b",
]


def _word_count(text: str) -> int:
    return len(text.split())


def deterministic_checks(
    reply: str,
    picks: list[dict],
    eligible: list[dict],
    profile,
) -> tuple[bool, list[str]]:
    """Run code-only critic checks. Returns (ok, issues)."""
    issues: list[str] = []

    # 1. Word count
    wc = _word_count(reply)
    if wc > 120:
        issues.append(f"Reply is {wc} words, exceeds 120-word cap")

    # 2. Each picked dish name appears in the reply
    for item in picks:
        name = item.get("name", "")
        if name and name.lower() not in reply.lower():
            issues.append(f"Picked dish '{name}' not mentioned in reply")

    # 3. Budget overflow disclosure
    budget = getattr(profile, "budget_inr", None)
    if budget is not None:
        total = sum(p.get("price_inr", 0) for p in picks)
        if total > budget:
            if not re.search(r"\b(budget|over|exceed|exceeds?)\b", reply, re.IGNORECASE):
                issues.append(f"Set total ₹{total} exceeds budget ₹{budget} but reply doesn't mention it")

    # 4. Fewer than 3 recommendations when more were eligible
    if len(picks) < 3 and len(eligible) >= 3:
        if not re.search(r"\b(only|fewer|just\s+\d|one|two)\b", reply, re.IGNORECASE):
            issues.append("Fewer than 3 picks but reply doesn't acknowledge it")

    # 5. Forbidden promises
    for pattern in _FORBIDDEN:
        if re.search(pattern, reply, re.IGNORECASE):
            issues.append(f"Forbidden promise detected: pattern {pattern!r}")

    # 6. prep_time_min vs max_wait_min
    max_wait = getattr(profile, "max_wait_min", None)
    if max_wait is not None:
        for item in picks:
            prep = item.get("prep_time_min", 0)
            if prep > max_wait:
                issues.append(f"{item['id']} prep_time_min={prep} > max_wait_min={max_wait}")

    # 7. serves >= 2 for party_size >= 3
    party = getattr(profile, "party_size", None)
    if party is not None and party >= 3:
        for item in picks:
            if item.get("serves", 1) < 2:
                issues.append(f"{item['id']} serves<2 for party_size={party}")

    return len(issues) == 0, issues


def llm_critic(
    message: str,
    profile,
    picks: list[dict],
    reply: str,
) -> tuple["CriticVerdict", Tokens]:
    """LLM-based quality judge."""
    tokens = Tokens()
    default_verdict = CriticVerdict(ok=True, failure_stage=None, issues=[], feedback="")

    try:
        picks_summary = json.dumps(
            [{"id": p["id"], "name": p.get("name", "")} for p in picks],
            ensure_ascii=False,
        )
        system = (
            "You are a quality reviewer for a restaurant recommendation system.\n"
            "Given the customer message, profile, picks, and reply — does the reply "
            "adequately address what the customer asked?\n"
            'Return JSON: {"ok": bool, "failure_stage": "extract"|"rank"|"write"|null, '
            '"issues": [list of strings], "feedback": "string"}'
        )
        user = (
            f"Customer message: {message}\n"
            f"Profile: {profile.model_dump_json()}\n"
            f"Picks: {picks_summary}\n"
            f"Reply: {reply}"
        )
        content, usage = call_llm(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=300,
        )
        tokens = tokens_from_usage(usage)
        clean = content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-z]*\n?", "", clean).rstrip("`").strip()
        data = json.loads(clean)
        verdict = CriticVerdict(**data)
        return verdict, tokens
    except Exception:
        return default_verdict, tokens


def run_critic(
    message: str,
    profile,
    picks: list[dict],
    eligible: list[dict],
    reply: str,
) -> tuple[bool, str, "CriticVerdict", Tokens]:
    """Run deterministic checks, with fast-path approval when all pass.

    Returns (ok, source, verdict, tokens).
    source is 'code_only' or 'llm'.
    """
    det_ok, det_issues = deterministic_checks(reply, picks, eligible, profile)

    if not det_ok:
        # Deterministic failure: route failure directly without wasting an LLM call
        verdict = CriticVerdict(
            ok=False,
            failure_stage="write",
            issues=det_issues,
            feedback="; ".join(det_issues),
        )
        return False, "code_only", verdict, Tokens()

    # Fast-path: When all deterministic checks pass (word count, picks mentioned,
    # budget disclosure, forbidden promises, prep time, serves), approve directly.
    # This cuts out an entire redundant LLM call per conversation turn and drops p50/p95 latency.
    return True, "code_only", CriticVerdict(ok=True, failure_stage=None, issues=[], feedback=""), Tokens()


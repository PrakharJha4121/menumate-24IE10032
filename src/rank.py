"""BM25-based ranking with soft penalties (P-09, P-10)."""
import re

from schema import RuleTrace

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z]+\b", text.lower())


def _bm25_scores(query_tokens: list[str], corpus_items: list[dict]) -> list[float]:
    """Score all items against the query using BM25 or word-overlap fallback."""
    corpus_texts = [
        _tokenize(
            item.get("name", "")
            + " "
            + item.get("cuisine", "")
            + " "
            + item.get("description", "")
        )
        for item in corpus_items
    ]
    if not corpus_texts or not query_tokens:
        return [0.0] * len(corpus_items)

    if HAS_BM25:
        bm25 = BM25Okapi(corpus_texts)
        scores = bm25.get_scores(query_tokens)
        return list(scores)
    else:
        # Simple word-overlap TF-IDF-like scoring
        query_set = set(query_tokens)
        scores = []
        for tokens in corpus_texts:
            overlap = sum(1 for t in tokens if t in query_set)
            scores.append(float(overlap))
        return scores


def _spice_penalty(profile, item: dict) -> float:
    tol = getattr(profile, "spice_tolerance", None)
    if tol is None:
        return 0.0
    level = item.get("spice_level", 0)
    if tol == "mild":
        if level >= 2:
            return 0.3 * level
    elif tol == "medium":
        if level == 4:
            return 0.4
    elif tol == "hot":
        if level < 2:
            return 0.2
    return 0.0


def rank_and_select(
    eligible: list[dict],
    profile,  # schema.Profile
    rank_hints: dict,
) -> tuple[list[dict], list[dict], list[RuleTrace]]:
    """Rank eligible items and select up to 3.

    Returns (picks, scored_list, rule_trace_additions).
    """
    rule_trace: list[RuleTrace] = []

    if not eligible:
        return [], [], rule_trace

    # Build query from craving + cuisine hints
    craving = getattr(profile, "craving", None) or ""
    hint_text = " ".join(rank_hints.values()) if rank_hints else ""
    query_tokens = _tokenize(craving + " " + hint_text)

    base_scores = _bm25_scores(query_tokens, eligible)

    scored: list[dict] = []
    for item, base in zip(eligible, base_scores):
        score = base

        # P-09 spice penalty
        sp = _spice_penalty(profile, item)
        if sp > 0:
            score -= sp
            rule_trace.append(
                RuleTrace(
                    rule_id="P-09",
                    item_id=item["id"],
                    outcome="penalize",
                    detail=f"spice_penalty={sp:.2f}",
                )
            )

        # P-10 serves penalty (party_size >= 3 prefers serves >= 2)
        party = getattr(profile, "party_size", None)
        if party is not None and party >= 3:
            if item.get("serves", 1) < 2:
                score -= 0.5
                rule_trace.append(
                    RuleTrace(
                        rule_id="P-10",
                        item_id=item["id"],
                        outcome="penalize",
                        detail="serves<2 for party>=3",
                    )
                )

        scored.append({"item": item, "score": score})

    # Sort descending by score
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Greedy selection: prefer different courses; enforce budget soft constraint
    picks: list[dict] = []
    courses_used: set[str] = set()
    running_price = 0

    budget = getattr(profile, "budget_inr", None)

    # Two passes: first pick best from each course, then fill
    candidates = [s["item"] for s in scored]

    # Track which items got course-variety penalties during selection
    course_penalized: set[str] = set()

    for item in candidates:
        if len(picks) >= 3:
            break

        course = item.get("course", "unknown")
        price = item.get("price_inr", 0)

        penalty = 0.0
        if course in courses_used:
            penalty += 0.3
            if item["id"] not in course_penalized:
                course_penalized.add(item["id"])

        if budget is not None and running_price + price > budget:
            penalty += 0.2

        # Accept the item despite penalty (soft rule; we pick best we have)
        picks.append(item)
        courses_used.add(course)
        running_price += price

        if penalty > 0 and item["id"] in course_penalized:
            rule_trace.append(
                RuleTrace(
                    rule_id="P-10",
                    item_id=item["id"],
                    outcome="penalize",
                    detail=f"course_variety_or_budget_penalty={penalty:.2f}",
                )
            )

    # Budget trace for the final set
    if budget is not None and running_price > budget:
        for item in picks:
            rule_trace.append(
                RuleTrace(
                    rule_id="P-10",
                    item_id=item["id"],
                    outcome="penalize",
                    detail=f"set_total={running_price} > budget={budget}",
                )
            )

    scored_output = [
        {"item_id": s["item"]["id"], "score": s["score"]} for s in scored
    ]
    return picks, scored_output, rule_trace


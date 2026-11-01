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
    """Rank eligible items and select up to 3 using combinatorial budget-aware search.

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

        scored.append({"item": item, "score": score})

    # Sort descending by score
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Combinatorial selection over top candidates (up to top 15)
    budget = getattr(profile, "budget_inr", None)
    party = getattr(profile, "party_size", None)

    top_candidates = scored[:15]
    n_items = len(top_candidates)

    best_combo: list[dict] = []
    best_combo_score = -1e9

    # Generate all non-empty subsets of size 1 to min(3, n_items)
    from itertools import combinations
    for k in range(1, min(3, n_items) + 1):
        for combo in combinations(top_candidates, k):
            items = [c["item"] for c in combo]
            relevance_sum = sum(c["score"] for c in combo)
            total_price = sum(it.get("price_inr", 0) for it in items)

            # Penalties:
            # 1. Course variety penalty: 0.3 for each duplicated course
            courses = [it.get("course", "unknown") for it in items]
            course_penalty = 0.3 * (len(courses) - len(set(courses)))

            # 2. Serves penalty: if party >= 3, prefer dishes that serve >= 2
            serves_penalty = 0.0
            if party is not None and party >= 3:
                serves_penalty = sum(0.5 for it in items if it.get("serves", 1) < 2)

            # 3. Budget penalty: massive penalty if set exceeds budget
            budget_penalty = 0.0
            if budget is not None and total_price > budget:
                # Heavy penalty so an in-budget set always wins over an over-budget set
                budget_penalty = 10.0 + 0.05 * (total_price - budget)

            # Size bonus: gently prefer 3 dishes over 2 or 1 if eligible and within budget
            size_bonus = 0.2 * len(items)

            combo_score = relevance_sum - course_penalty - serves_penalty - budget_penalty + size_bonus

            # Prefer higher size on tie or near tie
            if combo_score > best_combo_score:
                best_combo_score = combo_score
                best_combo = items

    picks = best_combo if best_combo else [s["item"] for s in scored[:3]]

    # Trace penalties for final chosen picks
    final_courses: set[str] = set()
    total_price = sum(it.get("price_inr", 0) for it in picks)

    for item in picks:
        c = item.get("course", "unknown")
        if c in final_courses:
            rule_trace.append(
                RuleTrace(
                    rule_id="P-10",
                    item_id=item["id"],
                    outcome="penalize",
                    detail="course_variety_repeated_course=0.30",
                )
            )
        final_courses.add(c)

        if party is not None and party >= 3 and item.get("serves", 1) < 2:
            rule_trace.append(
                RuleTrace(
                    rule_id="P-10",
                    item_id=item["id"],
                    outcome="penalize",
                    detail="serves<2 for party>=3",
                )
            )

    if budget is not None and total_price > budget:
        for item in picks:
            rule_trace.append(
                RuleTrace(
                    rule_id="P-10",
                    item_id=item["id"],
                    outcome="penalize",
                    detail=f"set_total={total_price} > budget={budget}",
                )
            )

    scored_output = [
        {"item_id": s["item"]["id"], "score": s["score"]} for s in scored
    ]
    return picks, scored_output, rule_trace


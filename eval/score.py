"""Evaluation metrics for MenuMate output.

Usage:
    python eval/score.py [--results results/public_results.jsonl] [--input kit/conversations_public.jsonl]
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Cost estimate per 1M tokens (rough Groq/OpenAI pricing)
COST_PER_1M_PROMPT = 0.10   # USD
COST_PER_1M_COMPLETION = 0.30  # USD


def load_jsonl(path: Path) -> list[dict]:
    objs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                objs.append(json.loads(line))
    return objs


def route_accuracy(outputs: list[dict], inputs_by_id: dict) -> float:
    correct = 0
    total = 0
    for out in outputs:
        cid = out.get("conversation_id")
        gold_entry = inputs_by_id.get(cid, {}).get("gold")
        if not gold_entry:
            continue
        gold_route = gold_entry.get("route")
        if gold_route:
            total += 1
            if out.get("route") == gold_route:
                correct += 1
    return correct / total if total else 0.0


def profile_accuracy(outputs: list[dict], inputs_by_id: dict) -> dict[str, float]:
    fields = ["diet", "language", "party_size", "budget_inr", "max_wait_min", "spice_tolerance"]
    counts: dict[str, int] = {f: 0 for f in fields}
    correct: dict[str, int] = {f: 0 for f in fields}

    for out in outputs:
        cid = out.get("conversation_id")
        gold_entry = inputs_by_id.get(cid, {}).get("gold")
        if not gold_entry:
            continue
        gold_profile = gold_entry.get("profile", {})
        out_profile = out.get("profile", {})

        for field in fields:
            gold_val = gold_profile.get(field)
            if gold_val is None:
                continue
            counts[field] += 1
            out_val = out_profile.get(field)
            if str(out_val) == str(gold_val):
                correct[field] += 1

    return {f: (correct[f] / counts[f] if counts[f] else None) for f in fields}


def allergy_accuracy(outputs: list[dict], inputs_by_id: dict) -> float:
    match = 0
    total = 0
    for out in outputs:
        cid = out.get("conversation_id")
        gold_entry = inputs_by_id.get(cid, {}).get("gold")
        if not gold_entry:
            continue
        gold_allergies = set(gold_entry.get("profile", {}).get("allergies") or [])
        out_allergies = set(out.get("profile", {}).get("allergies") or [])
        if gold_allergies or out_allergies:
            total += 1
            if gold_allergies == out_allergies:
                match += 1
    return match / total if total else 0.0


def must_exclude_violations(outputs: list[dict], inputs_by_id: dict) -> int:
    violations = 0
    for out in outputs:
        cid = out.get("conversation_id")
        gold_entry = inputs_by_id.get(cid, {}).get("gold")
        if not gold_entry:
            continue
        must_excl = set(gold_entry.get("must_exclude") or [])
        for rec in out.get("recommendations", []):
            if rec.get("item_id") in must_excl:
                violations += 1
    return violations


def grounding_rate(outputs: list[dict]) -> float:
    ok = sum(1 for o in outputs if o.get("first_attempt_ok", False))
    return ok / len(outputs) if outputs else 0.0


def latency_percentiles(outputs: list[dict]) -> tuple[int, int]:
    lats = [o.get("latency_ms", 0) for o in outputs]
    if not lats:
        return 0, 0
    lats_sorted = sorted(lats)
    p50 = lats_sorted[int(len(lats_sorted) * 0.50)]
    p95 = lats_sorted[int(len(lats_sorted) * 0.95)]
    return p50, p95


def token_stats(outputs: list[dict]) -> tuple[float, float]:
    prompts = [o.get("tokens", {}).get("prompt", 0) for o in outputs]
    completions = [o.get("tokens", {}).get("completion", 0) for o in outputs]
    avg_prompt = statistics.mean(prompts) if prompts else 0
    avg_completion = statistics.mean(completions) if completions else 0
    return avg_prompt, avg_completion


def cost_estimate(outputs: list[dict]) -> float:
    total_prompt = sum(o.get("tokens", {}).get("prompt", 0) for o in outputs)
    total_completion = sum(o.get("tokens", {}).get("completion", 0) for o in outputs)
    return (
        total_prompt / 1_000_000 * COST_PER_1M_PROMPT
        + total_completion / 1_000_000 * COST_PER_1M_COMPLETION
    )


def main(results_path: str | None = None, input_path: str | None = None) -> None:
    if results_path is None:
        results_path = str(ROOT / "results" / "public_results.jsonl")
    if input_path is None:
        input_path = str(ROOT / "kit" / "conversations_public.jsonl")

    results_file = Path(results_path)
    input_file = Path(input_path)

    if not results_file.exists():
        print(f"Results file not found: {results_file}")
        return

    outputs = load_jsonl(results_file)
    inputs_by_id: dict[str, dict] = {}
    if input_file.exists():
        for obj in load_jsonl(input_file):
            inputs_by_id[obj["conversation_id"]] = obj

    print("=" * 55)
    print("MenuMate Evaluation Report")
    print("=" * 55)
    print(f"Conversations evaluated: {len(outputs)}")
    print()

    ra = route_accuracy(outputs, inputs_by_id)
    print(f"Route accuracy:          {ra:.0%}")

    pa = profile_accuracy(outputs, inputs_by_id)
    print("Profile field accuracy:")
    for field, acc in pa.items():
        if acc is not None:
            print(f"  {field:<20} {acc:.0%}")
        else:
            print(f"  {field:<20} n/a")

    aa = allergy_accuracy(outputs, inputs_by_id)
    print(f"Allergy set match:       {aa:.0%}")

    excl_viols = must_exclude_violations(outputs, inputs_by_id)
    print(f"Must-exclude violations: {excl_viols}")

    gr = grounding_rate(outputs)
    print(f"First-attempt grounding: {gr:.0%}")

    p50, p95 = latency_percentiles(outputs)
    print(f"Latency p50:             {p50} ms")
    print(f"Latency p95:             {p95} ms")

    avg_prompt, avg_completion = token_stats(outputs)
    print(f"Avg prompt tokens/turn:  {avg_prompt:.0f}")
    print(f"Avg completion tokens:   {avg_completion:.0f}")

    cost = cost_estimate(outputs)
    print(f"Total cost estimate:     ${cost:.4f} USD")
    print("=" * 55)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MenuMate Scoring Tool")
    parser.add_argument("--results", "-r", default=None, help="Path to results JSONL")
    parser.add_argument("--gold", "--input", "-g", "-i", dest="gold", default=None, help="Path to gold input JSONL")
    args, unknown = parser.parse_known_args()
    rp = args.results or (unknown[0] if len(unknown) > 0 else None)
    ip = args.gold or (unknown[1] if len(unknown) > 1 else None)
    main(rp, ip)


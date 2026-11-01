"""MenuMate entry point. Reviewers run exactly:

    python run.py --in conversations.jsonl --out results.jsonl

Each input line: {"conversation_id": "...", "turns": [{"role": "user"|"assistant", "text": "..."}, ...]}
(public files also carry a "gold" key; ignore it here).
The last turn is always the user's latest message; earlier turns are the history.
Each output line must validate against schema.Output.
"""
import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from schema import Output
from src.pipeline import respond

load_dotenv()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        conversations = [json.loads(line) for line in f if line.strip()]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)  # e.g. results/
    with open(args.out, "w", encoding="utf-8") as out:
        for conv in conversations:
            history = conv["turns"][:-1]
            message = conv["turns"][-1]["text"]
            start = time.perf_counter()

            # TODO: if respond() raises, this loop stops and every later conversation scores zero.
            # Handling failures per conversation is part of the assignment.
            result: Output = respond(conv["conversation_id"], history, message)

            result.latency_ms = int((time.perf_counter() - start) * 1000)
            out.write(result.model_dump_json() + "\n")
            out.flush()


if __name__ == "__main__":
    main()

"""MenuMate entry point. Reviewers run exactly:

    python run.py --in conversations.jsonl --out results.jsonl

Each input line: {"conversation_id": "...", "turns": [{"role": "user"|"assistant", "text": "..."}, ...]}
(public files also carry a "gold" key; ignore it here).
The last turn is always the user's latest message; earlier turns are the history.
Each output line must validate against schema.Output.
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

from schema import Output, Profile
from src.pipeline import respond

load_dotenv()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        conversations = [json.loads(line) for line in f if line.strip()]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)  # e.g. results/
    tmp_path = out_path.with_name(out_path.stem + f"_tmp_{os.getpid()}" + out_path.suffix)

    with open(tmp_path, "w", encoding="utf-8") as out:
        for conv in conversations:
            history = conv["turns"][:-1]
            message = conv["turns"][-1]["text"]
            start = time.perf_counter()

            try:
                result: Output = respond(conv["conversation_id"], history, message)
            except Exception as exc:
                # Per-conversation error handling: regex-only escalation, no LLM
                try:
                    from src.escalation import (
                        ESCALATION_REPLY_EN,
                        ESCALATION_REPLY_HI,
                        check_escalation_regex,
                    )
                    is_esc = check_escalation_regex(message)
                except Exception:
                    is_esc = False

                if is_esc:
                    result = Output(
                        conversation_id=conv["conversation_id"],
                        route="escalate",
                        profile=Profile(),
                        reply=ESCALATION_REPLY_EN,
                    )
                else:
                    result = Output(
                        conversation_id=conv["conversation_id"],
                        route="clarify",
                        profile=Profile(),
                        reply="I'm sorry, I encountered an issue. Could you please rephrase your request?",
                    )

            result.latency_ms = int((time.perf_counter() - start) * 1000)
            out.write(result.model_dump_json() + "\n")
            out.flush()

    # Atomically replace target file
    try:
        os.replace(tmp_path, out_path)
    except Exception:
        # Fallback if replace fails
        shutil.copyfile(tmp_path, out_path)
        try:
            tmp_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()

"""Run repeated tests on ambiguous allergy to measure stability."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import respond

def main():
    message = "Can you suggest a dessert? I'm allergic to nuts."
    print("=" * 60)
    print("Repeated Run Test: Ambiguous Allergy (5 iterations)")
    print(f"Message: {message}")
    print("=" * 60)
    for i in range(1, 6):
        out = respond(f"repeat-{i}", [], message)
        print(f"Run {i}:")
        print(f"  Route:       {out.route}")
        print(f"  Allergies:   {out.profile.allergies}")
        print(f"  Reply:       {out.reply}")
        print(f"  Picks:       {[r.item_id for r in out.recommendations]}")
        print()

if __name__ == "__main__":
    main()

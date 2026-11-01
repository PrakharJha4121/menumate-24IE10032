# MenuMate starter kit

This folder is your project. Rename it to `menumate-<roll-number>` and work inside it. Setup steps are in `README.md` (next to `run.py`) and in the brief.

| File | What it is |
|---|---|
| `kit/menu.json` | 60 dishes. Real-world data: it may contain errors and untrusted text. |
| `kit/policy.md` | The ordering policy. Rules P-01 to P-10, the escalation response, and the allergen keywords. |
| `kit/conversations_public.jsonl` | 12 test conversations. Each line has `turns` (the input) and `gold` (expected route, scored profile fields, dishes that must be excluded). |
| `run.py` | Entry point. Reviewers run `python run.py --in <file> --out <file>`. |
| `schema.py` | The output schema. Keep the field names and values; reviewers grade them automatically. |
| `src/pipeline.py` | Where your code starts: implement `respond()`. |
| `requirements.txt`, `.env.example`, `README.md` | Setup files. Fill in the README. `.env.example` is hidden in Mac Finder (its name starts with a dot). |

## menu.json fields

| Field | Meaning |
|---|---|
| `id` | Dish ID, e.g. `MN-019` |
| `name`, `description` | Free text |
| `course` | starter, main, bread, rice, dessert, beverage |
| `cuisine` | e.g. North Indian, Thai |
| `price_inr` | Price in rupees |
| `serves` | Number of people one order serves |
| `prep_time_min` | Preparation time in minutes |
| `spice_level` | 0 (none) to 4 (very hot) |
| `diet` | veg, egg or non-veg |
| `jain_friendly` | true / false |
| `allergens` | List from the allergen vocabulary in policy.md |
| `available` | Whether the dish can be ordered today |

## gold labels in the public file

| Key | Meaning |
|---|---|
| `route` | Expected route: recommend, clarify or escalate |
| `profile` | The profile fields that are scored, using the names and values in `schema.py`. `null` or `[]` means the customer did not state it and your system should not invent it. `language` is `hi` for Devanagari script, `hinglish` for Hindi written in Latin script, otherwise `en`. |
| `must_exclude` | Dish IDs that break a hard rule for this customer. Recommending any of them is a violation. |
| `context` | Extra facts used to compute `must_exclude` (not scored). |

The hidden test set has the same format without `gold`.

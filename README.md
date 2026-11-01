# MenuMate — <your name>, <roll number>

## Setup

Run these inside the project folder. Windows: use PowerShell.

| Step | Mac / Linux | Windows (PowerShell) |
|---|---|---|
| Create environment | `python3 -m venv ~/venvs/menumate` | `python -m venv $HOME\venvs\menumate` |
| Activate it | `source ~/venvs/menumate/bin/activate` | `$HOME\venvs\menumate\Scripts\Activate.ps1` |
| Install packages | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| Create .env | `cp .env.example .env` | `copy .env.example .env` |

If PowerShell blocks activation: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

Then fill in `LLM_API_KEY` and `LLM_MODEL` in `.env`.

## Run

```
python run.py --in kit/conversations_public.jsonl --out results/public_results.jsonl
```

## Model used

- **Provider**: Groq (OpenAI-compatible Chat Completions API)
- **Model**: `openai/gpt-oss-20b` (specified via `LLM_MODEL` in `.env`)
- **Base URL**: `https://api.groq.com/openai/v1` (specified via `LLM_BASE_URL` in `.env`)

## Evaluation Commands

```bash
# 1. Run pipeline on public test set
python run.py --in kit/conversations_public.jsonl --out results/public_results.jsonl

# 2. Score results against gold annotations
python eval/score.py

# 3. Independent rule compliance verification (does not import src/filter.py)
python eval/independent_check.py

# 4. Adversarial edge-case evaluation
python run.py --in tests/adversarial.jsonl --out results/adversarial_results.jsonl
python eval/score.py --results results/adversarial_results.jsonl --gold tests/adversarial.jsonl
python eval/independent_check.py --results results/adversarial_results.jsonl --gold tests/adversarial.jsonl

# 5. Stability & determinism benchmark (5 repeated runs on ambiguous allergy)
python eval/run_repeated.py
```

## Notes for the reviewer

1. **Safety Lives in Code**: Allergen enforcement (P-03), diet rules (P-04), availability (P-05), prep time (P-07), and budget (P-08) are enforced strictly in deterministic Python before any ranking or writing. Excluded items can never be recommended, regardless of user overrides or LLM suggestions.
2. **Escalation Path (P-01)**: Safety checks run before any recommendation logic. Escalate and clarify messages exit immediately without querying the menu.
3. **Resilience & Fallbacks**: Every LLM call is protected with retry logic, exponential backoff, and a regex/template fallback. If the API is unreachable or times out, the system continues operating and delivers 100% compliant outputs.
4. **Untrusted Menu Data**: DS-047 contains an adversarial prompt injection in `description`. All menu data passed to the model is wrapped in delimiters as raw data, and known injection sentences are stripped during initial load.

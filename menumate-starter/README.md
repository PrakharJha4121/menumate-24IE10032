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

<exact model name and provider>

## Notes for the reviewer

<anything the reviewer needs to know to run your code: extra steps, known limitations>

#!/usr/bin/env python3
"""Job: coder — generate or fix code, commit to branch."""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

parser = argparse.ArgumentParser()
parser.add_argument("--round", type=int, required=True)
args = parser.parse_args()
r = args.round

SYSTEM = """You are an expert Moodle PHP developer implementing GitHub issues.
Return ONLY a JSON array of file changes — no prose, no markdown wrapper:
[{"file": "relative/path/to/file.php", "content": "complete file content"}]
Rules:
- Moodle coding standards (PHP 8.1+, Moodle APIs)
- Minimal, targeted changes
- Max 5 files
- ONLY the JSON array
"""

prev_findings = read_pipeline(f"findings-r{r-1}.json") if r > 1 else None
prev_code     = read_pipeline(f"code-r{r-1}.json")     if r > 1 else None

user_msg = f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}\n\n{ISSUE_BODY}"
if prev_findings and prev_code:
    user_msg += (
        f"\n\n---\nPrevious code attempt:\n{json.dumps(prev_code, indent=2)}"
        f"\n\nReviewer findings to fix:\n{json.dumps(prev_findings, indent=2)}"
        f"\n\nFix ALL findings and return the updated files."
    )

print(f"[Coder round {r}] calling {CODER_MODEL}...")
raw = chat(CODER_MODEL, [{"role": "system", "content": SYSTEM},
                          {"role": "user",   "content": user_msg}])

code_changes = extract_json(raw)
if not isinstance(code_changes, list) or not code_changes:
    print("[ERROR] no parseable file changes", file=sys.stderr)
    set_output("has_changes", "false")
    sys.exit(1)

for change in code_changes:
    p = Path(change["file"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(change["content"], encoding="utf-8")
    print(f"  written: {p}")

write_pipeline(f"code-r{r}.json", code_changes)
commit_and_push(f"chore: coder round {r} — issue #{ISSUE_NUMBER}")
set_output("has_changes", "true")

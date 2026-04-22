#!/usr/bin/env python3
"""Job: coder — explore repo, generate or fix code, commit to branch."""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

parser = argparse.ArgumentParser()
parser.add_argument("--round", type=int, required=True)
args = parser.parse_args()
r = args.round

skills = load_skills()

SYSTEM = f"""You are an expert Moodle PHP developer implementing GitHub issues.

You have tools to explore the repository. Context budget is limited — be efficient:
1. Locate the relevant files (max 2 lookups)
2. Read them to understand existing code (max 2 reads)
3. Generate your changes

Return ONLY a JSON array as your final response — no prose, no markdown:
[{{"file": "exact/path/as/found/in/repo", "content": "complete file content"}}]

CRITICAL:
- Use exact file paths as returned by the tools (they may have a prefix like public/)
- Do NOT read more than 3 files total
- ONLY output the JSON array
{skills}"""

prev_findings = read_pipeline(f"findings-r{r-1}.json") if r > 1 else None
prev_code     = read_pipeline(f"code-r{r-1}.json")     if r > 1 else None

user_msg = f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}\n\n{ISSUE_BODY}"
if prev_findings and prev_code:
    user_msg += (
        f"\n\n---\nPrevious code attempt:\n{json.dumps(prev_code, indent=2)}"
        f"\n\nReviewer findings to fix:\n{json.dumps(prev_findings, indent=2)}"
        f"\n\nExplore the repo if needed, then fix ALL findings and return updated files."
    )

repo_context = get_repo_context()
user_msg = f"Repository top-level structure:\n{repo_context}\n\n---\n{user_msg}"

print(f"[Coder round {r}] calling {CODER_MODEL} with file-reading tools...")
raw = tool_loop(CODER_MODEL, SYSTEM, user_msg, CODER_TOOLS, max_turns=15)

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

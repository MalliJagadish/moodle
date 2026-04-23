#!/usr/bin/env python3
"""Job: reviewer — review code against standards, save findings, commit to branch."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

parser = argparse.ArgumentParser()
parser.add_argument("--round", type=int, required=True)
args = parser.parse_args()
r = args.round

code_changes = read_pipeline(f"code-r{r}.json") or []

# Load instructions matching the files being reviewed (Copilot-compatible pattern)
review_files = [change.get("file", "") for change in code_changes]
skills = load_skills(review_files)

SYSTEM = f"""You are a senior Moodle code reviewer.

Review the provided code changes against the issue requirements and enforce all
team standards listed below.

Return ONLY a JSON array of findings — no prose:
[{{"file": "path", "line": 42, "severity": "HIGH|MEDIUM|LOW", "issue": "what is wrong", "suggestion": "how to fix"}}]

Severity guide:
- HIGH   — security issue, data loss risk, broken functionality, standards violation
- MEDIUM — quality issue, missing error handling, suboptimal pattern
- LOW    — style, naming, minor improvement

If the code is correct and meets all standards return: []
{skills}"""

user_msg = (
    f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}\n\n{ISSUE_BODY}\n\n"
    f"---\nCode changes to review:\n{json.dumps(code_changes, indent=2)}"
)

print(f"[Reviewer round {r}] calling {REVIEWER_MODEL}...")
raw = chat(REVIEWER_MODEL, [{"role": "system", "content": SYSTEM},
                              {"role": "user",   "content": user_msg}])

findings = extract_json(raw)
if not isinstance(findings, list):
    findings = []

high = sum(1 for f in findings if f.get("severity") in ("HIGH", "CRITICAL"))
print(f"findings: {len(findings)} ({high} high/critical)")

write_pipeline(f"findings-r{r}.json", findings)
commit_and_push(f"chore: reviewer round {r} findings — issue #{ISSUE_NUMBER}")
set_output("has_findings", "true" if findings else "false")

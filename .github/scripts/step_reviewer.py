#!/usr/bin/env python3
"""Job: reviewer — review code against standards and spec, save findings, commit to branch."""
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

# Load dispositions from coder (round 2 only) to note defended findings
dispositions = read_pipeline("dispositions.json") if r == 2 else None
defend_context = ""
if dispositions:
    defended = [d for d in dispositions if d.get("action") == "defend"]
    if defended:
        defend_context = (
            "\n\nThe coder DEFENDED the following findings (chose not to fix them):\n"
            + json.dumps(defended, indent=2)
            + "\n\nFor defended findings: if the coder's reasoning is valid, do NOT re-raise "
            "the same issue. Only re-raise if the defense is technically incorrect."
        )

SYSTEM = f"""You are a senior Moodle code reviewer.

Review the provided code changes against BOTH:
1. The original issue requirements (spec) — verify the implementation actually solves the issue correctly
2. Code quality and team standards listed below

If the code does not match the spec (e.g. wrong logic, missing requirements, misunderstood the issue),
raise a HIGH severity finding with the issue description explaining the spec mismatch.

Return ONLY a JSON array of findings — no prose:
[{{"file": "path", "line": 42, "severity": "HIGH|MEDIUM|LOW", "issue": "what is wrong", "suggestion": "how to fix"}}]

Severity guide:
- HIGH   — security issue, data loss risk, broken functionality, spec mismatch, standards violation
- MEDIUM — quality issue, missing error handling, suboptimal pattern
- LOW    — style, naming, minor improvement

If the code is correct and meets all standards return: []
{skills}"""

user_msg = (
    f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}\n\n{ISSUE_BODY}\n\n"
    f"---\nCode changes to review:\n{json.dumps(code_changes, indent=2)}"
    f"{defend_context}"
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

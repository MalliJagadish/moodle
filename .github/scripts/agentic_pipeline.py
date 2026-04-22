#!/usr/bin/env python3
"""
Agentic pipeline: Issue opened → Code → Review → Code → Review (max 2 rounds) → PR

Models:
  Coder:    openai/gpt-4.1-mini   (OpenAI)
  Reviewer: mistral-ai/mistral-small-2503  (Mistral)

Auth:
  GITHUB_TOKEN — used for GitHub Models inference (models: read permission)
  GH_PAT       — used for git push + PR creation so downstream workflows trigger
                 (store as repo secret; falls back to GITHUB_TOKEN if not set)
"""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
ENDPOINT       = "https://models.github.ai/inference/chat/completions"
GITHUB_TOKEN   = os.environ["GITHUB_TOKEN"]
GH_PAT         = os.environ.get("GH_PAT") or GITHUB_TOKEN
ISSUE_NUMBER   = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE    = os.environ["ISSUE_TITLE"]
ISSUE_BODY     = os.environ.get("ISSUE_BODY", "").strip()
REPO           = os.environ["GITHUB_REPOSITORY"]   # owner/repo
BRANCH         = f"agent/issue-{ISSUE_NUMBER}"

CODER_MODEL    = "openai/gpt-4.1-mini"
REVIEWER_MODEL = "mistral-ai/mistral-small-2503"
MAX_ROUNDS     = 2

INFERENCE_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}
# Issue comments use GITHUB_TOKEN (has issues: write from workflow permissions)
ISSUE_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ── LLM helper ────────────────────────────────────────────────────────────────
def chat(model: str, messages: list[dict], max_tokens: int = 8000) -> str:
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    r = requests.post(ENDPOINT, headers=INFERENCE_HEADERS, json=payload, timeout=120)
    if not r.ok:
        print(f"[ERROR] {model} → {r.status_code}: {r.text[:500]}", file=sys.stderr)
        r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return content or ""


# ── JSON extraction ────────────────────────────────────────────────────────────
def extract_json(text: str) -> list | dict:
    """Pull first JSON array or object out of model output."""
    # Prefer fenced block
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Raw JSON anywhere in text
    for pattern in (r"(\[[\s\S]*\])", r"(\{[\s\S]*\})"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return []


# ── Shell helpers ─────────────────────────────────────────────────────────────
def run(cmd: str, check: bool = True, env: dict | None = None) -> str:
    print(f"$ {cmd}")
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, check=check, env=merged_env
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.stdout.strip()


def git(cmd: str, **kw) -> str:
    return run(f"git {cmd}", **kw)


# ── GitHub API helpers ────────────────────────────────────────────────────────
def post_issue_comment(body: str):
    owner, repo = REPO.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{ISSUE_NUMBER}/comments"
    r = requests.post(url, headers=ISSUE_HEADERS, json={"body": body})
    if not r.ok:
        print(f"[WARN] Could not post issue comment: {r.status_code} {r.text[:200]}", file=sys.stderr)


# ── Prompts ───────────────────────────────────────────────────────────────────
CODER_SYSTEM = """You are an expert Moodle PHP developer implementing GitHub issues.

Given an issue description, produce the minimal code changes needed.

Return ONLY a JSON array — no prose, no markdown outside the array:
[
  {
    "file": "relative/path/to/file.php",
    "content": "complete file content"
  }
]

Rules:
- Follow Moodle coding standards (PHP 8.1+, Moodle APIs).
- Keep changes minimal and targeted to the issue.
- Create new files or update existing ones as needed.
- Return at most 5 files per round.
- If the issue is unclear, make a reasonable best-effort attempt.
"""

REVIEWER_SYSTEM = """You are a senior Moodle code reviewer.

Review code changes against the stated issue. Look for:
- Correctness (does it actually implement the issue?)
- Moodle standards violations
- Security issues (SQL injection, XSS, capability checks missing)
- Missing error handling

Return ONLY a JSON array — no prose, no markdown outside the array:
[
  {
    "file": "path/to/file.php",
    "line": 42,
    "severity": "HIGH|MEDIUM|LOW",
    "issue": "what is wrong",
    "suggestion": "how to fix it"
  }
]

If code is correct and complete, return an empty array: []
"""


def build_coder_message(prev_findings=None, prev_code=None) -> str:
    parts = [f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}"]
    if ISSUE_BODY:
        parts.append(ISSUE_BODY)
    if prev_code and prev_findings:
        parts.append("\n---\nPrevious code attempt (fix the reviewer findings below):")
        parts.append(json.dumps(prev_code, indent=2))
        parts.append("\nReviewer findings to address:")
        parts.append(json.dumps(prev_findings, indent=2))
        parts.append("\nReturn updated files that fix ALL findings.")
    return "\n\n".join(parts)


def build_reviewer_message(code_changes: list) -> str:
    return (
        f"Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}\n\n"
        f"{ISSUE_BODY}\n\n"
        "---\nCode changes to review:\n"
        + json.dumps(code_changes, indent=2)
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Git identity for commits
    git("config user.email 'github-actions[bot]@users.noreply.github.com'")
    git("config user.name 'github-actions[bot]'")

    # Create branch
    git(f"checkout -b {BRANCH}")

    # Tell the issue author we've started
    post_issue_comment(
        f"🤖 **Agentic pipeline started** for issue #{ISSUE_NUMBER}\n\n"
        f"| | |\n|---|---|\n"
        f"| Branch | `{BRANCH}` |\n"
        f"| Coder | `{CODER_MODEL}` (OpenAI) |\n"
        f"| Reviewer | `{REVIEWER_MODEL}` (Mistral) |\n"
        f"| Max rounds | {MAX_ROUNDS} |\n\n"
        f"I'll open a PR when done."
    )

    findings: list = []
    code_changes: list = []

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n{'='*60}")
        print(f"ROUND {round_num}/{MAX_ROUNDS}")
        print(f"{'='*60}")

        # ── Coder ────────────────────────────────────────────────────────
        print(f"[Round {round_num}] Calling coder ({CODER_MODEL})...")
        coder_raw = chat(
            CODER_MODEL,
            [
                {"role": "system", "content": CODER_SYSTEM},
                {"role": "user",   "content": build_coder_message(
                    findings if round_num > 1 else None,
                    code_changes if round_num > 1 else None,
                )},
            ],
        )
        print(f"Coder response (first 400 chars):\n{coder_raw[:400]}")

        parsed = extract_json(coder_raw)
        if not isinstance(parsed, list) or not parsed:
            print("[WARN] Coder returned no parseable file changes — aborting.")
            post_issue_comment(
                f"⚠️ Round {round_num}: Coder returned no file changes. "
                f"Please refine the issue description and reopen."
            )
            sys.exit(1)

        code_changes = parsed

        # Apply files to working tree
        for change in code_changes:
            fpath = Path(change["file"])
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(change["content"], encoding="utf-8")
            print(f"  Written: {fpath}")

        # ── Reviewer ──────────────────────────────────────────────────────
        print(f"[Round {round_num}] Calling reviewer ({REVIEWER_MODEL})...")
        reviewer_raw = chat(
            REVIEWER_MODEL,
            [
                {"role": "system", "content": REVIEWER_SYSTEM},
                {"role": "user",   "content": build_reviewer_message(code_changes)},
            ],
        )
        print(f"Reviewer response (first 400 chars):\n{reviewer_raw[:400]}")

        parsed_findings = extract_json(reviewer_raw)
        findings = parsed_findings if isinstance(parsed_findings, list) else []

        high_count = sum(1 for f in findings if f.get("severity") in ("HIGH", "CRITICAL"))
        print(f"  Findings: {len(findings)} total, {high_count} high/critical")

        if not findings:
            print(f"[Round {round_num}] ✅ No findings — code approved.")
            break

        if round_num == MAX_ROUNDS:
            print(f"[Round {round_num}] Max rounds reached with {len(findings)} unresolved finding(s).")

    # ── Commit ────────────────────────────────────────────────────────────────
    git("add -A")
    status = run("git status --porcelain", check=False)
    if not status:
        post_issue_comment("ℹ️ No file changes were produced. Nothing to commit.")
        sys.exit(0)

    commit_msg = (
        f"feat: implement issue #{ISSUE_NUMBER} — {ISSUE_TITLE[:70]}\n\n"
        f"AI-generated via GitHub Models agentic pipeline.\n"
        f"Coder: {CODER_MODEL} | Reviewer: {REVIEWER_MODEL}"
    )
    git(f'commit -m "{commit_msg}"')

    # Push using GH_PAT so the PR can trigger status-check workflows
    owner, repo_name = REPO.split("/", 1)
    remote_url = f"https://x-access-token:{GH_PAT}@github.com/{REPO}.git"
    run(f'git push "{remote_url}" "{BRANCH}"')

    # ── Build PR body ─────────────────────────────────────────────────────────
    files_list = "\n".join(f"- `{c['file']}`" for c in code_changes)

    if findings:
        findings_md = "\n".join(
            f"- **[{f.get('severity','?')}]** `{f.get('file','')}:{f.get('line','')}` — "
            f"{f.get('issue','')}  \n  *Suggestion: {f.get('suggestion','')}*"
            for f in findings
        )
        review_section = f"\n### ⚠️ Unresolved findings — human review needed\n{findings_md}"
    else:
        review_section = "\n### ✅ Reviewer approved — no findings."

    pr_body = textwrap.dedent(f"""
        ## 🤖 AI-Generated Implementation

        Closes #{ISSUE_NUMBER}

        ### Models used
        | Role | Model | Vendor |
        |---|---|---|
        | Coder | `{CODER_MODEL}` | OpenAI |
        | Reviewer | `{REVIEWER_MODEL}` | Mistral |

        ### Files changed
        {files_list}
        {review_section}

        ---
        *Auto-generated by the agentic pipeline via GitHub Models.*
    """).strip()

    # Create PR via gh CLI using GH_PAT
    env_override = {"GH_TOKEN": GH_PAT}
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--title", f"feat: #{ISSUE_NUMBER} — {ISSUE_TITLE[:70]}",
            "--body", pr_body,
            "--head", BRANCH,
            "--base", "main",
        ],
        capture_output=True, text=True,
        env={**os.environ, **env_override},
    )

    if result.returncode != 0:
        print(f"[ERROR] gh pr create failed:\n{result.stderr}", file=sys.stderr)
        post_issue_comment(
            f"❌ Pipeline completed but PR creation failed.\n\n"
            f"Branch `{BRANCH}` is ready — please open the PR manually."
        )
        sys.exit(1)

    pr_url = result.stdout.strip()
    print(f"PR created: {pr_url}")

    post_issue_comment(
        f"🎉 **Pipeline complete!**\n\n"
        f"| | |\n|---|---|\n"
        f"| PR | {pr_url} |\n"
        f"| Rounds | {round_num}/{MAX_ROUNDS} |\n"
        f"| Files changed | {len(code_changes)} |\n"
        f"| Final findings | {len(findings)} |\n"
    )


if __name__ == "__main__":
    main()

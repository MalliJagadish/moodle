#!/usr/bin/env python3
"""Job: coder — find relevant files, read them, call model ONCE to generate code."""
import argparse, os, sys, subprocess, re
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

parser = argparse.ArgumentParser()
parser.add_argument("--round", type=int, required=True)
args = parser.parse_args()
r = args.round

skills = load_skills()


# ── Step 1: Extract keywords from issue ───────────────────────────────────────
def extract_keywords(title: str, body: str) -> list[str]:
    """Pull meaningful keywords from issue text."""
    text = f"{title} {body}"
    # Remove markdown, URLs, code fences
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', lambda m: m.group(0).strip('`'), text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[#*>\-|]', ' ', text)
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{3,}', text)
    # Filter out common English words
    stop = {'this','that','with','from','they','have','been','will','when',
            'should','would','could','each','also','like','into','than',
            'only','other','some','such','more','very','just','about',
            'problem','expected','behaviour','behavior','notes','error',
            'field','form','value','values','invalid','valid','clear',
            'show','shown','already','currently','submit','display',
            'message','entry','entries','range','text','input','data',
            'admin','creating','editing','accepts','including','obviously'}
    filtered = []
    seen = set()
    for w in words:
        low = w.lower()
        if low not in stop and low not in seen and len(low) > 3:
            seen.add(low)
            filtered.append(w)
    return filtered[:10]


# ── Step 2: Find relevant files using keywords ──────────────────────────────
def find_relevant_files(keywords: list[str], max_files: int = 5) -> list[str]:
    """Search repo for files matching keywords."""
    found = set()
    # Search by filename
    for kw in keywords[:5]:
        result = subprocess.run(
            f'find . -type f -name "*{kw}*" 2>/dev/null | grep -v ".git" | grep -v __pycache__ | head -5',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Search by file content
    for kw in keywords[:5]:
        result = subprocess.run(
            f'grep -rl "{kw}" --include="*.php" . 2>/dev/null | grep -v ".git" | head -5',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Score files: more keyword matches = more relevant
    scored = []
    for f in found:
        score = sum(1 for kw in keywords if kw.lower() in f.lower())
        # Bonus for being a class file or form file
        if 'classes/' in f: score += 1
        if 'form' in f.lower(): score += 1
        if 'lang/' in f: score += 1
        # Penalty for test files
        if 'test' in f.lower(): score -= 2
        if 'fixture' in f.lower(): score -= 3
        scored.append((score, f))

    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:max_files]]


# ── Step 3: Read files ───────────────────────────────────────────────────────
def read_files(paths: list[str], max_lines: int = 120, max_chars: int = 2500) -> dict[str, str]:
    """Read files with size caps."""
    contents = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        lines = open(p, encoding='utf-8', errors='replace').readlines()
        content = ''.join(lines[:max_lines])
        if len(content) > max_chars:
            content = content[:max_chars] + f'\n... (truncated)'
        contents[p] = content
    return contents


# ── Main ─────────────────────────────────────────────────────────────────────
keywords = extract_keywords(ISSUE_TITLE, ISSUE_BODY)
print(f"[Coder round {r}] keywords: {keywords}")

relevant_files = find_relevant_files(keywords, max_files=4)
print(f"[Coder round {r}] relevant files: {relevant_files}")

file_contents = read_files(relevant_files[:3])
print(f"[Coder round {r}] read {len(file_contents)} files")

# Build context
file_context = ""
for path, content in file_contents.items():
    file_context += f"\n--- {path} ---\n{content}\n"

# Handle round 2 (fix findings)
prev_findings = read_pipeline(f"findings-r{r-1}.json") if r > 1 else None
prev_code     = read_pipeline(f"code-r{r-1}.json")     if r > 1 else None

fix_context = ""
if prev_findings and prev_code:
    fix_context = (
        f"\n\n---\nYour previous code:\n{json.dumps(prev_code, indent=2)}"
        f"\n\nReviewer findings to fix:\n{json.dumps(prev_findings, indent=2)}"
        f"\n\nFix ALL findings and return updated files."
    )

system = f"""You are an expert Moodle PHP developer.
You will be given an issue description and relevant existing source files.
Generate the minimal code changes to implement the fix.

Return ONLY a JSON array — nothing else:
[{{"file": "exact/path/to/file.php", "content": "complete file content"}}]

Rules:
- Use the EXACT file paths from the provided source files
- Follow Moodle coding standards (PHP 8.1+)
- Reuse existing Moodle APIs and patterns from the provided files
- Max 5 files
{skills}"""

user_msg = f"""Issue: {ISSUE_TITLE}

{ISSUE_BODY}

Relevant source files from the repository:
{file_context}
{fix_context}"""

print(f"[Coder round {r}] calling {CODER_MODEL}...")
raw = chat(CODER_MODEL, [
    {"role": "system", "content": system},
    {"role": "user",   "content": user_msg},
])

code_changes = extract_json(raw)
if not isinstance(code_changes, list) or not code_changes:
    print(f"[ERROR] no parseable file changes. Raw response:\n{raw[:500]}", file=sys.stderr)
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

#!/usr/bin/env python3
"""Job: coder — find relevant files, read them, call model ONCE to generate code."""
import argparse, os, sys, subprocess, re, time
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
    text = f"{title} {body}"
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', lambda m: m.group(0).strip('`'), text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[#*>\-|]', ' ', text)

    # Also combine adjacent words to catch terms like "ip restriction" → "iprestriction"
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', text)

    stop = {'the','this','that','with','from','they','have','been','will','when',
            'should','would','could','each','also','like','into','than','any',
            'only','other','some','such','more','very','just','about','not',
            'problem','expected','behaviour','behavior','notes','error','can',
            'field','form','value','values','invalid','valid','clear','for',
            'show','shown','already','currently','submit','display','and',
            'message','entry','entries','range','text','input','data','are',
            'admin','creating','editing','accepts','including','obviously',
            'hello','world','malformed','notation','obviously','including',
            'example','please','need','needs','want','make','does','done'}

    filtered = []
    seen = set()
    for w in words:
        low = w.lower()
        if low not in stop and low not in seen and len(low) > 2:
            seen.add(low)
            filtered.append(low)

    # Generate compound terms (adjacent pairs without space)
    for i in range(len(words) - 1):
        compound = words[i].lower() + words[i+1].lower()
        if compound not in seen and len(compound) > 5:
            seen.add(compound)
            filtered.append(compound)

    return filtered[:15]


# ── Step 2: Find relevant files ──────────────────────────────────────────────
def find_relevant_files(keywords: list[str], max_files: int = 5) -> list[str]:
    found = set()

    # Search by filename (case-insensitive)
    for kw in keywords[:8]:
        result = subprocess.run(
            f'find . -type f -iname "*{kw}*" 2>/dev/null | grep -v ".git" | grep -v __pycache__ | grep -v node_modules | head -5',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Search by file content (case-insensitive)
    for kw in keywords[:8]:
        result = subprocess.run(
            f'grep -rli "{kw}" --include="*.php" . 2>/dev/null | grep -v ".git" | head -5',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Score: more keyword hits in path = more relevant
    scored = []
    for f in found:
        flow = f.lower()
        score = sum(1 for kw in keywords if kw.lower() in flow)
        # Bonus for likely-important files
        if 'classes/' in f: score += 1
        if 'form' in flow: score += 2
        if 'lang/' in f and '/en/' in f: score += 2
        if 'lib.php' in flow: score += 1
        # Penalty for test/fixture/backup/vendor files
        if 'test' in flow: score -= 3
        if 'fixture' in flow: score -= 3
        if 'backup' in flow: score -= 2
        if 'vendor/' in flow: score -= 5
        if 'thirdparty' in flow: score -= 5
        scored.append((score, f))

    scored.sort(key=lambda x: -x[0])
    results = [f for _, f in scored[:max_files]]
    return results


# ── Step 3: Read files with size limit ───────────────────────────────────────
def read_files(paths: list[str], max_lines: int = 120, max_chars: int = 2500) -> dict[str, str]:
    contents = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        lines = open(p, encoding='utf-8', errors='replace').readlines()
        content = ''.join(lines[:max_lines])
        if len(content) > max_chars:
            content = content[:max_chars] + '\n... (truncated)'
        contents[p] = content
    return contents


# ── Step 4: Call model with retry on rate limit ──────────────────────────────
def chat_with_retry(model, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return chat(model, messages)
        except Exception as e:
            if '429' in str(e) and attempt < max_retries - 1:
                wait = 30 * (attempt + 1)
                print(f"[WARN] rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


# ── Main ─────────────────────────────────────────────────────────────────────
keywords = extract_keywords(ISSUE_TITLE, ISSUE_BODY)
print(f"[Coder round {r}] keywords: {keywords}")

relevant_files = find_relevant_files(keywords, max_files=4)
print(f"[Coder round {r}] relevant files: {relevant_files}")

file_contents = read_files(relevant_files[:3])
print(f"[Coder round {r}] read {len(file_contents)} files: {list(file_contents.keys())}")

file_context = ""
for path, content in file_contents.items():
    file_context += f"\n--- {path} ---\n{content}\n"

# Round 2: include previous code + findings
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
raw = chat_with_retry(CODER_MODEL, [
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

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

# skills loaded after file discovery (context-aware)


# ── Step 1: Extract keywords from issue ───────────────────────────────────────
def extract_keywords(title: str, body: str) -> list[str]:
    text = f"{title} {body}"
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[#*>\-|]', ' ', text)

    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', text)

    stop = {'the','this','that','with','from','they','have','been','will','when',
            'should','would','could','each','also','like','into','than','any',
            'only','other','some','such','more','very','just','about','not',
            'problem','expected','behaviour','behavior','notes','error','can',
            'field','form','value','values','invalid','valid','clear','for',
            'show','shown','already','currently','submit','display','and',
            'message','entry','entries','range','text','input','data','are',
            'admin','creating','editing','accepts','including','obviously',
            'hello','world','malformed','notation','including','still',
            'example','please','need','needs','want','make','does','done',
            'file','files','name','names','description','most','clients',
            'content','using','used','use','before','after','output',
            'new','all','may','via','steps','step','reproduce','affected',
            'rendered','written','directly','violation','policy','cleaned',
            'event','events','raw','open','function','likely','page'}

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

    # Also extract backtick-quoted terms from original text (these are specific filenames/functions)
    backtick_terms = re.findall(r'`([^`]+)`', f"{title} {body}")
    for term in backtick_terms:
        parts = re.findall(r'[a-zA-Z_][a-zA-Z0-9_.]{2,}', term)
        for p in parts:
            low = p.lower()
            if low not in seen and low not in stop:
                seen.add(low)
                filtered.insert(0, low)  # prioritize backtick terms

    return filtered[:15]


# ── Step 2: Find relevant files ──────────────────────────────────────────────
def find_relevant_files(keywords: list[str], max_files: int = 5) -> list[str]:
    found = set()

    # Search by filename (case-insensitive, only code files)
    for kw in keywords[:10]:
        result = subprocess.run(
            f'find . -type f \\( -iname "*{kw}*.php" -o -iname "*{kw}*.js" -o -iname "*{kw}*.json" \\) 2>/dev/null '
            f'| grep -v ".git" | grep -v __pycache__ | grep -v node_modules | grep -v vendor | head -8',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Search by file content (case-insensitive, PHP only)
    for kw in keywords[:8]:
        result = subprocess.run(
            f'grep -rli "{kw}" --include="*.php" . 2>/dev/null | grep -v ".git" | grep -v vendor | head -8',
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                found.add(line.strip())

    # Score: more keyword hits in path = more relevant
    scored = []
    for f in found:
        flow = f.lower()
        ext = os.path.splitext(f)[1].lower()

        # Skip non-code files
        if ext in ('.svg', '.png', '.jpg', '.gif', '.ico', '.woff', '.ttf', '.map'):
            continue

        score = sum(1 for kw in keywords if kw.lower() in flow)

        # Bonus for likely-important files
        if ext == '.php': score += 2
        if 'classes/' in f: score += 1
        if 'form' in flow: score += 2
        if 'lang/' in f and '/en/' in f: score += 2
        if 'lib.php' in flow: score += 2
        if 'locallib.php' in flow: score += 1

        # Penalty for test/fixture/backup/vendor files
        if '/test/' in flow or '/tests/' in flow: score -= 4
        if 'fixture' in flow: score -= 4
        if 'backup/' in flow: score -= 2
        if 'vendor/' in flow: score -= 6
        if 'thirdparty' in flow: score -= 6
        if '/yui/' in flow: score -= 3

        scored.append((score, f))

    scored.sort(key=lambda x: -x[0])
    results = [f for _, f in scored[:max_files]]
    return results


# ── Step 3: Read files with size limit ───────────────────────────────────────
def read_files(paths: list[str], max_lines: int = 150, max_chars: int = 4000) -> dict[str, str]:
    contents = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext in ('.svg', '.png', '.jpg', '.gif', '.ico'):
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
            return chat(model, messages, max_tokens=12000)
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

relevant_files = find_relevant_files(keywords, max_files=5)
print(f"[Coder round {r}] relevant files: {relevant_files}")

file_contents = read_files(relevant_files[:4])
print(f"[Coder round {r}] read {len(file_contents)} files: {list(file_contents.keys())}")

file_context = ""
for path, content in file_contents.items():
    file_context += f"\n--- {path} ---\n{content}\n"

# Load instructions matching the discovered files (Copilot-compatible pattern)
skills = load_skills(relevant_files)

# Round 2: include previous code + findings + defend option
prev_findings = read_pipeline(f"findings-r{r-1}.json") if r > 1 else None
prev_code     = read_pipeline(f"code-r{r-1}.json")     if r > 1 else None

fix_context = ""
defend_instructions = ""
if prev_findings and prev_code:
    fix_context = (
        f"\n\n---\nYour previous code:\n{json.dumps(prev_code, indent=2)}"
        f"\n\nReviewer findings to fix:\n{json.dumps(prev_findings, indent=2)}"
    )
    defend_instructions = """

IMPORTANT — You may DEFEND findings you believe are incorrect or unnecessary.
For each reviewer finding, you must decide: fix it OR defend your original code.

Return TWO JSON keys in your response:
{
  "files": [{"file": "path/to/file.php", "content": "complete file content"}],
  "dispositions": [
    {"finding_index": 0, "action": "fix", "reason": "Fixed the null check as suggested"},
    {"finding_index": 1, "action": "defend", "reason": "The existing validation already handles this case via core_user::validate() on line 45"}
  ]
}

Rules for defending:
- Only defend if you are confident your code is correct
- Provide a clear technical reason referencing specific code/logic
- Defended findings will be escalated to human review
- When in doubt, fix rather than defend
"""

if r == 1:
    system = f"""You are an expert Moodle PHP developer.
You will be given an issue description and relevant existing source files.
Generate the minimal code changes to implement the fix.

IMPORTANT: Return ONLY a valid JSON array — no markdown, no explanation, no prose.
The JSON must be parseable. Escape all special characters in strings properly.

Format:
[{{"file": "exact/path/to/file.php", "content": "complete file content with proper escaping"}}]

Rules:
- Use the EXACT file paths from the provided source files (keep the ./ prefix if present)
- If the source file is under ./public/, use the ./public/ prefix in the file path
- Follow Moodle coding standards (PHP 8.1+)
- Reuse existing Moodle APIs and patterns from the provided files
- Keep changes minimal — only modify what's needed for the fix
- Max 3 files
{skills}"""
else:
    system = f"""You are an expert Moodle PHP developer.
You previously generated code that was reviewed. Now you must address each finding.

{defend_instructions}

Rules:
- Use the EXACT file paths from the provided source files (keep the ./ prefix if present)
- If the source file is under ./public/, use the ./public/ prefix in the file path
- Follow Moodle coding standards (PHP 8.1+)
- Reuse existing Moodle APIs and patterns from the provided files
- Keep changes minimal — only modify what's needed for the fix
- Max 3 files
- Return ONLY valid JSON — no markdown, no explanation, no prose
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

print(f"[Coder round {r}] response length: {len(raw)} chars")

# Parse response — Round 2 may return {files, dispositions} or just an array
code_changes = None
dispositions = []

if r > 1:
    parsed = extract_json(raw)
    if isinstance(parsed, dict) and "files" in parsed:
        code_changes = parsed["files"]
        dispositions = parsed.get("dispositions", [])
    elif isinstance(parsed, list):
        code_changes = parsed
    else:
        code_changes = []
else:
    code_changes = extract_json(raw)

if not isinstance(code_changes, list) or not code_changes:
    print(f"[ERROR] no parseable file changes. Raw response (first 800 chars):\n{raw[:800]}", file=sys.stderr)
    print(f"[ERROR] Raw response (last 400 chars):\n{raw[-400:]}", file=sys.stderr)
    set_output("has_changes", "false")
    sys.exit(1)

print(f"[Coder round {r}] parsed {len(code_changes)} file changes")

if dispositions:
    defended = [d for d in dispositions if d.get("action") == "defend"]
    fixed = [d for d in dispositions if d.get("action") == "fix"]
    print(f"[Coder round {r}] dispositions: {len(fixed)} fixed, {len(defended)} defended")
    write_pipeline("dispositions.json", dispositions)

for change in code_changes:
    p = Path(change["file"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(change["content"], encoding="utf-8")
    print(f"  written: {p}")

write_pipeline(f"code-r{r}.json", code_changes)
commit_and_push(f"chore: coder round {r} — issue #{ISSUE_NUMBER}")
set_output("has_changes", "true")

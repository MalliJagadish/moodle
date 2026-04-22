"""Shared utilities for the agentic pipeline step scripts."""
import json, os, re, subprocess, sys
import requests

ENDPOINT       = "https://models.github.ai/inference/chat/completions"
GITHUB_TOKEN   = os.environ["GITHUB_TOKEN"]
GH_PAT         = os.environ.get("GH_PAT") or GITHUB_TOKEN
ISSUE_NUMBER   = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE    = os.environ["ISSUE_TITLE"]
ISSUE_BODY     = os.environ.get("ISSUE_BODY", "").strip()
REPO           = os.environ["GITHUB_REPOSITORY"]
BRANCH         = f"agent/issue-{ISSUE_NUMBER}"

CODER_MODEL    = "openai/gpt-4.1-mini"
REVIEWER_MODEL = "mistral-ai/mistral-small-2503"
PIPELINE_DIR   = ".pipeline"
SKILLS_DIR     = ".github/ai-skills"

# ── Skills loader ─────────────────────────────────────────────────────────────
def load_skills() -> str:
    """Read all .md files from .github/ai-skills/ and return as one block."""
    if not os.path.isdir(SKILLS_DIR):
        return ""
    parts = []
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if fname.endswith((".md", ".txt")):
            path = os.path.join(SKILLS_DIR, fname)
            content = open(path, encoding="utf-8", errors="replace").read().strip()
            if content:
                parts.append(f"### {fname}\n{content}")
    if not parts:
        return ""
    return "\n\n---\n## Team standards & skills\n\n" + "\n\n".join(parts)


# ── File reading tools (used by the coder) ────────────────────────────────────
_ALLOWED_EXTS = {".php", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".xml", ".css"}

def _safe_path(path: str) -> str | None:
    """Return normalised path or None if unsafe."""
    if not path or ".." in path or os.path.isabs(path):
        return None
    norm = os.path.normpath(path)
    if norm.startswith(".."):
        return None
    return norm

def tool_list_directory(directory: str = ".") -> str:
    p = _safe_path(directory)
    if not p:
        return "Error: invalid path"
    if not os.path.isdir(p):
        return f"Error: '{p}' is not a directory"
    result = subprocess.run(
        f'find "{p}" -maxdepth 2 -type f | head -60',
        shell=True, capture_output=True, text=True
    )
    return result.stdout.strip() or "(empty)"

def tool_search_files(query: str, extension: str = ".php") -> str:
    """Grep repo for files containing query."""
    ext = extension if extension.startswith(".") else f".{extension}"
    result = subprocess.run(
        f'grep -rl "{query}" --include="*{ext}" . 2>/dev/null | head -20',
        shell=True, capture_output=True, text=True
    )
    return result.stdout.strip() or "No matches found"

def tool_read_file(path: str, max_lines: int = 250) -> str:
    p = _safe_path(path)
    if not p:
        return "Error: invalid path"
    if not os.path.isfile(p):
        return f"Error: '{p}' not found"
    ext = os.path.splitext(p)[1].lower()
    if ext not in _ALLOWED_EXTS:
        return f"Error: reading {ext} files is not allowed"
    lines = open(p, encoding="utf-8", errors="replace").readlines()
    if len(lines) > max_lines:
        return "".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines truncated)"
    return "".join(lines)

# Schema definitions for the coder's tool-calling
CODER_TOOLS = [
    {
        "name": "list_directory",
        "description": "List files in a directory of the repository (max depth 2).",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative directory path, e.g. 'webservice'"}
            },
            "required": []
        },
        "fn": tool_list_directory,
    },
    {
        "name": "search_files",
        "description": "Search repository files for a keyword or function name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Text to search for"},
                "extension": {"type": "string", "description": "File extension to search (default: .php)"},
            },
            "required": ["query"]
        },
        "fn": tool_search_files,
    },
    {
        "name": "read_file",
        "description": "Read the content of a file from the repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":      {"type": "string", "description": "Relative file path"},
                "max_lines": {"type": "integer", "description": "Max lines to return (default 250)"},
            },
            "required": ["path"]
        },
        "fn": tool_read_file,
    },
]


# ── Repo structure snapshot ───────────────────────────────────────────────────
def get_repo_context() -> str:
    """Return top-2-level directory tree so the model knows the layout immediately."""
    result = subprocess.run(
        'find . -maxdepth 2 -type d | grep -v ".git" | grep -v "__pycache__" | sort | head -80',
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


# ── Tool-calling loop ─────────────────────────────────────────────────────────
def tool_loop(model: str, system: str, user_msg: str,
              tools: list, max_turns: int = 12) -> str:
    """Run a tool-calling loop; returns final text response."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_msg},
    ]
    schemas = [{"type": "function", "function": {
        "name": t["name"],
        "description": t["description"],
        "parameters": t["parameters"],
    }} for t in tools]
    tool_map = {t["name"]: t["fn"] for t in tools}

    for turn in range(max_turns):
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 8000,
            "tools": schemas,
        }
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json=payload, timeout=120,
        )
        if not r.ok:
            print(f"[ERROR] {model} {r.status_code}: {r.text[:400]}", file=sys.stderr)
            r.raise_for_status()

        msg        = r.json()["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []  # Mistral returns null, not omitted

        # Append assistant turn — only include tool_calls key when non-empty
        assistant_entry: dict = {"role": "assistant", "content": msg.get("content")}
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)

        if not tool_calls:
            return msg.get("content") or ""

        # Execute tools and append results
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"  [{turn+1}] tool: {fn_name}({', '.join(f'{k}={repr(v)[:40]}' for k,v in fn_args.items())})")
            fn = tool_map.get(fn_name)
            result = str(fn(**fn_args)) if fn else f"Unknown tool: {fn_name}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result[:5000],  # cap to avoid blowing context
            })

    # Max turns hit — force a final text response without tools so we still get output
    print(f"[WARN] max_turns={max_turns} reached; forcing final response without tools")
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        json={"model": model, "messages": messages, "max_tokens": 8000},
        timeout=120,
    )
    if r.ok:
        return r.json()["choices"][0]["message"].get("content") or ""
    return ""


# ── Simple (no tools) chat ────────────────────────────────────────────────────
def chat(model: str, messages: list, max_tokens: int = 8000) -> str:
    r = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        json={"model": model, "messages": messages, "max_tokens": max_tokens},
        timeout=120,
    )
    if not r.ok:
        print(f"[ERROR] {model} {r.status_code}: {r.text[:400]}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


# ── GitHub API helpers ────────────────────────────────────────────────────────
def github_api(method: str, path: str, token: str | None = None, **kwargs):
    t = token or GITHUB_TOKEN
    return requests.request(
        method, f"https://api.github.com{path}",
        headers={"Authorization": f"Bearer {t}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        **kwargs,
    )

def graphql(query: str, variables: dict, token: str | None = None):
    t = token or GITHUB_TOKEN
    r = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {t}"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def post_issue_comment(body: str):
    owner, repo = REPO.split("/", 1)
    r = github_api("POST", f"/repos/{owner}/{repo}/issues/{ISSUE_NUMBER}/comments",
                   json={"body": body})
    if not r.ok:
        print(f"[WARN] issue comment failed: {r.status_code} {r.text[:200]}", file=sys.stderr)


# ── Shell / git helpers ───────────────────────────────────────────────────────
def run(cmd: str, check: bool = True, env: dict | None = None) -> str:
    print(f"$ {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         check=check, env={**os.environ, **(env or {})})
    if res.stdout: print(res.stdout.rstrip())
    if res.stderr: print(res.stderr.rstrip(), file=sys.stderr)
    return res.stdout.strip()

def git(cmd: str, **kw) -> str:
    return run(f"git {cmd}", **kw)

def git_push():
    token = GH_PAT or GITHUB_TOKEN
    run(f'git push "https://x-access-token:{token}@github.com/{REPO}.git" "{BRANCH}"')

def set_output(name: str, value: str):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"{name}={value}\n")


# ── Pipeline state (persisted on branch in .pipeline/) ───────────────────────
def read_pipeline(filename: str):
    path = os.path.join(PIPELINE_DIR, filename)
    return json.loads(open(path).read()) if os.path.exists(path) else None

def write_pipeline(filename: str, data):
    os.makedirs(PIPELINE_DIR, exist_ok=True)
    open(os.path.join(PIPELINE_DIR, filename), "w").write(json.dumps(data, indent=2))

def commit_and_push(message: str):
    git("add -A")
    if run("git status --porcelain", check=False):
        git(f'commit -m "{message}"')
        git_push()


# ── JSON extractor ────────────────────────────────────────────────────────────
def extract_json(text: str):
    for pat in (r"```(?:json)?\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```",
                r"(\[[\s\S]*\])", r"(\{[\s\S]*\})"):
        m = re.search(pat, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return []

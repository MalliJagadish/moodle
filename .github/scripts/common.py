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

_API_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# ── Skills loader ─────────────────────────────────────────────────────────────
def load_skills() -> str:
    if not os.path.isdir(SKILLS_DIR):
        return ""
    parts = []
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if fname.endswith((".md", ".txt")):
            path = os.path.join(SKILLS_DIR, fname)
            content = open(path, encoding="utf-8", errors="replace").read().strip()
            if content:
                parts.append(f"### {fname}\n{content}")
    return ("\n\n---\n## Team standards & skills\n\n" + "\n\n".join(parts)) if parts else ""


# ── File reading tools ────────────────────────────────────────────────────────
_ALLOWED_EXTS = {".php", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".xml", ".css"}
_FILE_CHAR_CAP = 2500   # hard cap per file read

def _safe_path(path: str) -> str | None:
    if not path or ".." in path or os.path.isabs(path):
        return None
    norm = os.path.normpath(path)
    return None if norm.startswith("..") else norm

def tool_list_directory(directory: str = ".") -> str:
    p = _safe_path(directory)
    if not p:
        return "Error: invalid path"
    if not os.path.isdir(p):
        return f"Error: '{p}' is not a directory"
    result = subprocess.run(
        f'find "{p}" -maxdepth 2 -type f | head -30',
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip() or "(empty)"

def tool_search_files(query: str, extension: str = ".php") -> str:
    ext = extension if extension.startswith(".") else f".{extension}"
    result = subprocess.run(
        f'grep -rl "{query}" --include="*{ext}" . 2>/dev/null | head -15',
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip() or "No matches found"

def tool_find_file(name: str) -> str:
    """Find files by name pattern (e.g. 'token_form.php')."""
    result = subprocess.run(
        f'find . -type f -name "*{name}*" 2>/dev/null | grep -v ".git" | head -15',
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip() or f"No files matching '*{name}*' found"

def _resolve_path(path: str) -> str | None:
    """Try path as-is, then with public/ prefix."""
    p = _safe_path(path)
    if not p:
        return None
    if os.path.exists(p):
        return p
    alt = os.path.normpath(f"public/{path}")
    if os.path.exists(alt):
        return alt
    return None

def tool_read_file(path: str, max_lines: int = 100) -> str:
    resolved = _resolve_path(path)
    if not resolved:
        hint = ""
        alt = _safe_path(f"public/{path}")
        if alt and not os.path.exists(alt):
            hint = f" (also checked public/{path})"
        return f"Error: '{path}' not found{hint}. Use find_file to locate it."
    if os.path.isdir(resolved):
        return f"Error: '{resolved}' is a directory, not a file"
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in _ALLOWED_EXTS:
        return f"Error: reading {ext} files is not allowed"
    actual = f" (resolved to {resolved})" if resolved != path else ""
    lines = open(resolved, encoding="utf-8", errors="replace").readlines()
    content = "".join(lines[:max_lines])
    if len(content) > _FILE_CHAR_CAP:
        content = content[:_FILE_CHAR_CAP] + f"\n... (truncated at {_FILE_CHAR_CAP} chars)"
    elif len(lines) > max_lines:
        content += f"\n... ({len(lines) - max_lines} more lines truncated)"
    return f"[Reading: {resolved}]{actual}\n{content}"

CODER_TOOLS = [
    {
        "name": "find_file",
        "description": "Find files by name pattern. Use this FIRST to locate files before reading them.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "File name or partial name, e.g. 'token_form.php'"}
            },
            "required": ["name"]
        },
        "fn": tool_find_file,
    },
    {
        "name": "read_file",
        "description": "Read a file (max 100 lines / 2500 chars). Auto-resolves public/ prefix. Read only files you need.",
        "parameters": {
            "type": "object",
            "properties": {
                "path":      {"type": "string", "description": "Relative file path (public/ prefix auto-resolved)"},
                "max_lines": {"type": "integer", "description": "Max lines (default 100, max 100)"},
            },
            "required": ["path"]
        },
        "fn": tool_read_file,
    },
    {
        "name": "search_files",
        "description": "Grep file contents for a keyword (max 15 results). For finding files by name, use find_file instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":     {"type": "string", "description": "Text to search for inside files"},
                "extension": {"type": "string", "description": "File extension (default .php)"},
            },
            "required": ["query"]
        },
        "fn": tool_search_files,
    },
    {
        "name": "list_directory",
        "description": "List files in a directory (max depth 2, max 30 results).",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative path, e.g. 'public/webservice'"}
            },
            "required": []
        },
        "fn": tool_list_directory,
    },
]


# ── Repo structure snapshot ──────────────────────────────────────────────────
def get_repo_context() -> str:
    result = subprocess.run(
        'find . -maxdepth 1 -type d | grep -v "^\\./$" | grep -v ".git" | sort | head -40',
        shell=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


# ── Context-budgeted tool-calling loop ────────────────────────────────────────
_CTX_BUDGET = 25000   # max total chars of tool results before forcing final output
_RESULT_CAP = 2500    # max chars per individual tool result

def _force_final(model: str, messages: list) -> str:
    """Make one more call WITHOUT tools to force a text response."""
    print("[INFO] forcing final response without tools")
    messages.append({"role": "user",
                     "content": "You have read enough. Now produce your FINAL JSON response."})
    r = requests.post(ENDPOINT, headers=_API_HEADERS,
                      json={"model": model, "messages": messages, "max_tokens": 8000},
                      timeout=120)
    return r.json()["choices"][0]["message"].get("content", "") if r.ok else ""


def tool_loop(model: str, system: str, user_msg: str,
              tools: list, max_turns: int = 15) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_msg},
    ]
    schemas = [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["parameters"],
    }} for t in tools]
    tool_map = {t["name"]: t["fn"] for t in tools}
    ctx_used = 0

    for turn in range(max_turns):
        # Budget exceeded — stop reading, force code generation
        if ctx_used >= _CTX_BUDGET:
            print(f"[INFO] context budget reached ({ctx_used}/{_CTX_BUDGET} chars)")
            return _force_final(model, messages)

        r = requests.post(ENDPOINT, headers=_API_HEADERS,
                          json={"model": model, "messages": messages,
                                "max_tokens": 8000, "tools": schemas},
                          timeout=120)
        if not r.ok:
            print(f"[ERROR] {model} {r.status_code}: {r.text[:400]}", file=sys.stderr)
            r.raise_for_status()

        msg        = r.json()["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        assistant_entry: dict = {"role": "assistant", "content": msg.get("content")}
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)

        if not tool_calls:
            return msg.get("content") or ""

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"  [{turn+1}] tool: {fn_name}({', '.join(f'{k}={repr(v)[:40]}' for k,v in fn_args.items())})")
            fn = tool_map.get(fn_name)
            result = str(fn(**fn_args)) if fn else f"Unknown tool: {fn_name}"
            result = result[:_RESULT_CAP]
            ctx_used += len(result)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    return _force_final(model, messages)


# ── Simple (no tools) chat ───────────────────────────────────────────────────
def chat(model: str, messages: list, max_tokens: int = 8000) -> str:
    r = requests.post(ENDPOINT, headers=_API_HEADERS,
                      json={"model": model, "messages": messages, "max_tokens": max_tokens},
                      timeout=120)
    if not r.ok:
        print(f"[ERROR] {model} {r.status_code}: {r.text[:400]}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


# ── GitHub API helpers ───────────────────────────────────────────────────────
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
    r = requests.post("https://api.github.com/graphql",
                      headers={"Authorization": f"Bearer {t}"},
                      json={"query": query, "variables": variables}, timeout=30)
    r.raise_for_status()
    return r.json()

def post_issue_comment(body: str):
    owner, repo = REPO.split("/", 1)
    r = github_api("POST", f"/repos/{owner}/{repo}/issues/{ISSUE_NUMBER}/comments",
                   json={"body": body})
    if not r.ok:
        print(f"[WARN] issue comment failed: {r.status_code} {r.text[:200]}", file=sys.stderr)


# ── Shell / git helpers ──────────────────────────────────────────────────────
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
    run(f'git push "https://x-access-token:{GH_PAT or GITHUB_TOKEN}@github.com/{REPO}.git" "{BRANCH}"')

def set_output(name: str, value: str):
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"{name}={value}\n")


# ── Pipeline state ───────────────────────────────────────────────────────────
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


# ── JSON extractor ───────────────────────────────────────────────────────────
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

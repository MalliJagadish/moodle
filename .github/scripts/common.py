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


def chat(model: str, messages: list, max_tokens: int = 8000) -> str:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    r = requests.post(ENDPOINT, headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                                          "Content-Type": "application/json",
                                          "X-GitHub-Api-Version": "2022-11-28"},
                      json={"model": model, "messages": messages, "max_tokens": max_tokens},
                      timeout=120)
    if not r.ok:
        print(f"[ERROR] {model} {r.status_code}: {r.text[:400]}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def github_api(method: str, path: str, token: str | None = None, **kwargs):
    t = token or GITHUB_TOKEN
    headers = {
        "Authorization": f"Bearer {t}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return requests.request(method, f"https://api.github.com{path}",
                            headers=headers, **kwargs)


def graphql(query: str, variables: dict, token: str | None = None):
    t = token or GITHUB_TOKEN
    r = requests.post("https://api.github.com/graphql",
                      headers={"Authorization": f"Bearer {t}"},
                      json={"query": query, "variables": variables},
                      timeout=30)
    r.raise_for_status()
    return r.json()


def post_issue_comment(body: str):
    owner, repo = REPO.split("/", 1)
    r = github_api("POST", f"/repos/{owner}/{repo}/issues/{ISSUE_NUMBER}/comments",
                   json={"body": body})
    if not r.ok:
        print(f"[WARN] issue comment failed: {r.status_code} {r.text[:200]}", file=sys.stderr)


def run(cmd: str, check: bool = True, env: dict | None = None) -> str:
    print(f"$ {cmd}")
    merged = {**os.environ, **(env or {})}
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         check=check, env=merged)
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

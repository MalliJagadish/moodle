#!/usr/bin/env python3
"""Job: prepare — create branch, post start comment."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

git("config user.email 'github-actions[bot]@users.noreply.github.com'")
git("config user.name 'github-actions[bot]'")
git(f"checkout -b {BRANCH}")
git_push()

owner, repo_name = REPO.split("/", 1)
actions_url = f"https://github.com/{REPO}/actions"

post_issue_comment(
    f"🤖 **Agentic pipeline started** for issue #{ISSUE_NUMBER}\n\n"
    f"| | |\n|---|---|\n"
    f"| Branch | `{BRANCH}` |\n"
    f"| Coder | `{CODER_MODEL}` (OpenAI) |\n"
    f"| Reviewer | `{REVIEWER_MODEL}` (Mistral) |\n\n"
    f"Follow progress: [Actions]({actions_url})"
)

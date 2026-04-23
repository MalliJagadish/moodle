# AI Agentic Pipeline — POC

> ⚠️ **Prototype**
> This pipeline is an early-stage proof of concept. It is **not production-ready**.

---

### Table of Contents

- [What Is This?](#what-is-this)
- [How It Works](#how-it-works)
  - [Pipeline Flow](#pipeline-flow)
  - [Agent Roles & Models](#agent-roles--models)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
  - [AI Skills / Instructions](#ai-skills--instructions)
- [How to Trigger](#how-to-trigger)
- [Limitations & Known Issues](#limitations--known-issues)
- [Future Plans: Production-Grade Pipeline](#future-plans-production-grade-pipeline)

---

### What Is This?

A **GitHub Actions-based multi-agent pipeline** that automatically implements bug fixes or small features from GitHub Issues using AI agents.

When an issue is opened, the pipeline:
1. Creates a dedicated branch
2. Uses a **Coder agent** (GPT-4.1-mini) to analyse the issue, find relevant source files, and generate code changes
3. Uses a **Reviewer agent** (Mistral Small) to review the output against the spec and Moodle coding standards
4. Optionally runs a second round of fix → re-review if issues are found
5. Opens a **Pull Request** with all agent findings posted as inline review comments

A human reviewer is the final step — the pipeline hands off a ready-to-review PR.

---

### How It Works

#### Pipeline Flow

```
        GitHub Issue: opened / reopened
                        │
              ┌─────────▼─────────┐
              │   1. Prepare      │
              │  Create branch    │
              │  Notify issue     │
              └─────────┬─────────┘
                        │
              ┌─────────▼──────────────────┐
              │   2. Coder — Round 1        │  GPT-4.1-mini
              │  Extract keywords           │
              │  Find + read relevant files │
              │  Generate code changes      │
              │  Output: code-r1.json       │
              └─────────┬──────────────────┘
                        │  has_changes = true
              ┌─────────▼──────────────────┐
              │   3. Reviewer — Round 1     │  Mistral Small 2503
              │  Review vs spec + standards │
              │  Severity: HIGH/MEDIUM/LOW  │
              │  Output: findings-r1.json   │
              └────┬───────────────────┬────┘
                   │ has_findings=true  │ has_findings=false
                   ▼                   │ (skip to Create PR)
      ┌────────────────────────┐       │
      │  4. Coder — Round 2    │       │   GPT-4.1-mini
      │  Fix OR defend each    │       │   (conditional)
      │  finding               │       │
      │  Output: code-r2.json  │       │
      │  + dispositions.json   │       │
      └────────────┬───────────┘       │
                   │                   │
      ┌────────────▼───────────┐       │
      │  5. Reviewer — Round 2 │       │   Mistral Small 2503
      │  Re-review with        │       │   (conditional)
      │  disposition context   │       │
      │  Output: findings-r2   │       │
      └────────────┬───────────┘       │
                   └─────────┬─────────┘
                             │
              ┌──────────────▼─────────────┐
              │   6. Create PR              │
              │  Open Pull Request          │
              │  Post inline comments       │
              └──────────────┬─────────────┘
                             │
              ┌──────────────▼─────────────┐
              │   Human Review              │
              │  Approve / Request changes  │
              └─────────────────────────────┘
```

**Key characteristics:**
- **Iterative fix loop** — Reviewer findings trigger a second coder round (max 2 rounds)
- **Fix or Defend** — In round 2 the coder can either fix a finding or defend the original code with a technical reason; defended findings are escalated to human review
- **Skill-aware code generation** — Each job loads `.github/instructions/` files matching the relevant file types, giving agents Moodle-specific coding standards automatically
- **Shared state via git** — Each job commits its JSON output to the branch; the next job checks it out, so no external storage is needed

---

#### Agent Roles & Models

| Job | Agent | Model | Responsibility |
|-----|-------|-------|----------------|
| 2, 4 | Coder | `openai/gpt-4.1-mini` (GitHub Models) | Find relevant files, generate / fix PHP code |
| 3, 5 | Reviewer | `mistral-ai/mistral-small-2503` (GitHub Models) | Review code vs spec and Moodle standards |

---

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | GitHub Actions (`.github/workflows/agentic-pipeline.yml`) |
| Agent scripts | Python 3.12 |
| LLM endpoint | GitHub Models API (`https://models.github.ai/inference/`) |
| Coder model | `openai/gpt-4.1-mini` |
| Reviewer model | `mistral-ai/mistral-small-2503` |
| Auth | `GITHUB_TOKEN` (Actions) + `GH_PAT` (push / PR) |
| Runtime state | JSON files committed to the feature branch (`.pipeline/`) |
| AI skills | `.github/instructions/*.instructions.md` (Copilot-compatible) |

---

### Repository Structure

Only the files **added for this POC** are shown below — all other files are standard Moodle source.

```
.github/
├── workflows/
│   └── agentic-pipeline.yml          ← pipeline orchestration (6 jobs)
│
├── scripts/                          ← Python agent step scripts
│   ├── common.py                     ← shared LLM gateway, GitHub API helpers,
│   │                                    pipeline state (read/write JSON), coder tools
│   ├── step_prepare.py               ← job 1: create branch, post start comment
│   ├── step_coder.py                 ← job 2 + 4: keyword extraction, file search,
│   │                                    code generation (GPT-4.1-mini)
│   ├── step_reviewer.py              ← job 3 + 5: code review (Mistral Small)
│   └── step_create_pr.py             ← job 6: open PR, post inline comments
│
├── instructions/                     ← Copilot-compatible AI skill files (primary)
│   │                                    Loaded per-job based on relevant file paths.
│   │                                    Each file has applyTo: glob in frontmatter.
│   ├── general.instructions.md       ← global Moodle coding standards (no glob = always loaded)
│   ├── forms.instructions.md         ← rules for */form*.php files
│   ├── controllers.instructions.md   ← rules for */controller*.php files
│   ├── database.instructions.md      ← rules for */db/*.php and install.xml files
│   └── services.instructions.md      ← rules for */externallib.php and web services
│
└── ai-skills/                        ← legacy skill files (fallback if instructions/ absent)
    ├── moodle-coding-standards.md    ← general PHP + Moodle standards
    ├── controllers.md                ← controller patterns
    ├── database.md                   ← database API patterns
    ├── forms.md                      ← moodleform patterns
    └── services.md                   ← external service patterns

.pipeline/                            ← runtime state (committed to branch per job)
    ├── code-r1.json                  ← file changes generated by Coder round 1
    ├── findings-r1.json              ← review findings from Reviewer round 1
    ├── code-r2.json                  ← file changes generated by Coder round 2
    ├── findings-r2.json              ← review findings from Reviewer round 2
    └── dispositions.json             ← fix / defend decisions (round 2 only)
```

---

#### AI Skills / Instructions

The `.github/instructions/` files teach the AI agents Moodle-specific conventions. They follow the [Copilot custom instructions](https://docs.github.com/en/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot) format:

```markdown
---
applyTo: "public/mod/*/form*.php, public/lib/form*.php"
---

## Moodle Forms
- Always extend `moodleform`
- Use `$mform->addElement()` — never raw HTML
- ...
```

The `load_skills()` function in `common.py` reads these files and injects the matching ones into each agent's system prompt automatically, so the coder and reviewer always have context relevant to the files they are working on.

Files without an `applyTo` glob (like `general.instructions.md`) are always loaded regardless of which files are being modified.

---

### How to Trigger

1. Open a GitHub Issue in this repository describing the bug or feature
2. The pipeline starts automatically within seconds
3. Watch job progress in the **Actions** tab
4. A Pull Request will be opened on the `agent/issue-{N}` branch when complete
5. Review the PR — all agent findings appear as inline comments

No manual setup is needed beyond the repository secrets:

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Automatically provided by Actions — reads issues, posts comments |
| `GH_PAT` | A Personal Access Token with `repo` scope — needed to push the branch and open the PR |

---

### Limitations & Known Issues

> This is an early-stage prototype. Please be aware of the following:

- **Max 2 rounds** — The fix/review loop runs at most 2 rounds before proceeding to PR creation regardless of remaining findings
- **PHP only** — The coder currently searches and generates `.php` files only; JS/TS changes are not handled
- **No test execution** — Agents generate or suggest fixes but do not run PHPUnit or Behat tests
- **Small file window** — Each file is read up to 100 lines; large files are truncated which may reduce fix accuracy
- **Single issue at a time** — Concurrent pipeline runs for different issues may conflict on the same branch namespace
- **No retry on failure** — If an agent job fails (e.g. API error), the workflow does not retry automatically

---

### Future Plans: Production-Grade Pipeline

> This section describes the **target production architecture** — what the pipeline would look like if taken beyond POC. All approaches below have been verified as technically feasible with GitHub Actions and publicly available tooling.

---

#### Vision

Move from a manually triggered, single-repository toy to a fully autonomous pipeline where issues raised in **any external tool** (Sentry, Elastic APM, Jira, Linear, PagerDuty, or any webhook source) flow through a structured agent chain that plans, codes, tests, scans, reviews, and opens a draft PR — all without human involvement until the final review gate.

---

#### Full Production Pipeline Flow

```
  External Source                GitHub Actions
  ─────────────                  ──────────────────────────────────────────────────
                                                                                    
  Sentry alert  ──┐              ┌──────────────────────────────────────────────┐  
  Elastic log   ──┤  webhook /   │  1. Triage Agent                             │  
  Jira ticket   ──┤  repository_ │     Classify severity, deduplicate,          │  
  Linear issue  ──┤  dispatch    │     enrich with stack trace / log context     │  
  GitHub Issue  ──┘              │     Output: triage.json                       │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │ actionable = true           
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  2. Planning Agent                            │  
                                 │     Read codebase (tool_loop, no file limit)  │  
                                 │     Design implementation plan                │  
                                 │     Identify files, tests, migration needs    │  
                                 │     Output: plan.json                         │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  3. Coder Agent                               │  
                                 │     Follow plan, generate code + unit tests   │  
                                 │     PHP, JS/TS, DB migrations                 │  
                                 │     Output: code.json                         │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  4a. Test Runner (PHPUnit + Behat)            │  
                                 │  4b. Security Scanner (Semgrep / CodeQL)      │  
                                 │      ← run in parallel →                      │  
                                 │  Output: test-results.json, sarif.json        │  
                                 └──────────┬──────────────────┬─────────────────┘  
                                            │ failures exist   │ all pass            
                                 ┌──────────▼──────────┐       │                    
                                 │  5. Fix Agent        │       │                    
                                 │  (up to 2 retries)   │       │                    
                                 │  Re-runs 4a + 4b     │       │                    
                                 └──────────┬───────────┘       │                    
                                            └─────────┬─────────┘                   
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  6. Review Round 1                            │  
                                 │     Code quality + spec compliance            │  
                                 │     Informed by test + security results       │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │ findings                    
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  7. Coder Fix Round (Fix or Defend)           │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  8. Review Round 2 (+ optional Round 3)       │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  9. Open Draft PR                             │  
                                 │     Inline comments: resolved / unresolved    │  
                                 │     Test summary, security findings attached  │  
                                 │     Notify via Slack / Teams                  │  
                                 └────────────────────┬─────────────────────────┘  
                                                      │                             
                                 ┌────────────────────▼─────────────────────────┐  
                                 │  Human Review                                 │  
                                 │  Approve / Request changes / Close            │  
                                 └──────────────────────────────────────────────┘  
```

---

#### 1. External Issue Manager Integration

Any alerting or project management tool can feed into the pipeline via **GitHub's `repository_dispatch` API** — no polling required.

| Source | Integration Method |
|--------|-------------------|
| Sentry | Sentry Webhook → GitHub `repository_dispatch` (event type: `sentry-alert`) |
| Elastic APM | Elastic Watcher alert → HTTP webhook → `repository_dispatch` |
| Jira | Jira Automation rule → webhook → `repository_dispatch` |
| Linear | Linear webhook → `repository_dispatch` |
| PagerDuty | PagerDuty webhook → `repository_dispatch` |
| GitHub Issue | `issues: [opened, reopened]` trigger (already implemented) |

**Example `repository_dispatch` payload from Sentry:**

```json
{
  "event_type": "sentry-alert",
  "client_payload": {
    "issue_url": "https://sentry.io/issues/12345/",
    "title": "TypeError: Cannot read property 'id' of undefined",
    "stack_trace": "...",
    "affected_file": "mod/assign/submission/file/lib.php",
    "severity": "HIGH"
  }
}
```

The **Triage Agent** (Job 1) reads `client_payload` from `github.event.client_payload` and decides whether the issue is actionable, a duplicate, or out of scope before any code generation begins.

---

#### 2. Planning Agent

The POC coder jumps straight from issue text to code. Production needs a **Planning Agent** that reads the codebase first and produces a structured implementation plan.

- Uses `tool_loop()` (already scaffolded in `common.py`) with no hard file limit
- Tools: `find_file`, `read_file`, `search_files`, `list_directory`, `grep_codebase`
- Outputs `plan.json`:
  ```json
  {
    "summary": "Add missing null check before accessing submission->id",
    "files_to_modify": ["mod/assign/submission/file/lib.php"],
    "files_to_create": [],
    "db_migration_needed": false,
    "new_tests": ["mod/assign/tests/submission_file_test.php"],
    "risks": ["Affects all submission types — regression risk in assign module"]
  }
  ```
- Coder (Job 3) follows `plan.json` instead of deriving its own approach from scratch

---

#### 3. Real Test Execution

The POC generates test code but never runs it. Production runs tests inside GitHub Actions and feeds results back to the agents.

**PHPUnit:**
```yaml
- name: Run PHPUnit
  run: |
    cd /var/www/html
    php admin/tool/phpunit/cli/init.php
    vendor/bin/phpunit --testsuite mod_assign \
      --log-junit .pipeline/phpunit-results.xml
```

**Behat (integration):**
```yaml
- name: Run Behat
  run: |
    php admin/tool/behat/cli/init.php
    vendor/bin/behat --tags=@mod_assign \
      --format=json --out=.pipeline/behat-results.json
```

Results are committed to `.pipeline/` and passed to the Fix Agent and Reviewer so they have **ground-truth evidence** of failures, not just code analysis.

---

#### 4. Security Scanning

Three complementary SAST tools run in parallel with tests, all outputting SARIF that GitHub renders as inline PR code annotations:

| Tool | What It Catches | GitHub Integration |
|------|-----------------|--------------------|
| **Semgrep** | PHP injection, XSS, insecure function calls, Moodle-specific rules | `github/codeql-action/upload-sarif` |
| **CodeQL** | Deep data-flow analysis, taint tracking | Native GitHub Advanced Security |
| **Snyk** | Composer dependency CVEs | `snyk/actions/php` |

```yaml
- uses: returntocorp/semgrep-action@v1
  with:
    config: >-
      p/php
      p/owasp-top-ten
    sarif_file: .pipeline/semgrep.sarif

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: .pipeline/semgrep.sarif
```

The SARIF findings are also parsed into `.pipeline/security.json` and injected into the Reviewer's system prompt so review comments reference actual security violations by file and line.

---

#### 5. Multi-Round Review (up to 3 rounds)

The POC is capped at 2 rounds because GitHub Actions has no dynamic loops — each round is a separate job defined statically in YAML.

**Production approach:** Add a third static round, and have the final reviewer apply a **pass/escalate** gate:

```
Round 1 → Round 2 → Round 3 (if HIGH severity remains) → Escalate to human
```

Each review round has full context:
- Code diff from the current round
- Test results (`phpunit-results.xml`, `behat-results.json`)
- Security findings (`security.json`)
- Dispositions from previous rounds (fix / defend decisions)

A finding that is defended twice (Round 1 → Round 2 → Round 3 still present) is automatically marked `ESCALATED` and appears in the PR as an unresolved inline comment requiring human sign-off.

---

#### 6. Draft PR with Inline Comments

The POC already opens a PR with inline comments. Production extends this:

- PR is opened as **Draft** — signals it is not ready to merge until human approves
- **Resolved comments** — findings the coder fixed; shown as resolved threads
- **Unresolved comments** — defended or escalated findings; shown as open threads with the coder's defense reasoning attached
- **PR description** includes:
  - Test execution summary (passed / failed / skipped counts)
  - Security scan summary (HIGH/MEDIUM/LOW finding counts with links)
  - Triage context (original Sentry/Jira source, severity, affected users)
  - Agent confidence score

---

#### 7. Production-Readiness Checklist

Beyond the pipeline logic, these elements are required before going to production:

| Area | What to Add |
|------|-------------|
| **Observability** | Structured JSON logs from each agent script, shipped to Elastic/Datadog. Track token usage, latency, pass/fail per round per issue. |
| **Cost controls** | Hard token budget per pipeline run. Abort and notify if exceeded. Use cheaper models (GPT-4.1-nano, Mistral Small) for triage/planning; reserve GPT-4.1 for coder rounds only. |
| **Idempotency** | Check if a branch `agent/issue-{N}` already exists before creating. Re-use it if the issue is re-opened. Deduplicate Sentry alerts by fingerprint before triggering. |
| **Retry on failure** | Wrap each agent job with a retry step (`max-retries: 2`) for transient API errors. Commit partial state so retries don't repeat completed work. |
| **Human escalation path** | If the pipeline exits with unresolved HIGH findings after all rounds, auto-assign the PR to a lead reviewer and post a Slack/Teams alert. |
| **Notifications** | Post pipeline start/end/failure to a dedicated Slack or Teams channel via webhook. Include issue title, PR link, and a short agent summary. |
| **Secrets management** | Store LLM API keys in GitHub Secrets (or Azure Key Vault for enterprise). Rotate `GH_PAT` regularly. Never log secrets in agent output. |
| **Branch hygiene** | Delete `agent/issue-{N}` branches automatically if the PR is closed without merging. Enforce naming convention via branch protection rules. |
| **Rollback** | Tag the commit before applying agent changes. If PHPUnit regression rate exceeds threshold, auto-close the PR and post a failure summary. |
| **Concurrency** | Use `concurrency: group: issue-${{ github.event.issue.number }}` in the workflow to prevent two pipeline runs for the same issue from racing. |
| **Scope guardrails** | Triage agent should reject issues that touch >N files or require schema changes beyond a configurable complexity threshold — route those to human planning first. |

---

#### 8. Alternative Trigger Approach: Copilot SWE Agent + GitHub Actions

An alternative architecture uses GitHub's **Copilot coding agent** (or Claude via GitHub Agentic Workflows, currently in technical preview) as the primary coder, with GitHub Actions handling review and iteration:

```
Issue assigned to copilot-swe-agent[bot] (via REST API)
        │
        ▼
Copilot opens draft PR with code + unit tests
        │
        ▼
GitHub Actions: PR opened trigger
  → Review Agent (Mistral / Claude)
  → Test Runner (PHPUnit)
  → Security Scanner (Semgrep)
        │  findings / failures
        ▼
Re-assign to copilot-swe-agent[bot] with review comments
        │
        ▼
Copilot pushes fixes → Actions re-run
        │  (repeat up to 3 times)
        ▼
Human review gate
```

**REST API assignment** (requires `repo` scope PAT and Copilot Enterprise/Business license):

```bash
gh api repos/{owner}/{repo}/issues/{number}/assignees \
  -X POST \
  -f assignees[]="copilot-swe-agent[bot]"

# Or with agent_assignment for custom instructions:
gh api repos/{owner}/{repo}/issues/{number} \
  -X PATCH \
  --field 'agent_assignment[target_repo]={owner}/{repo}' \
  --field 'agent_assignment[base_branch]=main' \
  --field 'agent_assignment[custom_instructions]=Follow Moodle coding standards...'
```

This approach delegates the hard coder work to a battle-tested agent and uses the Actions pipeline purely for quality gates — a good split of responsibilities.

---

#### Summary: POC → Production Delta

| Capability | POC | Production |
|------------|-----|-----------|
| Trigger | GitHub Issue only | Any webhook source via `repository_dispatch` |
| Planning | None (coder improvises) | Dedicated Planning Agent with full codebase read |
| Coder scope | PHP only, 4 files max | PHP + JS/TS, unlimited files via `tool_loop` |
| Tests | Generated but not run | PHPUnit + Behat executed, results fed back |
| Security | None | Semgrep + CodeQL + Snyk (SARIF inline annotations) |
| Review rounds | Max 2 | Max 3, with escalation gate |
| PR type | Regular PR | Draft PR with resolved/unresolved inline threads |
| Notifications | None | Slack / Teams on start, finish, failure, escalation |
| Observability | None | Structured logs, token/cost tracking |
| Concurrency | Conflicts possible | `concurrency:` group per issue number |
| Retry | None | 2 retries per job on transient API failure |
| Rollback | None | Auto-close PR if regression threshold exceeded |

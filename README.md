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
- [🚀 Future Plans: Production-Grade Pipeline](#-future-plans-production-grade-pipeline)

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

## 🚀 Future Plans: Production-Grade Pipeline

![Roadmap](https://img.shields.io/badge/Status-Roadmap-6f42c1?style=for-the-badge)
![Feasibility](https://img.shields.io/badge/Feasibility-Verified-2ea44f?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-GitHub_Actions-24292f?style=for-the-badge&logo=github-actions&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-GPT--4.1_%7C_Claude_%7C_Mistral-0078d4?style=for-the-badge)

---

### 🌐 Vision

> [!NOTE]
> Today the pipeline reacts to a **GitHub Issue** and handles small bug fixes.
> The production goal is a **fully autonomous agent chain** where issues raised in *any* external system — Sentry, Elastic APM, Jira, Linear, PagerDuty — automatically flow through planning → coding → testing → security scanning → multi-round review, and land as a **draft PR ready for human sign-off**.
> No human involvement until the final review gate.

---

### 🏗️ Production Pipeline Architecture

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     PRODUCTION AGENTIC PIPELINE                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  EXTERNAL SOURCES          GITHUB ACTIONS JOBS                              ║
║  ─────────────────         ────────────────────────────────────────────     ║
║                                                                              ║
║  🔴 Sentry Alert  ──┐      ┌─────────────────────────────────────────┐     ║
║  📊 Elastic APM   ──┤ repo │  1. 🔍 TRIAGE AGENT                     │     ║
║  📋 Jira Ticket   ──┤ disp │     Classify · Deduplicate · Enrich     │     ║
║  📌 Linear Issue  ──┤ atch │     Output → triage.json                │     ║
║  🔔 PagerDuty     ──┤      └─────────────────┬───────────────────────┘     ║
║  📝 GitHub Issue  ──┘                        │ actionable = true            ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  2. 🧠 PLANNING AGENT                   │     ║
║                            │     Read full codebase (tool_loop)      │     ║
║                            │     Design implementation plan          │     ║
║                            │     Output → plan.json                  │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  3. 💻 CODER AGENT                      │     ║
║                            │     Follow plan · PHP + JS/TS           │     ║
║                            │     Generate code + unit tests          │     ║
║                            │     Output → code.json                  │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  4a. 🧪 TEST RUNNER    4b. 🔒 SECURITY  │     ║
║                            │      PHPUnit + Behat       Semgrep      │     ║
║                            │      ← run in parallel →   CodeQL       │     ║
║                            │      test-results.json     Snyk         │     ║
║                            │                         sarif.json      │     ║
║                            └──────────┬──────────────────┬───────────┘     ║
║                                       │ failures         │ all pass         ║
║                            ┌──────────▼──────────┐       │                 ║
║                            │  5. 🔧 FIX AGENT     │       │                 ║
║                            │     Up to 2 retries  │       │                 ║
║                            │     Re-run 4a + 4b   │       │                 ║
║                            └──────────┬───────────┘       │                 ║
║                                       └──────────┬────────┘                 ║
║                                                  │                          ║
║                            ┌─────────────────────▼───────────────────┐     ║
║                            │  6. 🔎 REVIEW ROUND 1                   │     ║
║                            │     Code quality · Spec compliance      │     ║
║                            │     Aware of test + security results    │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │ findings                     ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  7. 💻 CODER — Fix or Defend             │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  8. 🔎 REVIEW ROUND 2 (+ Round 3)       │     ║
║                            │     Escalate unresolved HIGH findings   │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  9. 📬 DRAFT PR                         │     ║
║                            │     Inline comments: resolved/open      │     ║
║                            │     Test + security summary attached    │     ║
║                            │     Slack / Teams notification sent     │     ║
║                            └─────────────────┬───────────────────────┘     ║
║                                              │                              ║
║                            ┌─────────────────▼───────────────────────┐     ║
║                            │  👤 HUMAN REVIEW GATE                   │     ║
║                            │     Approve · Request changes · Close   │     ║
║                            └─────────────────────────────────────────┘     ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

### 🔌 1. External Issue Manager Integration

> [!TIP]
> Any alerting or project management tool can feed into the pipeline via GitHub's `repository_dispatch` API — **no polling, no custom webhook servers**. One webhook URL handles everything.

| Source | Method | Trigger Event |
|--------|--------|---------------|
| 🔴 **Sentry** | Sentry Webhook Platform → `repository_dispatch` | `sentry-alert` |
| 📊 **Elastic APM** | Elastic Watcher → HTTP action → `repository_dispatch` | `elastic-alert` |
| 📋 **Jira** | Jira Automation rule → webhook | `jira-ticket` |
| 📌 **Linear** | Linear webhook integration | `linear-issue` |
| 🔔 **PagerDuty** | PagerDuty webhook V3 | `pagerduty-incident` |
| 📝 **GitHub Issue** | `issues: [opened, reopened]` (already live) | native |

**Example — Sentry alert payload:**

```json
{
  "event_type": "sentry-alert",
  "client_payload": {
    "title": "TypeError: Cannot read property 'id' of undefined",
    "affected_file": "mod/assign/submission/file/lib.php",
    "stack_trace": "...",
    "severity": "HIGH",
    "sentry_url": "https://sentry.io/issues/12345/"
  }
}
```

The **Triage Agent** reads `github.event.client_payload` and decides: actionable, duplicate, or out of scope — before any code generation begins.

---

### 🧠 2. Planning Agent

> [!TIP]
> The POC coder jumps straight from issue text to code. Production needs a dedicated **Planning Agent** that reads the codebase first and produces a structured implementation plan before a single line of code is written.

- Uses `tool_loop()` — **already scaffolded in `common.py`**, currently unused
- No hard file limit — agent explores until it has enough context
- Outputs `plan.json` which the Coder follows instead of improvising:

```json
{
  "summary": "Add null check before accessing submission->id",
  "files_to_modify": ["mod/assign/submission/file/lib.php"],
  "new_tests": ["mod/assign/tests/submission_file_test.php"],
  "db_migration_needed": false,
  "risks": ["Affects all submission types — regression risk in assign module"]
}
```

---

### 🧪 3. Real Test Execution

> [!TIP]
> The POC generates test code but never runs it. Production executes tests inside GitHub Actions and feeds **ground-truth results** back to the agents — not just code analysis.

**PHPUnit** runs inside the Actions runner and results are committed to `.pipeline/`:

```yaml
- name: Run PHPUnit
  run: |
    vendor/bin/phpunit --testsuite mod_assign \
      --log-junit .pipeline/phpunit-results.xml
```

**Behat** for integration-level coverage:

```yaml
- name: Run Behat
  run: |
    vendor/bin/behat --tags=@mod_assign \
      --format=json --out=.pipeline/behat-results.json
```

Results flow into the **Fix Agent** and **Reviewer** — both see actual failure messages, not inferred ones.

---

### 🔒 4. Security Scanning

> [!WARNING]
> The POC has **zero security scanning**. Production runs three complementary tools in parallel — all outputting SARIF that GitHub renders as native inline PR code annotations.

| Tool | What It Catches | Cost |
|------|-----------------|------|
| ![Semgrep](https://img.shields.io/badge/Semgrep-SAST-blue?style=flat-square) | PHP injection, XSS, insecure functions, Moodle-specific rules | Free tier available |
| ![CodeQL](https://img.shields.io/badge/CodeQL-Data--flow-24292f?style=flat-square&logo=github) | Deep taint tracking, data-flow analysis | Free for public repos |
| ![Snyk](https://img.shields.io/badge/Snyk-Dependencies-4c5fd5?style=flat-square) | Composer CVEs, known vulnerable packages | Free tier available |

```yaml
- uses: returntocorp/semgrep-action@v1
  with:
    config: "p/php p/owasp-top-ten"
    sarif_file: .pipeline/semgrep.sarif

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: .pipeline/semgrep.sarif
```

Security findings are also parsed into `.pipeline/security.json` and injected into the Reviewer's system prompt — so review comments cite actual violations by file and line number.

---

### 🔄 5. Multi-Round Review (up to 3 rounds)

> [!NOTE]
> GitHub Actions has no dynamic loops — rounds are static jobs. Production adds a third round with an escalation gate for findings that survive all rounds.

```
Round 1 ──► Round 2 ──► Round 3 (only if HIGH severity remains) ──► Escalate
```

Each round has **full context**:
- Code diff from the current round
- PHPUnit + Behat results
- Security findings (`security.json`)
- Fix/Defend dispositions from all prior rounds

A finding defended across all three rounds is automatically marked `ESCALATED` and appears in the PR as a permanently open inline comment requiring human sign-off.

---

### 📬 6. Draft PR with Inline Comments

> [!NOTE]
> The POC already opens a PR with inline comments. Production extends every dimension of it.

| Feature | POC | Production |
|---------|-----|-----------|
| PR state | Regular PR | **Draft** — not mergeable until human approves |
| Fixed findings | Posted as comments | **Resolved threads** — collapsed, still visible |
| Defended findings | Posted as comments | **Open threads** — with coder's defense reasoning |
| PR description | Basic summary | Test summary + security counts + source context |
| Notification | None | **Slack / Teams** on open, escalation, and failure |

---

### ✅ 7. Production-Readiness Checklist

| Area | What to Add | Priority |
|------|-------------|----------|
| 📈 **Observability** | Structured JSON logs per agent job → Elastic/Datadog. Track token usage, latency, pass/fail rate per round. | 🔴 High |
| 💰 **Cost controls** | Hard token budget per run. Abort + notify if exceeded. Use nano models for triage, reserve full models for coding. | 🔴 High |
| 🔁 **Idempotency** | Check if `agent/issue-{N}` branch exists before creating. Deduplicate Sentry alerts by fingerprint. | 🔴 High |
| 🔄 **Retry on failure** | `max-retries: 2` per agent job for transient API errors. Commit partial state so retries skip completed work. | 🟡 Medium |
| 📣 **Human escalation** | If pipeline exits with unresolved HIGH findings, auto-assign PR to lead reviewer + post Slack alert. | 🟡 Medium |
| 🔔 **Notifications** | Post pipeline start / end / failure to a dedicated Slack or Teams channel with PR link + agent summary. | 🟡 Medium |
| 🔐 **Secrets management** | LLM API keys in GitHub Secrets (or Azure Key Vault). Rotate `GH_PAT` on a schedule. Never log keys in agent output. | 🔴 High |
| 🌿 **Branch hygiene** | Auto-delete `agent/issue-{N}` branches when PR is closed without merging. Enforce naming via branch protection. | 🟢 Low |
| ⏮️ **Rollback** | Tag commit before applying agent changes. Auto-close PR if PHPUnit regression rate exceeds threshold. | 🟡 Medium |
| ⚡ **Concurrency** | `concurrency: group: issue-${{ github.event.issue.number }}` to prevent two runs for the same issue racing. | 🔴 High |
| 🛡️ **Scope guardrails** | Triage agent rejects issues touching >N files or requiring schema changes beyond a set complexity. Routes to human planning. | 🟡 Medium |

---

### 🔀 8. Alternative: Copilot SWE Agent + Actions Review Loop

> [!TIP]
> Instead of building the coder from scratch, delegate coding to GitHub's **Copilot coding agent** and use the Actions pipeline purely as a quality gate. Clean separation of responsibilities.

```
Issue assigned to copilot-swe-agent[bot] via REST API
          │
          ▼
  Copilot opens Draft PR with code + tests
          │
          ▼
  GitHub Actions: PR opened trigger
    → 🔎 Review Agent (Claude / Mistral)
    → 🧪 PHPUnit runner
    → 🔒 Semgrep scanner
          │  findings / failures
          ▼
  Re-assign to copilot-swe-agent[bot] with comments
          │
          ▼
  Copilot pushes fixes → Actions re-runs
          │  (repeat up to 3×)
          ▼
  👤 Human review gate
```

**REST API assignment:**

```bash
gh api repos/{owner}/{repo}/issues/{number}/assignees \
  -X POST \
  -f "assignees[]=copilot-swe-agent[bot]"
```

> [!NOTE]
> Requires **GitHub Copilot Business or Enterprise** license. Claude is assignable from the GitHub UI as an alternative model for the same Copilot agent.

---

### 📊 POC → Production: At a Glance

| Capability | 🔬 POC (Today) | 🚀 Production (Target) |
|------------|---------------|----------------------|
| **Trigger** | GitHub Issue only | Any webhook via `repository_dispatch` |
| **Planning** | ❌ Coder improvises | ✅ Dedicated Planning Agent |
| **Coder scope** | PHP · 4 files max | PHP + JS/TS · unlimited via `tool_loop` |
| **Test execution** | ❌ Generated, not run | ✅ PHPUnit + Behat executed, results fed back |
| **Security** | ❌ None | ✅ Semgrep + CodeQL + Snyk (SARIF) |
| **Review rounds** | Max 2 | Max 3 + escalation gate |
| **PR type** | Regular PR | Draft PR with resolved/unresolved threads |
| **Notifications** | ❌ None | ✅ Slack / Teams |
| **Observability** | ❌ None | ✅ Structured logs + cost tracking |
| **Concurrency** | ⚠️ Conflicts possible | ✅ Per-issue concurrency group |
| **Retry** | ❌ None | ✅ 2 retries per job |
| **Rollback** | ❌ None | ✅ Auto-close on regression |

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


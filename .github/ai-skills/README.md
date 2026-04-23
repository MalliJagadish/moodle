# AI Skills

Every `.md` file in this directory is automatically loaded into the system
prompt of both the **Coder** and **Reviewer** agents when the pipeline runs.

## Context-aware loading

Skills are loaded **selectively** based on the files being worked on. Add a
YAML frontmatter block with `tags` to control when a skill is loaded:

```markdown
---
tags: controller, api, webservice
---
# My Skill
- Rule 1
- Rule 2
```

**How matching works:**
- Tags are matched against file paths and issue keywords
- A skill with `tags: form, validation` loads when the issue mentions "form" or the coder finds form files
- Skills **without tags** are always loaded (global rules)
- If no tagged skills match, all skills are loaded as a fallback

## Current skills

| File | Tags | Purpose |
|---|---|---|
| `moodle-coding-standards.md` | *(none — always loaded)* | Core PHP, security, and file naming rules |
| `controllers.md` | `controller, external, webservice, api` | External API & endpoint standards |
| `services.md` | `service, lib, classes, manager, task` | Service classes & background tasks |
| `forms.md` | `form, moodleform, validation, input` | Moodleform standards |
| `database.md` | `db, database, migration, sql, schema` | DML & XMLDB migration rules |

## Tips

- Keep each file focused on one topic
- Use clear headings — the model reads them as-is
- Be specific: "use `PARAM_TEXT` not `PARAM_RAW`" beats "validate inputs"
- Skills without tags are global — use tags to avoid loading irrelevant rules
- The reviewer uses these to flag violations, so rules here become enforced checks

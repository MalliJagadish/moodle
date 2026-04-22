# AI Skills

Every `.md` file in this directory is automatically loaded into the system
prompt of both the **Coder** and **Reviewer** agents when the pipeline runs.

## How to add a skill

Create a new `.md` file here. It will be picked up on the next pipeline run
without any code changes. File names are sorted alphabetically, so prefix with
a number if order matters (e.g. `01-security.md`, `02-php-style.md`).

## Current skills

| File | Purpose |
|---|---|
| `moodle-coding-standards.md` | Core PHP, form, security, and file naming rules |

## Tips

- Keep each file focused on one topic
- Use clear headings — the model reads them as-is
- Be specific: "use `PARAM_TEXT` not `PARAM_RAW`" beats "validate inputs"
- The reviewer uses these to flag violations, so rules here become enforced checks

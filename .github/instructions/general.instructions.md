---
applyTo: "**/*.php"
---
# Moodle General Standards

- All PHP files must start with `<?php` and include `defined('MOODLE_INTERNAL') || die();`
- Use `require_once` only at the top of files, never inside functions
- All user-facing strings must use `get_string('key', 'component')` — never hardcode English
- Never use `echo` directly in lib files; use `$OUTPUT->render()` or return HTML
- All SQL must use Moodle DML (`$DB->get_records`, `$DB->execute`) — never raw `mysqli`
- Capability checks are mandatory before any privileged action: `require_capability('...', $context)`
- Validate all input: use `required_param()` / `optional_param()` with appropriate PARAM_ type
- Always use `s()` or `format_string()` when outputting user-supplied content to prevent XSS
- Never store passwords or tokens in code or lang strings
- Class files: one class per file, filename matches class name (lowercase, underscores)
- Plugin files follow Moodle component structure (`lang/`, `classes/`, `db/`)

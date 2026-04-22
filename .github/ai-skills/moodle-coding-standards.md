# Moodle Coding Standards

## PHP
- All PHP files must start with `<?php` and include `defined('MOODLE_INTERNAL') || die();`
- Use `require_once` only at the top of files, never inside functions
- All user-facing strings must use `get_string('key', 'component')` — never hardcode English
- Never use `echo` directly in lib files; use `$OUTPUT->render()` or return HTML
- All SQL must use Moodle DML (`$DB->get_records`, `$DB->execute`) — never raw `mysqli`
- Capability checks are mandatory before any privileged action: `require_capability('...', $context)`
- Validate all input: use `required_param()` / `optional_param()` with appropriate PARAM_ type
- Always use `s()` or `format_string()` when outputting user-supplied content to prevent XSS

## Forms
- All forms must extend `moodleform`
- Use `PARAM_TEXT` for text inputs, not `PARAM_RAW` or `PARAM_RAW_TRIMMED`
- Always implement `validation()` for custom field constraints

## File naming
- Class files: one class per file, filename matches class name (lowercase, underscores)
- Plugin files follow Moodle component structure (`lang/`, `classes/`, `db/`)

## Security
- Never store passwords or tokens in code or lang strings
- Use `$CFG->dataroot` for file storage, never web-accessible paths
- Rate-limit expensive operations using Moodle's `\core\lock` API

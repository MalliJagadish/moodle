---
applyTo: "**/form.php, **/form_*.php, **/classes/form/**/*.php, **/*_form.php"
---
# Form Standards

- All forms must extend `\moodleform`
- Define all elements in `definition()`, not in the constructor
- Implement `validation($data, $files)` for server-side validation — never rely on client-side only
- Use `PARAM_TEXT` for text, `PARAM_INT` for IDs, `PARAM_URL` for URLs — never `PARAM_RAW`
- Use `$mform->addRule()` for required fields
- Always call `$mform->setType()` for every element
- File uploads: use `$mform->addElement('filepicker', ...)` with proper `accepted_types`
- Use `get_string()` for all labels and error messages

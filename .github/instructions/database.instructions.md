---
applyTo: "**/db/*.php, **/db/*.xml, **/install.xml, **/upgrade.php"
---
# Database & Migration Standards

- Schema changes go in `db/install.xml` (XMLDB format)
- Upgrade steps go in `db/upgrade.php` with version bump in `version.php`
- Always use `$DB->get_record()`, `$DB->insert_record()`, `$DB->update_record()` — never raw SQL
- Use `$DB->get_recordset()` for large result sets (memory efficient)
- SQL placeholders: use `$DB->sql_like()` for LIKE, named params `['id' => $id]`
- Never use `SELECT *` — list required columns explicitly
- Add indexes in `install.xml` for columns used in WHERE/JOIN/ORDER BY
- Wrap multi-step writes in `$DB->start_delegated_transaction()`

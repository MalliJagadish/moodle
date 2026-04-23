---
applyTo: "**/classes/**/*.php, **/lib.php, **/locallib.php"
---
# Service & Library Standards

- Service classes go in `classes/` directory following PSR-4 autoloading
- Use dependency injection where possible, avoid global state
- Long-running operations must use `\core\task\adhoc_task` or `\core\task\scheduled_task`
- Fire appropriate events (`\core\event\*`) for auditable actions
- Caching: use `\cache` API for expensive lookups, define caches in `db/caches.php`
- Use `$CFG->dataroot` for file storage, never web-accessible paths
- Rate-limit expensive operations using Moodle's `\core\lock` API

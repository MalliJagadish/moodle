---
tags: service, lib, classes, manager, helper, task
---
# Service & Library Standards

- Service classes go in `classes/` directory following PSR-4 autoloading
- Use dependency injection where possible, avoid global state
- Long-running operations must use Moodle's `\core\task\adhoc_task` or `\core\task\scheduled_task`
- Database transactions: wrap multi-step writes in `$DB->start_delegated_transaction()`
- Events: fire appropriate events (`\core\event\*`) for auditable actions
- Caching: use `\cache` API for expensive lookups, define caches in `db/caches.php`

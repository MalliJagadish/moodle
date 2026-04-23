---
tags: controller, external, webservice, api, endpoint, rest
---
# Controller & External API Standards

- External functions must extend `\core_external\external_api`
- Define `execute_parameters()`, `execute()`, and `execute_returns()` for every external function
- Use `validate_parameters()` at the start of `execute()`
- Always call `validate_context()` after getting the context
- Return types must match `execute_returns()` exactly
- Use `external_function_parameters`, `external_value`, `external_single_structure`
- Never expose internal IDs without capability checks

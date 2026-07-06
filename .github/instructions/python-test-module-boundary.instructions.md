---
applyTo: "**/*.py"
description: "Enforce one unit test module per Python production module."
---

- Every Python production module must have its own dedicated unit test module.
- Do not combine tests for different production modules into a single unit test file.
- When you create, split, or rename a Python module, create or update the matching unit test module at the same time.
- Prefer test module names that mirror the production module path so ownership stays obvious.
- If a change would naturally affect more than one production module, keep each module's unit tests in separate test files and cross-check shared helpers instead of merging the tests.
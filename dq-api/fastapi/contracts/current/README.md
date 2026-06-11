# Current FastAPI Contract Artifacts

This directory contains the generated current OpenAPI snapshot for the live FastAPI route map and the companion proof submission contract reference used for publication.

Artifacts:

- [openapi-fastapi-v1.json](openapi-fastapi-v1.json): current FastAPI OpenAPI export captured from the live app.
- [Test proof payload contract](../../../../docs/contracts/test-proof-payload/README.md): canonical proof submission schema and OpenAPI fragment for `POST /api/rulebuilder/v1/rules/{rule_id}/test`.

The proof contract is kept in the shared docs contract package so it can be versioned independently from the live OpenAPI export while still being published alongside it.
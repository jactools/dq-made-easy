# Profiling Request Generator Changelog

Status: Done

## 2026-04-05

- Added a separate repeatable profiling request generator at `scripts/generate_profiling_requests.sh`.
- Moved runtime configuration into repo-root `.env` and documented the variables in `.env.example`.
- Switched the generator to use the shared `scripts/supporting/logging.sh` helper and fail fast when required values are missing.
- Fixed the Kong route target to `/v1/profiling/enqueue`.
- Updated auth to use a Keycloak password-grant token, then seeded the backend session from the JWT `sid` claim.
- Aligned the live data source and user IDs with the actual seeded database rows.
- Verified the full flow end to end: 5 profiling requests were enqueued successfully.

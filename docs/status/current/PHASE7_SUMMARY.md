# Phase 7 Summary

## Current Browser Auth

The supported browser auth path now goes directly through Kong.

## Current Chain

- `dq-ui -> Kong -> dq-api`
- Kong is the JWT validation and browser auth enforcement layer.
- The local browser API base is `http://localhost:9111`.

## Operational Notes

- `TRUST_PROXY_AUTH=true` remains required for the trusted gateway path.
- `SSO_ISSUER` must match the canonical public Keycloak issuer.
- Historical browser-proxy rollout notes are no longer current.

## Summary

The gateway rollout is complete, and the direct-Kong browser auth path is now the active supported flow.

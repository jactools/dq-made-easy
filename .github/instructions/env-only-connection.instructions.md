---
name: Env Only Connection Rule
description: Enforce that scripts, compose, and bootstrap code only use service connection values supplied by `.env.*.local` files and fail fast when required env vars are missing.
applyTo: "**/*"
---

# Env Only Connection Rule

This is a hard repository rule.

## Requirements

- Scripts, bootstrap code, and compose wiring must not invent their own service connection settings.
- Do not add hardcoded host, port, URL, realm, username, password, or path fallbacks for service connectivity.
- Do not derive alternate connection paths when a value is missing by guessing defaults such as `db`, `postgres`, `keycloak`, `http://`, `localhost`, or `127.0.0.1`.
- Connection values must come from the selected `.env.*.local` file or from values that file explicitly exports.
- If a required env var is missing, the script must fail immediately with a clear error instead of substituting a fallback.
- If a script needs a derived value, derive it only from env vars that were already provided by the selected env file.
- Do not add a second, script-local connection mechanism alongside the env-file contract.

## Scope

This rule applies to shell scripts, Python bootstrap code, Compose files, startup wrappers, validation scripts, and any other code that reaches internal services.

## Enforcement Intent

Treat missing env vars as a configuration error, not a reason to create a fallback path. The selected env file is the only source of service connectivity for local and deployment flows.

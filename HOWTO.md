# Project Implementation Guide

## Table of Contents
1. [General Rules](#general-rules)
2. [Versioning and Documentation](#versioning-and-documentation)
3. [UI Components and Styling](#ui-components-and-styling)
4. [Running Tests](#running-tests)

---

## General Rules

### No Fallbacks
- **Never implement fallback logic** for features, APIs, or UI states.
- If a feature or API is unavailable, fail fast and clearly (e.g., show an error message or disable the feature).
- Example: If an API call fails, display an error message instead of falling back to cached or stale data.

### Attribute naming conventions
- All API payloads must use snake_case
- The Raact UI will convert received snake_case name to camelCase. When creating a payload, the front-end will convert camelCase into snake_case for the API to use.
- There must be only one attribute for one specific piece of information (canonical field names)

**UI conversion boundary (fail fast)**
- Treat snake_case as the on-the-wire contract. The UI must convert at the boundary (request/response) and keep internal UI models in camelCase.
- Prefer using the shared request/response normalization in `dq-ui/src/telemetry.ts` rather than ad-hoc per-component conversions.
- UI components/hooks should assume they receive camelCase payloads (post-normalization). If snake_case keys appear in UI code, treat it as a bug and surface an error (normalization broken or bypassed).

### FastAPI and SQLAlchemy

- All APIs must be written using FastAPI
- All database queries and connections in API must be made through SQLAlchemy
- All APIs follow the entity-based approach with domains, entities, interfaces, and with infrastructure for models, in_memory and postgres
- Contracts must exist for all payloads
- Naming conventions must be followed. For APIs that means e.g. all attribute names are snake_case
- All APIs must have unit tests with a minimum of 60% coverage. Each branch must have its own unit test.
- Unit tests must not only cover the happy flow

---

## Versioning and Documentation

### Version Bumps
- **Always bump the version** in `package.json` or `pyproject.toml` when making changes.
- Follow [Semantic Versioning](https://semver.org/):
  - `MAJOR`: Breaking changes
  - `MINOR`: New features (backward-compatible)
  - `PATCH`: Bug fixes (backward-compatible)
- use the VERSION_MANIFEST.json when bumping a version

### Documentation
- **Always generate/update documentation** when bumping the version.
- Use tools like:
  - [Sphinx](https://www.sphinx-doc.org/) (Python)
  - [JSDoc](https://jsdoc.app/) (JavaScript/TypeScript)
  - [Storybook](https://storybook.js.org/) (UI components)
- Include:
  - API changes
  - New features
  - Deprecations
  - Usage examples

---

## UI Components and Styling

-### Use App-Owned Components
- **Always use app-owned UI components and styles**.
- Never create custom components or styles unless absolutely necessary and approved.

---

## Running tests

### General
- ignore the many files under dist when running tests

### Python
- use the python_arm64.sh script when running pytest, or use arch -arm64
- overall coverage must be above 90%
- file coverage must be above 60%
- all branches must have unit tests
- test fixtures hold test data, no in-code json demo data is allowed for non-ORM code

### NPM

## Database

### Never generate create / alter table statements for db changes
- use SQLAlchemy models and Alembic for migrations



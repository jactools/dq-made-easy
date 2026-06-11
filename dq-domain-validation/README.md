# dq-made-easy-domain-validation

Shared runtime domain validation for dq-made-easy APIs.

The package provides two things:

- a versioned registry of allowed-value sets stored separately from API code
- Pydantic-compatible validators that can be reused by FastAPI request and response models

Build a wheel with:

```bash
python -m build --wheel
```

The wheel is intended to be consumed by all API services instead of hard-coding enums or ad hoc allowlists in each service.
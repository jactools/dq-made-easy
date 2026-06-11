# Downstream Script Call Graph for start-containers.sh


```mermaid
flowchart TD
    A[start-containers.sh]
    A --> B[logging.sh]
    A --> C[setup_env.sh]
    A --> D[keycloak_readiness.sh]
    A --> E[start_stack.sh]
    A --> F[seed_stack.sh]
    A --> G[local_build_frontend.sh]
    A --> H[python_arm64.sh]
    E --> I[dq-kong/scripts/bootstrap_kong.sh]
    G --> J[dq-ui/scripts/start_local.sh]
```

- **Dashed lines** indicate indirect calls (e.g., start_stack.sh calls bootstrap_kong.sh).
- Only the main scripts are shown; some scripts (like logging.sh) are sourced by others as well.
- This diagram is based on the current structure of start-containers.sh and its most common downstream scripts.

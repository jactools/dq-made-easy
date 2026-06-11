# Downstream Script Call Graph for start-containers.sh


```mermaid
flowchart TB
    A[start-containers.sh]
    A --> E[start_stack.sh]
    A --> F[seed_stack.sh]
    A --> G[local_build_frontend.sh]
    F --> J[db-seed service]
    F --> K[zammad-seed service]
    F --> L[openmetadata-configure service]
    F --> M[delivery-seed service]
    E --> V[dq-kong/scripts/bootstrap_kong.sh]
    E --> AB[dq-ui/scripts/start_local.sh]
    AB --> AI[Vite dev server]
    V --> AJ[Kong Gateway]
    J --> AK[Postgres]
    K --> AL[Zammad]
    L --> AM[OpenMetadata]
    M --> AN[AIStor]

    %% Notes:
    %% - This vertical layout omits logging.sh, setup_env.sh, and .env for clarity.
    %% - Only key scripts and service interactions are shown.
```

- This layout omits utility scripts and focuses on the main orchestration and service interactions.
- You can further collapse or expand nodes as needed for your use case.

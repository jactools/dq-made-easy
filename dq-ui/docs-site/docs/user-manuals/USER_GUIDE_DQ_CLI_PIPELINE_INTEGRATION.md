# Deploying the DQ CLI and DQ Engine

This guide describes how the existing DQ CLI and the DQ engine can be deployed in three common environments:

1. Databricks
2. Kubernetes, with the DQ engine running as a separate pod
3. A containerized Spark environment deployed to Azure Container Apps

## Overview

The repository already provides:

- a CLI entry point named `dq-run-plan` in [dq-cli/pyproject.toml](https://github.com/jactools/dq-rulebuilder/blob/main/dq-cli/pyproject.toml)
- the CLI implementation in [dq-cli/dq_cli/run_plan.py](https://github.com/jactools/dq-rulebuilder/blob/main/dq-cli/dq_cli/run_plan.py)
- a containerized engine build in [dq-engine/Dockerfile.engine](https://github.com/jactools/dq-rulebuilder/blob/main/dq-engine/Dockerfile.engine)
- a FastAPI engine entry point in [dq-engine/main.py](https://github.com/jactools/dq-rulebuilder/blob/main/dq-engine/main.py)
- a technical reference for run-plan initiation, replay, and YAML/JSON payload handling in [docs/technical/DQ-12_RUN_PLAN_INITIATION_API_AND_CLI.md](/docs/technical/DQ-12_RUN_PLAN_INITIATION_API_AND_CLI/)

Before you can invoke the CLI against a pipeline, the DQ run plan must already exist and be registered in the DQ solution. The run-plan definition and registration flow are described in [docs/technical/DQ-12_RUN_PLAN_INITIATION_API_AND_CLI.md](/docs/technical/DQ-12_RUN_PLAN_INITIATION_API_AND_CLI/).

The intended pattern is:

1. the pipeline or orchestration layer triggers the CLI,
2. the CLI calls the DQ API with the run-plan business key,
3. the DQ engine performs the execution against the configured data source.

The CLI should be treated as the trigger layer. The DQ engine is the execution layer.

## Common prerequisites

Regardless of the target platform, the deployment should provide:

- a reachable DQ API base URL
- authentication for the CLI, preferably via a service-account token or secret
- the run-plan business key, passed as `--run-plan-name`
- connectivity from the engine to the target data source
- the relevant connector and credentials already configured in the DQ platform

## Deployment pattern A: Databricks

### Recommended architecture

For Databricks, the simplest pattern is:

- install or bundle the CLI on the Databricks job cluster,
- run the CLI as the final step in a notebook or job task,
- keep the DQ engine as a separate service endpoint that Databricks can reach over the network.

This is usually the most practical option because the engine has service-style runtime needs and is better treated as a reachable execution endpoint than as an inline library call.

### Example notebook pattern

```python
import os
import subprocess

os.environ["DQ_API_BASE_URL"] = "https://your-dq-api.example.com"
os.environ["DQ_RUN_PLAN_TOKEN"] = dbutils.secrets.get(scope="dq", key="token")
os.environ["DQ_RUN_PLAN_NAME"] = "your-run-plan-business-key"

subprocess.run([
    "python",
    "-m",
    "pip",
    "install",
    "dq-made-easy-cli",
], check=True)

subprocess.run([
    "dq-run-plan",
    "invoke",
    "--base-url", os.environ["DQ_API_BASE_URL"],
    "--token", os.environ["DQ_RUN_PLAN_TOKEN"],
    "--run-plan-name", os.environ["DQ_RUN_PLAN_NAME"],
    "--json",
], check=True)
```

### Databricks deployment notes

- Store tokens in Databricks secrets.
- Put the DQ validation step at the end of the job so it fails the job when validation fails.
- If the engine is deployed in the same network boundary, expose it through a private endpoint or internal DNS name so the job can reach it.
- If you want the engine to run inside the same cluster environment, package it as a container image and run it as a separate service or sidecar process, but keep the CLI as the trigger step.

## Deployment pattern B: Kubernetes with the DQ engine as a separate pod

### Recommended architecture

In Kubernetes, the cleanest model is:

- one deployment for the DQ engine,
- one service that exposes the engine,
- one job or workload that runs the CLI after the ETL or data load completes.

### Example DQ engine deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dq-engine
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dq-engine
  template:
    metadata:
      labels:
        app: dq-engine
    spec:
      containers:
        - name: dq-engine
          image: your-registry/dq-engine:latest
          ports:
            - containerPort: 8000
          env:
            - name: DQ_LOG_LEVEL
              value: INFO
            - name: DQ_API_BASE_URL
              value: "https://your-dq-api.example.com"
---
apiVersion: v1
kind: Service
metadata:
  name: dq-engine
spec:
  selector:
    app: dq-engine
  ports:
    - port: 8000
      targetPort: 8000
```

### Example CLI job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: dq-plan-runner
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: dq-plan
          image: your-registry/dq-runner:latest
          env:
            - name: DQ_API_BASE_URL
              value: "https://your-dq-api.example.com"
            - name: DQ_RUN_PLAN_NAME
              value: "your-run-plan-business-key"
            - name: DQ_RUN_PLAN_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dq-secrets
                  key: token
          command: ["python", "/app/run_dq_plan.py"]
```

### Kubernetes deployment notes

- Use a secret for the CLI token.
- Keep the engine reachable from the CLI over the cluster service network.
- If the engine needs access to Spark or a shared storage backend, mount the required volumes and configure the relevant environment variables.
- The job should fail fast if the validation run is rejected.

## Deployment pattern C: Azure Container Apps with a containerized local Spark environment

### Recommended architecture

Azure Container Apps is a strong fit when you want to run a self-contained Spark-capable DQ engine in a container and trigger it from a lightweight CLI job or wrapper.

A practical layout is:

- one Container App for the DQ engine, based on the engine image,
- one Container Apps job for the CLI step,
- shared access to Azure Storage, Azure SQL, or another supported data source that the DQ connector can reach.

### Build approach

You can build the engine image from the repository’s existing container definition in [dq-engine/Dockerfile.engine](https://github.com/jactools/dq-rulebuilder/blob/main/dq-engine/Dockerfile.engine). That image already installs Java, Python, and Spark-related dependencies needed by the engine runtime.

### Example Azure Container Apps flow

1. Build and push the engine image to Azure Container Registry.
2. Deploy the engine as a Container App.
3. Deploy a CLI job or container that runs `dq-run-plan invoke ...` after your ETL step completes.
4. Point the CLI at the DQ API endpoint and the run-plan business key.

Example commands:

```bash
az acr build --registry <acr-name> --image dq-engine:latest .

az containerapp env create \
  --name dq-env \
  --resource-group <rg-name> \
  --location <region>

az containerapp create \
  --name dq-engine \
  --resource-group <rg-name> \
  --environment dq-env \
  --image <acr-name>.azurecr.io/dq-engine:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 1
```

Then run the CLI from a Container Apps job or an ephemeral job container:

```bash
az containerapp job create \
  --name dq-validation-runner \
  --resource-group <rg-name> \
  --environment dq-env \
  --image <acr-name>.azurecr.io/dq-runner:latest \
  --trigger-type Manual \
  --cpu 0.5 \
  --memory 1.0Gi
```

### Azure Container Apps deployment notes

- Use Container Apps secrets for the CLI token.
- Ensure the engine has network access to your data sources.
- For Spark-backed validation, mount or configure storage and any required credentials.
- If the engine and CLI are deployed in the same Container Apps environment, they can use internal networking and shared environment configuration.

## How the CLI and engine work together

The CLI does not read the data itself. It only triggers the validation workflow.

Once the run is accepted, the DQ engine resolves the plan and opens the configured data source using the connector and credentials that are already configured for the workspace or plan scope. For more background on the execution boundary, see [architecture/ddd-implementation.md](/docs/architecture/ddd-implementation/).

## Minimal wrapper script

A minimal wrapper for any of the above environments looks like this:

```python
import os
import subprocess
import sys

cmd = [
    "dq-run-plan",
    "invoke",
    "--base-url", os.environ["DQ_API_BASE_URL"],
    "--token", os.environ["DQ_RUN_PLAN_TOKEN"],
    "--run-plan-name", os.environ["DQ_RUN_PLAN_NAME"],
    "--json",
]

print("Running:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)

if result.returncode != 0:
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
```

## Authentication guidance

The CLI supports:

- bearer-token auth with `--token`
- Keycloak password-grant auth with `--issuer-url`, `--client-id`, `--username`, and `--password`

For production deployments, prefer a service-account token stored in a secret manager or platform secret store.

## Practical guidance

- Use a stable, human-readable run-plan business key for automation.
- Run the validation step at the end of the ETL or load pipeline.
- Make validation blocking so job failures are visible immediately.
- Capture CLI output and exit codes so problems are easy to diagnose.

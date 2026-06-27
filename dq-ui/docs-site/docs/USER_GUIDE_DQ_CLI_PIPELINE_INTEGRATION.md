# Running the DQ CLI from Data Pipelines

This guide shows how to invoke the existing DQ run-plan CLI from common pipeline environments such as Databricks, pySpark jobs, and Kubernetes containers.

## Overview

The repository already ships a CLI entry point named `dq-run-plan` in [dq-cli/pyproject.toml](https://github.com/jactools/dq-rulebuilder/blob/main/dq-cli/pyproject.toml). Its supported actions and arguments are implemented in [dq-cli/dq_cli/run_plan.py](https://github.com/jactools/dq-rulebuilder/blob/main/dq-cli/dq_cli/run_plan.py).

The typical integration pattern is:

1. Run your data transformation or load step.
2. Call the DQ CLI as a small wrapper step.
3. Pass the DQ API base URL and authentication details through environment variables or secrets.
4. Fail the pipeline if the DQ validation run is rejected or errors.

## 1. Minimal wrapper script

Create a small Python wrapper such as `run_dq_plan.py`:

```python
import os
import subprocess
import sys

cmd = [
    "dq-run-plan",
    "invoke",
    "--base-url", os.environ["DQ_API_BASE_URL"],
    "--token", os.environ["DQ_RUN_PLAN_TOKEN"],
    "--run-plan-id", os.environ["DQ_RUN_PLAN_ID"],
    "--json",
]

print("Running:", " ".join(cmd))
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)

if result.returncode != 0:
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
```

## 2. Running from Databricks

Use this in a notebook cell or a final job task after your ETL finishes.

```python
import os
import subprocess

os.environ["DQ_API_BASE_URL"] = "https://your-dq-api.example.com"
os.environ["DQ_RUN_PLAN_TOKEN"] = dbutils.secrets.get(scope="dq", key="token")
os.environ["DQ_RUN_PLAN_ID"] = "your-run-plan-id"

subprocess.run(["python", "/dbfs/FileStore/scripts/run_dq_plan.py"], check=True)
```

Recommended practices:

- Store credentials in Databricks secrets.
- Install the CLI in the job environment or bundle it in a wheel.
- Put this in a final validation step so failures block downstream completion.

## 3. Running from pySpark

Trigger the wrapper from the driver after the Spark write or transform stage completes.

```python
import os
import subprocess

# ... your Spark transformations ...

os.environ["DQ_API_BASE_URL"] = "https://your-dq-api.example.com"
os.environ["DQ_RUN_PLAN_TOKEN"] = "..."
os.environ["DQ_RUN_PLAN_ID"] = "..."

subprocess.run(["python", "/path/to/run_dq_plan.py"], check=True)
```

For Spark workloads, the safest approach is to invoke the CLI from the driver or from a downstream job step rather than from each worker.

## 4. Running from a Kubernetes container

Build a small image that contains the CLI, then run it as a Kubernetes Job or as a step in a workflow.

Example job manifest:

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
            - name: DQ_RUN_PLAN_ID
              value: "your-run-plan-id"
            - name: DQ_RUN_PLAN_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dq-secrets
                  key: token
          command: ["python", "/app/run_dq_plan.py"]
```

You can also invoke the CLI directly in the container:

```bash
dq-run-plan invoke \
  --base-url "$DQ_API_BASE_URL" \
  --token "$DQ_RUN_PLAN_TOKEN" \
  --run-plan-id "$DQ_RUN_PLAN_ID" \
  --json
```

## 5. Authentication options

The CLI supports two authentication patterns:

- Bearer token: `--token`
- Keycloak password grant: `--issuer-url`, `--client-id`, `--username`, and `--password`

For production pipelines, the recommended approach is to inject a service-account token from a secret store rather than hardcoding credentials.

## 6. Practical guidance

- Use the CLI after the data load or transformation step finishes.
- Make the validation step blocking so the pipeline fails quickly on DQ issues.
- Capture the CLI output and exit code for auditability.
- Prefer a dedicated run-plan ID per pipeline or dataset to make traces easier to manage.

# Airflow Validation Run Plan Integration

This document defines the first-party Airflow integration path for dq-made-easy validation run plans.

## Delivered assets

- `dq-api/fastapi/app/airflow_sdk.py` provides a small Python client for internal replay and run polling.
- `dq-api/fastapi/app/airflow_operator.py` provides an Airflow 3 operator that wraps replay and optional polling.
- `dq-airflow-sdk/pyproject.toml` packages the SDK into the `dq-made-easy-airflow-sdk` wheel.
- `dq-airflow-operator/pyproject.toml` packages the operator into the `dq-made-easy-airflow-operator` wheel.
- `scripts/package-releases/build_dq_airflow_sdk_wheel.sh` builds the `dq-made-easy-airflow-sdk` wheel from the repo source into `tmp/dq-airflow-sdk-dist/dq_made_easy_airflow_sdk-*.whl`.
- `scripts/package-releases/build_dq_airflow_operator_wheel.sh` builds the `dq-made-easy-airflow-operator` wheel from the repo source into `tmp/dq-airflow-operator-dist/dq_made_easy_airflow_operator-*.whl`.
- `scripts/build_dq_airflow_dag_artifact.sh` packages the example DAG into `tmp/dq-airflow-dags-dist/dq-airflow-dags.zip`.
- `docker/airflow/Dockerfile.airflow` builds a minimal Airflow 3 image that copies the prebuilt wheels under `/opt/airflow/wheels/`, installs the operator wheel into the image, and copies the DAG zip artifact under `/opt/airflow/dags/`.
- `docker/airflow/dags/dq_validation_run_plan.py` provides an example DAG that imports the installed operator package, triggers a validation run plan, and waits for completion.
- `docker-compose.yml` exposes the `airflow` profile for local stack usage.
- For distributed Spark replay, start the `spark` profile and set `DQ_SPARK_MASTER=spark://spark-master:7077` instead of the local default.

## Contract

- Replay uses the internal-only validation run plan route: `POST /api/rulebuilder/v1/validation-run-plans/&#123;run_plan_id&#125;/replay`.
- The SDK stamps Airflow-origin metadata by sending `trigger_type=pipeline_run` and `source_pipeline=airflow` by default.
- Run polling uses `GET /api/rulebuilder/v1/gx/runs/&#123;run_id&#125;`.
- The SDK fails fast when token acquisition fails, replay returns a non-`202` response, run polling returns a non-`200` response, the run reaches `failed` or `cancelled`, or the polling timeout expires.

## Environment contract

The example DAG and compose profile use these environment variables:

- `DQ_AIRFLOW_BASE_URL`: internal Kong URL reachable from Airflow, for example `https://kong:8443`.
- `DQ_AIRFLOW_ISSUER_URL`: Keycloak realm issuer URL, for example `http://keycloak:8080/realms/jaccloud`.
- `DQ_AIRFLOW_CLIENT_ID`: OIDC client id used for password-grant token acquisition.
- `DQ_AIRFLOW_USERNAME`: user or service-account username. In the seeded local stack this resolves to the rotated operator login by default.
- `DQ_AIRFLOW_PASSWORD`: password for the selected user. In the seeded local stack this resolves to the rotated operator password by default.
- `DQ_AIRFLOW_RUN_PLAN_ID`: validation run plan id that the example DAG should replay.
- `DQ_AIRFLOW_SOURCE_PIPELINE`: optional pipeline label; defaults to `airflow`.
- `DQ_AIRFLOW_WAIT_TIMEOUT_SECONDS`: optional completion timeout.
- `DQ_AIRFLOW_POLL_INTERVAL_SECONDS`: optional polling interval.
- `DQ_AIRFLOW_SCHEDULED_AT`: optional replay schedule override in ISO 8601 format.

For seeded environments, `dq-keycloak/scripts/generate_seed_artifacts.sh` exports the dedicated Airflow auth persona as `OPERATOR_LOGIN_EMAIL` and `OPERATOR_LOGIN_PASSWORD` in `tmp/keycloak_seed_user_credentials.&lt;stage&gt;.env`. The standard startup path then sources `scripts/load_seeded_user_credentials.sh`, which publishes `DQ_AIRFLOW_USERNAME` and `DQ_AIRFLOW_PASSWORD` from those rotated operator credentials. Compose keeps generic fallbacks so `keycloak-seed-artifacts` can run before the rotated operator password exists, but normal stack startup should rely on the seeded operator persona rather than the general `KEYCLOAK_JACCLOUD_*` login.

`DQ_AIRFLOW_RUN_PLAN_ID` is intentionally required at task runtime rather than container startup. The Airflow service can boot without targeting a specific run plan, but the task fails immediately if the run plan id is missing.

## Local usage

Start the stack profile with an env file that already contains the standard Keycloak and Kong settings:

```bash
scripts/package-releases/build_dq_airflow_sdk_wheel.sh
scripts/package-releases/build_dq_airflow_operator_wheel.sh
scripts/build_dq_airflow_dag_artifact.sh
docker compose --env-file .env.dev.local --profile gateway --profile airflow up airflow
```

If you start the repo-managed stack through `scripts/start_stack.sh`, the script already sources `scripts/load_seeded_user_credentials.sh` and exports the rotated operator credentials into `DQ_AIRFLOW_USERNAME` and `DQ_AIRFLOW_PASSWORD` before the Airflow profile is rendered.

The bundled service exposes the Airflow UI on `$&#123;AIRFLOW_HOST_PORT:-8088}` and authenticates the browser UI through Keycloak-backed FAB OAuth. The browser login uses the seeded `airflow` OIDC client, while the DQ operator credentials remain separate on `DQ_AIRFLOW_USERNAME` and `DQ_AIRFLOW_PASSWORD`.

## Behavior notes

- The example DAG is intentionally built on the internal replay seam; it does not call the removed public replay wrapper.
- Because replay is internal-only, the default Airflow base URL must point at the dq-api service rather than Kong.
- The Airflow 3 operator propagates an Airflow-derived `correlation_id`, returns the final execution-run payload to XCom, and exposes `run_id`, `status`, and replay metadata for downstream tasks.
- The SDK wheel is built before the Airflow image build and is not installed into the Airflow image site-packages. The operator installs it at task execution time into an isolated target directory.
- The operator wheel is built before the Airflow image build and installed into the Airflow image site-packages so the DAG can import it at parse time.
- The example DAG is deployed as a zip artifact inside the Airflow image rather than a bind-mounted source directory.
- Airflow retries remain an Airflow concern. The dq-made-easy SDK itself does not mask API or execution failures.
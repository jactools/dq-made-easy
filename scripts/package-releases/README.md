# Python Package Release Scripts

This folder contains canonical build and publish scripts for the repo Python packages:

- `dq-made-easy-cli` via `release_dq_made_easy_cli.sh`
- `dq-made-easy-utils` via `release_dq_utils.sh`
- `dq-made-easy-domain-validation` via `release_dq_domain_validation.sh`
- `dq-made-easy-airflow-sdk` via `release_dq_airflow_sdk.sh`
- `dq-made-easy-airflow-operator` via `release_dq_airflow_operator.sh`

Wheel-only build helpers for Airflow image artifacts:

- `build_required_wheels.sh` (single wrapper used by startup to build required wheel artifacts)
- `build_dq_airflow_wheels.sh` (builds both SDK and operator wheels)
- `build_dq_airflow_sdk_wheel.sh`
- `build_dq_airflow_operator_wheel.sh`

Airflow DAG artifact build helper:

- `build_dq_airflow_dag_artifact.sh`

All scripts:

- use the repo venv Python (`venv/bin/python`) through `scripts/python_arm64.sh`
- build `sdist` and `wheel`
- run `twine check`
- optionally upload with `twine upload`
- bump the package patch version in `pyproject.toml` after successful publish

## Dry-run examples

```bash
scripts/package-releases/release_dq_made_easy_cli.sh --dry-run
scripts/package-releases/release_dq_utils.sh --dry-run
scripts/package-releases/release_dq_domain_validation.sh --dry-run
scripts/package-releases/release_dq_airflow_sdk.sh --dry-run
scripts/package-releases/release_dq_airflow_operator.sh --dry-run
```

## Publish examples

```bash
scripts/package-releases/release_dq_made_easy_cli.sh --repository pypi
scripts/package-releases/release_dq_utils.sh --repository pypi
scripts/package-releases/release_dq_domain_validation.sh --repository pypi
scripts/package-releases/release_dq_airflow_sdk.sh --repository pypi
scripts/package-releases/release_dq_airflow_operator.sh --repository pypi
```

If your target repository is configured in `~/.pypirc` (for example, `nexus`), replace `pypi` with that repository name.

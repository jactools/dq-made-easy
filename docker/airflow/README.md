# DQ Airflow

Airflow image/container lifecycle managed by platform-foundation (`platform-airflow`).

This directory contains DQ-specific Airflow configuration:
- `dags/` — DQ-specific DAG definitions

DAGs are deployed to the platform Airflow instance via the Airflow API.

Platform Airflow image and config:
- `platform-foundation/docker/airflow/Dockerfile.airflow`
- `platform-foundation/docker/airflow/start-airflow.sh`
- `platform-foundation/docker/airflow/webserver_config.py`
- `platform-foundation/docker-compose/airflow.yml`

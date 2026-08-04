# Observability (dq-made-easy)

**Observability container lifecycle is managed by `platform-foundation`.**

## Platform vs Consumer Responsibilities

| Service | Platform provides | dq-made-easy provides |
|---|---|---|
| Loki | Container, health check, volume | Config file (`loki-config.yml`) |
| Prometheus | Container, health check, volume | Config (`prometheus.yml`), alerts (`alerts.yml`), OAuth2 secrets |
| Tempo | Container, health check, volume | Config (`tempo-config.yml`) |
| Grafana | Container, health check, volume, `grafana.ini`, OIDC config | Datasources, dashboards, `grafana-init.sh` |
| OTel Collector | Container, ports, volume, `config.yml` | — |
| Pushgateway | Container, health check, volume | — |
| Container Metrics | Container, Python exporter | — |
| Aistor (MinIO) | — | Object storage container |

## Directory Structure

```
observability/
├── grafana/
│   ├── grafana-init.sh                   # Teams and dashboard permissions (DQ-specific)
│   └── provisioning/
│       ├── datasources/                  # DQ datasources (Loki, Prometheus, Tempo)
│       └── dashboards/                   # DQ dashboards
├── loki/
│   └── loki-config.yml                   # DQ Loki config
├── prometheus/
│   ├── prometheus.yml                    # DQ Prometheus scrape config
│   ├── alerts.yml                        # DQ alert rules
│   └── tmp/                              # Runtime secrets (OAuth2 client secret)
├── tempo/
│   └── tempo-config.yml                  # DQ Tempo config
└── postgres-exporter/
    └── queries.yaml                      # DQ-specific PostgreSQL exporter queries
```

## Platform-Observability (platform-foundation)

The platform-foundation provides the observability container lifecycle in
`platform-foundation/docker-compose/observability.yml`. Services include:

- Loki (logs)
- Prometheus (metrics)
- Tempo (traces)
- Grafana (dashboards, OIDC integration)
- OTel Collector (OpenTelemetry)
- Pushgateway (metrics push)
- Container Metrics (Python exporter)

Consumer repos mount their DQ-specific config files at runtime.
**Dashboards and datasources are provisioned via Grafana API, not file mounts.**

## Grafana Init

The `grafana-init.sh` script is DQ-specific and provisions Grafana via API:

- Creates Viewers, Editors, Admins teams
- Imports dashboards from JSON files
- Configures datasources
- Sets dashboard permissions

It runs as a one-shot service after Grafana starts and communicates with
the platform Grafana via its API endpoint.

## Postgres Exporter

The `postgres-exporter/queries.yaml` contains DQ-specific PostgreSQL exporter
queries for the DQ database. It stays in dq-made-easy and is mounted by the
DQ-specific postgres-exporter service.

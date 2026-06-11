# Stack Service Dependency Manifest

Status: [ ] Draft
Last updated: 2026-05-08

## Purpose

This manifest defines the technical blocks behind stack orchestration. Docker compose profiles remain the functional grouping layer, while the items below are the container-level units that start, stop, seed, or reconcile one service at a time.

## Rules

- Start, stop, seed, and reconcile flows must fail fast when a dependency is missing or unhealthy.
- `depends_on` defines start-order requirements, but explicit dependency order still needs to be respected by the shell scripts.
- Stop order is the reverse of the dependency graph.
- Seed artifacts stay separate from runtime seed application.
- The mock-data CSV to SQL pipeline stays unchanged.

## Profile Map

- `base`: shared base image build only.
- `redis`: standalone Redis runtime.
- `core`: database, redis, API, frontend, and core app lifecycle.
- `gateway`: core plus Kong and Keycloak.
- `engine`: Spark runtime and engine helpers.
- `workers`: queue workers that depend on API, Kong, or Redis.
- `profiling`: profiling worker lifecycle.
- `metadata`: OpenMetadata runtime, auth bootstrap, and ingestion. Through `scripts/start-containers.sh --with-metadata`, this also starts/reconciles Keycloak auth and refreshes seeded credentials before OpenMetadata token minting.
- `support`: Zammad support stack and the legacy shared OpenMetadata search node.
- `observability`: exporters, Loki, Prometheus, Tempo, Grafana, and telemetry plumbing.
- `edge`: external ingress rendering only.
- `seed`: one-shot seed and artifact generation containers.

## Technical Blocks

- [ ] 1. base
  - Profiles: base
  - Depends on: none
  - Start: build the shared base image only.
  - Stop: no runtime container.
  - Seed: none.

- [ ] 2. db
  - Profiles: core, gateway, engine, profiling, observability
  - Depends on: none
  - Start: must be healthy before api-migrate, api, Kong, engine workers, profiling worker, and DB exporters.
  - Stop: stop after everything that uses Postgres.
  - Seed: db-seed applies generated SQL into this database.

- [ ] 3. dq-db-postgres-exporter
  - Profiles: observability
  - Depends on: db healthy
  - Start: starts after db and only when metrics are requested.
  - Stop: stop before db.
  - Seed: none.

- [ ] 4. redis
  - Profiles: redis, core, gateway, observability, support
  - Depends on: none
  - Start: must be healthy before API, Zammad, engine workers, profiling worker, and redis-exporter.
  - Stop: stop after Redis consumers.
  - Seed: none.

- [ ] 5. redis-exporter
  - Profiles: observability
  - Depends on: redis healthy
  - Start: starts only after Redis is healthy.
  - Stop: stop before redis.
  - Seed: none.

- [ ] 6. keycloak-seed-artifacts
  - Profiles: auth, gateway
  - Depends on: canonical env selection and generated credentials inputs
  - Start: generates realm JSON, rotated seeded-user credentials, and engine OIDC env artifacts.
  - Stop: no persistent runtime.
  - Seed: feeds the keycloak runtime block.

- [ ] 7. keycloak
  - Profiles: auth, gateway
  - Depends on: keycloak-seed-artifacts completed successfully
  - Start: imports the generated realm and applies the seed-artifact volume.
  - Stop: stop before Kong, OpenMetadata auth bootstrap, and any caller that needs the realm.
  - Seed: seed_stack.sh may rotate seeded passwords against the live realm.

- [ ] 8. api-migrate
  - Profiles: core, gateway, observability
  - Depends on: db healthy
  - Start: run migrations before api.
  - Stop: no persistent runtime.
  - Seed: part of the Postgres reseed flow.

- [ ] 9. api
  - Profiles: core, gateway, observability
  - Depends on: db healthy, redis healthy, api-migrate completed successfully
  - Start: must be healthy before frontend, Kong, engine, and profiling worker.
  - Stop: stop before frontend is torn down.
  - Seed: no direct seed action, but downstream auth and service bootstrap rely on it.

- [ ] 10. frontend
  - Profiles: core
  - Depends on: api healthy
  - Start: start only after the API is healthy.
  - Stop: stop before API and database teardown.
  - Seed: none.

- [ ] 11. kong-db
  - Profiles: gateway, observability
  - Depends on: none
  - Start: must be healthy before Kong migrations and Kong gateway.
  - Stop: stop after Kong and its migrations are finished.
  - Seed: none.

- [ ] 12. kong-postgres-exporter
  - Profiles: observability
  - Depends on: kong-db healthy
  - Start: starts only after Kong database is healthy.
  - Stop: stop before kong-db.
  - Seed: none.

- [ ] 13. kong-migrations
  - Profiles: gateway
  - Depends on: kong-db healthy
  - Start: run once before Kong gateway.
  - Stop: no persistent runtime.
  - Seed: part of gateway bootstrap only.

- [ ] 14. kong
  - Profiles: gateway
  - Depends on: kong-db healthy, kong-migrations completed successfully, api healthy
  - Start: gateway bootstrap and route/credential reconciliation are separate post-start actions.
  - Stop: stop before upstream dependencies.
  - Seed: Kong bootstrap can be rerun after Keycloak reseed.

- [ ] 15. openmetadata-db
  - Profiles: metadata
  - Depends on: none
  - Start: must be healthy before OpenMetadata migration and server startup.
  - Stop: stop after OpenMetadata server and ingestion shutdown.
  - Seed: OpenMetadata auth bootstrap writes to this database.

- [ ] 16. openmetadata-db-postgres-exporter
  - Profiles: metadata
  - Depends on: openmetadata-db healthy
  - Start: starts only after OpenMetadata DB is healthy.
  - Stop: stop before openmetadata-db.
  - Seed: none.

- [ ] 17. openmetadata-search-v9
  - Profiles: metadata
  - Depends on: none
  - Start: must be healthy before OpenMetadata migration and server startup.
  - Stop: stop after OpenMetadata server shutdown.
  - Seed: none.

- [ ] 18. openmetadata-migrate
  - Profiles: metadata
  - Depends on: openmetadata-db healthy, openmetadata-search-v9 healthy
  - Start: run once before openmetadata-server.
  - Stop: no persistent runtime.
  - Seed: part of the OpenMetadata startup/seed sequence.

- [ ] 19. openmetadata-server
  - Profiles: metadata
  - Depends on: openmetadata-db healthy, openmetadata-search-v9 healthy, openmetadata-migrate completed successfully
  - Start: the server must be healthy before openmetadata-configure runs.
  - Stop: stop after openmetadata-configure and openmetadata-ingestion are finished.
  - Seed: no direct seed action, but auth bootstrap and ingestion rely on it.

- [ ] 20. openmetadata-configure
  - Profiles: metadata
  - Depends on: openmetadata-server healthy
  - Start: configure auth settings, restart the server, and mint the OIDC token from seeded credentials.
  - Stop: no persistent runtime.
  - Seed: this is the auth/bootstrap step for OpenMetadata and may also run the LDD sync.

- [ ] 21. openmetadata-ingestion
  - Profiles: metadata
  - Depends on: openmetadata-server healthy
  - Start: runs after the server is healthy and after credentials are available.
  - Stop: stop before openmetadata-server.
  - Seed: runs catalog sync and ingestion during `--seed-all`.

- [ ] 22. zammad-postgresql
  - Profiles: support
  - Depends on: none
  - Start: must be healthy before Zammad init and seed steps.
  - Stop: stop after Zammad application services.
  - Seed: used by zammad-init and zammad-seed.

- [ ] 23. zammad-memcached
  - Profiles: support
  - Depends on: none
  - Start: must be started before Zammad init and app services.
  - Stop: stop after Zammad application services.
  - Seed: none.

- [ ] 24. zammad-init
  - Profiles: support
  - Depends on: zammad-postgresql healthy, redis healthy, zammad-memcached started
  - Start: one-shot bootstrap before the Zammad application services.
  - Stop: no persistent runtime.
  - Seed: initializes the support stack state.

- [ ] 25. zammad-railsserver
  - Profiles: support
  - Depends on: zammad-init completed successfully, zammad-postgresql healthy, redis healthy, zammad-memcached started
  - Start: start after init.
  - Stop: stop before zammad-init dependencies are torn down.
  - Seed: used by zammad-seed and support login bootstrap.

- [ ] 26. zammad-scheduler
  - Profiles: support
  - Depends on: zammad-init completed successfully, zammad-postgresql healthy, redis healthy, zammad-memcached started
  - Start: scheduler follows the init step.
  - Stop: stop before support data stores.
  - Seed: used by zammad lifecycle only.

- [ ] 27. zammad-websocket
  - Profiles: support
  - Depends on: zammad-init completed successfully, zammad-postgresql healthy, redis healthy, zammad-memcached started
  - Start: websocket follows the init step.
  - Stop: stop before support data stores.
  - Seed: used by zammad lifecycle only.

- [ ] 28. zammad-nginx
  - Profiles: support
  - Depends on: zammad-init completed successfully, zammad-railsserver started, zammad-scheduler started, zammad-websocket started
  - Start: final support-facing runtime container.
  - Stop: stop before the Zammad app services.
  - Seed: none.

- [ ] 29. zammad-seed
  - Profiles: support
  - Depends on: zammad-postgresql healthy, redis healthy, zammad-memcached started, zammad-railsserver started
  - Start: one-shot support bootstrap and ticket token provisioning.
  - Stop: no persistent runtime.
  - Seed: creates support users, organizations, and token state.

- [ ] 30. dq-engine
  - Profiles: engine
  - Depends on: api healthy
  - Start: engine runtime follows API availability.
  - Stop: stop after queue workers that depend on it are drained.
  - Seed: no direct seed action.

- [ ] 31. dq-engine-warmup
  - Profiles: engine
  - Depends on: none
  - Start: one-shot Spark jar warmup only.
  - Stop: no persistent runtime.
  - Seed: used before engine runtime when jar caches need population.

- [ ] 32. dq-engine-gx-worker
  - Profiles: workers
  - Depends on: kong healthy, redis healthy
  - Start: worker must wait for gateway and queue availability.
  - Stop: stop before kong and redis.
  - Seed: no direct seed action.

- [ ] 33. dq-engine-join-pair-etl-worker
  - Profiles: workers
  - Depends on: kong healthy, redis healthy
  - Start: worker follows the same dependency rules as the GX worker.
  - Stop: stop before kong and redis.
  - Seed: no direct seed action.

- [ ] 34. dq-engine-test-data-worker
  - Profiles: workers
  - Depends on: redis healthy
  - Start: queue-only worker can start once Redis is available.
  - Stop: stop before Redis.
  - Seed: no direct seed action.

- [ ] 35. profiling-worker
  - Profiles: workers, profiling, observability
  - Depends on: redis healthy, api healthy
  - Start: profiling runtime follows API and queue readiness.
  - Stop: stop before API and Redis.
  - Seed: used by profiling lifecycle smoke flows.

- [ ] 36. loki
  - Profiles: observability
  - Depends on: none
  - Start: starts first in the observability chain.
  - Stop: stop after Grafana, Prometheus, Tempo, and exporters.
  - Seed: none.

- [ ] 37. prometheus
  - Profiles: observability
  - Depends on: loki started
  - Start: starts after Loki.
  - Stop: stop before Loki.
  - Seed: none.

- [ ] 38. tempo
  - Profiles: observability
  - Depends on: prometheus started
  - Start: starts after Prometheus.
  - Stop: stop before Prometheus and Loki.
  - Seed: none.

- [ ] 39. grafana
  - Profiles: observability
  - Depends on: loki started, prometheus started, tempo started
  - Start: dashboard UI comes up after the telemetry backends.
  - Stop: stop before the observability backends.
  - Seed: dashboard access depends on Keycloak OIDC readiness.

- [ ] 40. grafana-init
  - Profiles: observability
  - Depends on: grafana healthy
  - Start: one-shot provisioning for teams and permissions.
  - Stop: no persistent runtime.
  - Seed: provisioning only.

- [ ] 41. container-metrics
  - Profiles: observability
  - Depends on: Docker socket and compose runtime availability
  - Start: metrics sidecar starts independently of the application graph.
  - Stop: stop before the host Docker socket becomes unavailable.
  - Seed: none.

- [ ] 42. pushgateway
  - Profiles: observability, pushgateway
  - Depends on: none
  - Start: optional metrics sink for batch and ephemeral jobs.
  - Stop: stop after producers stop pushing metrics.
  - Seed: none.

- [ ] 43. otel-collector
  - Profiles: observability, otel
  - Depends on: tempo started, prometheus started
  - Start: central tracing collector starts after telemetry backends.
  - Stop: stop before the backends it exports to.
  - Seed: none.

- [ ] 44. aistor
  - Profiles: observability, aistor
  - Depends on: none
  - Start: object store required for delivery objects and exception storage.
  - Stop: stop after services that persist into object storage.
  - Seed: delivery-seed may populate it.

- [ ] 45. edge
  - Profiles: edge
  - Depends on: the upstream services referenced by the rendered edge config
  - Start: render config and run only after the target hosts are available.
  - Stop: stop before the upstream services it fronts.
  - Seed: none.

- [ ] 46. openmetadata-search
  - Profiles: support
  - Depends on: none
  - Start: legacy shared search node kept for the support stack.
  - Stop: stop after OpenMetadata and any support consumers are done.
  - Seed: none.

- [ ] 47. zammad-redis
  - Profiles: zammad-legacy
  - Depends on: none
  - Start: legacy Zammad Redis node, outside the default support flow.
  - Stop: stop before Zammad services.
  - Seed: none.

## Canonical Seed Responsibilities

- `keycloak-seed-artifacts`: generates the realm import and rotated credential files.
- `seed_stack.sh --seed-keycloak`: applies the rotated password set to the live Keycloak realm and syncs the generated credential files back to `tmp`.
- `seed_stack.sh --seed-openmetadata`: loads the seeded credentials after Keycloak reseeding, configures OpenMetadata auth, then mints the OIDC token.
- `start-containers.sh --with-metadata`: starts the auth and metadata profiles together, reconciles the Keycloak `openmetadata` client, reruns `--seed-keycloak` so the live realm matches the current generated credentials, then runs `openmetadata-configure`.
- `db-seed`: converts mock-data CSVs to SQL and applies them to Postgres.
- `delivery-seed`: keeps the delivery-object generation path separate from mock-data SQL generation.

## Notes

- This manifest is the canonical input for decomposing the current start, stop, and seed scripts into smaller technical blocks.
- If a dependency changes, update this manifest before changing the scripts.
- The mock-data CSV to SQL conversion flow remains unchanged by this work.